"""LLM client — reads active model config from DB at call time.

Priority:
  1. Active model_config document in MongoDB  (set from Settings UI)
  2. Environment variables / core.config      (legacy fallback)
"""
import logging
from typing import AsyncIterator, List, Optional

from openai import AsyncOpenAI

logger = logging.getLogger("docchat.llm")

# Module-level cached client.  Cleared whenever the active model changes.
_client: Optional[AsyncOpenAI] = None
_client_key: Optional[str] = None   # tracks which config the client was built for


async def _get_active_config() -> dict:
    """Return the active LLM model_config from DB, or fall back to env config."""
    try:
        from core.db import model_configs
        doc = await model_configs.find_one(
            {"model_type": "llm", "is_active": True},
            {"_id": 0},
        )
        if doc:
            return doc
    except Exception as e:
        logger.warning("Could not read active LLM config from DB: %s", e)

    # Fallback: build a synthetic config from env vars
    from core import config as cfg
    return {
        "provider": cfg.LLM_PROVIDER,
        "model_id": cfg.LLM_MODEL,
        "api_key": (
            cfg.OPENROUTER_API_KEY if cfg.LLM_PROVIDER == "openrouter"
            else cfg.EMERGENT_LLM_KEY
        ),
        "api_base_url": (
            cfg.OPENROUTER_BASE_URL if cfg.LLM_PROVIDER == "openrouter"
            else cfg.EMERGENT_BASE_URL
        ),
    }


def _build_client(config: dict) -> AsyncOpenAI:
    """Instantiate an AsyncOpenAI-compatible client from a model config dict."""
    from core import config as cfg

    provider = (config.get("provider") or "").lower()
    api_key = config.get("api_key") or ""
    base_url = config.get("api_base_url") or ""

    # Resolve api_key from env if not stored in DB config
    if not api_key:
        if provider == "openrouter":
            api_key = cfg.OPENROUTER_API_KEY
        elif provider == "emergent":
            api_key = cfg.EMERGENT_LLM_KEY
        elif provider == "openai":
            api_key = cfg.OPENAI_API_KEY
        elif provider == "anthropic":
            api_key = cfg.ANTHROPIC_API_KEY

    # Resolve base_url default per provider
    if not base_url:
        if provider == "openrouter":
            base_url = cfg.OPENROUTER_BASE_URL
        elif provider == "emergent":
            base_url = cfg.EMERGENT_BASE_URL
        # openai/anthropic/custom: use OpenAI SDK default if no override

    if not api_key:
        raise RuntimeError(
            f"No API key found for LLM provider '{provider}'. "
            "Add one via Settings → Models or set the matching env var."
        )

    kwargs: dict = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    if provider == "openrouter":
        kwargs["default_headers"] = {
            "HTTP-Referer": "https://docchat.app",
            "X-Title": "DocChat",
        }

    return AsyncOpenAI(**kwargs)


async def _get_client_and_model() -> tuple[AsyncOpenAI, str]:
    """Return (client, model_id), rebuilding the client if the active config changed."""
    global _client, _client_key

    config = await _get_active_config()
    config_key = f"{config.get('provider')}:{config.get('model_id')}:{bool(config.get('api_key'))}"

    if _client is None or _client_key != config_key:
        logger.info(
            "Building LLM client: provider=%s model=%s",
            config.get("provider"), config.get("model_id"),
        )
        _client = _build_client(config)
        _client_key = config_key

    return _client, config.get("model_id") or "gpt-4o-mini"


async def chat_complete(
    messages: List[dict], model: Optional[str] = None, temperature: float = 0.2
) -> str:
    client, active_model = await _get_client_and_model()
    resp = await client.chat.completions.create(
        model=model or active_model,
        messages=messages,
        temperature=temperature,
    )
    return resp.choices[0].message.content or ""


async def chat_stream(
    messages: List[dict],
    model: Optional[str] = None,
    temperature: float = 0.2,
) -> AsyncIterator[str]:
    client, active_model = await _get_client_and_model()
    stream = await client.chat.completions.create(
        model=model or active_model,
        messages=messages,
        temperature=temperature,
        stream=True,
    )
    async for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if delta and delta.content:
            yield delta.content
