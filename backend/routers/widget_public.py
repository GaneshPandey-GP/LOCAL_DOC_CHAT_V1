"""Public widget endpoints — no auth required, domain-validated + rate-limited."""
import hashlib
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel

from core.audit import log_event
from core.config import is_enabled
from core.db import documents, embed_widgets, widget_events, widget_sessions
from services import rag

router = APIRouter(prefix="/widget", tags=["widget-public"])

# ---------------------------------------------------------------------------
# Pure-JS widget logic (no Python interpolation inside — uses WIDGET_CFG var)
# ---------------------------------------------------------------------------
_WIDGET_JS = r"""
var _sessionId = null;
var _visitorEmail = null;
var _isLoading = false;
var _welcomeShown = false;

function _initWidget() {
  var ec = (WIDGET_CFG.email_collection || 'off');
  if (ec === 'off') {
    document.getElementById('dc-main').style.display = 'flex';
    _showWelcome();
  } else {
    document.getElementById('dc-email-gate').style.display = 'flex';
    document.getElementById('dc-main').style.display = 'none';
  }
}

function dcStartChat(skip) {
  var inp = document.getElementById('dc-email-input');
  var email = inp ? inp.value.trim() : '';
  if (!skip && WIDGET_CFG.email_collection === 'required' && !email) {
    inp.style.borderColor = '#ef4444';
    inp.placeholder = 'Email is required';
    return;
  }
  _visitorEmail = (skip || !email) ? null : email;
  document.getElementById('dc-email-gate').style.display = 'none';
  document.getElementById('dc-main').style.display = 'flex';
  _showWelcome();
}

function _showWelcome() {
  if (_welcomeShown) return;
  _welcomeShown = true;
  _appendMsg('assistant', WIDGET_CFG.welcome_message || 'Hi! How can I help you?');
}

function _autoResize(el) {
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 120) + 'px';
}

function dcHandleKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); dcSend(); }
}

function _escapeHtml(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function _renderMarkdown(text) {
  var s = _escapeHtml(text);
  s = s.replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>');
  s = s.replace(/`([^`\n]+)`/g, '<code>$1</code>');
  s = s.replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>');
  s = s.replace(/\*([^*\n]+)\*/g, '<em>$1</em>');
  s = s.replace(/\n/g, '<br>');
  return s;
}

function _appendMsg(role, text, citations, confidence) {
  var msgs = document.getElementById('dc-messages');
  var wrap = document.createElement('div');
  wrap.className = 'dc-msg dc-' + role;

  var bubble = document.createElement('div');
  bubble.className = 'dc-bubble';
  bubble.innerHTML = _renderMarkdown(text);
  wrap.appendChild(bubble);

  if (role === 'assistant' && WIDGET_CFG.allow_copy) {
    var copyBtn = document.createElement('button');
    copyBtn.className = 'dc-copy';
    copyBtn.title = 'Copy';
    copyBtn.innerHTML = '&#x2398;';
    copyBtn.onclick = function() {
      navigator.clipboard && navigator.clipboard.writeText(bubble.innerText || text);
      copyBtn.innerHTML = '&#x2713;';
      setTimeout(function(){ copyBtn.innerHTML = '&#x2398;'; }, 1500);
    };
    wrap.appendChild(copyBtn);
  }

  if (citations && citations.length && WIDGET_CFG.show_citations) {
    var citeRow = document.createElement('div');
    citeRow.className = 'dc-cites';
    citations.forEach(function(c) {
      var b = document.createElement('span');
      b.className = 'dc-cite-badge';
      b.title = c.text || '';
      b.textContent = '[' + c.index + '] ' + (c.filename || '');
      citeRow.appendChild(b);
    });
    wrap.appendChild(citeRow);
  }

  if (confidence && WIDGET_CFG.show_confidence) {
    var badge = document.createElement('span');
    badge.className = 'dc-conf dc-conf-' + confidence;
    badge.textContent = confidence;
    wrap.appendChild(badge);
  }

  msgs.appendChild(wrap);
  msgs.scrollTop = msgs.scrollHeight;
  return bubble;
}

function _showTyping() {
  var msgs = document.getElementById('dc-messages');
  var d = document.createElement('div');
  d.id = 'dc-typing';
  d.className = 'dc-msg dc-assistant';
  d.innerHTML = '<div class="dc-typing"><span></span><span></span><span></span></div>';
  msgs.appendChild(d);
  msgs.scrollTop = msgs.scrollHeight;
}

function _removeTyping() {
  var t = document.getElementById('dc-typing');
  if (t) t.remove();
}

async function dcSend() {
  if (_isLoading) return;
  var inp = document.getElementById('dc-query');
  var q = inp.value.trim();
  if (!q) return;
  inp.value = '';
  inp.style.height = 'auto';

  var maxQ = WIDGET_CFG.max_questions_per_session || 0;
  if (maxQ > 0) {
    var count = parseInt(document.getElementById('dc-messages').dataset.count || '0', 10);
    if (count >= maxQ) {
      _appendMsg('assistant', 'Session question limit reached. Please refresh to start a new session.');
      return;
    }
    document.getElementById('dc-messages').dataset.count = count + 1;
  }

  _isLoading = true;
  document.getElementById('dc-send').disabled = true;
  _appendMsg('user', q);
  _showTyping();

  try {
    var resp = await fetch(DC_API_BASE + '/widget/' + WIDGET_ID + '/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: q, session_id: _sessionId, visitor_email: _visitorEmail })
    });

    _removeTyping();

    if (!resp.ok) {
      var errData = await resp.json().catch(function(){ return { detail: WIDGET_CFG.fallback_message }; });
      _appendMsg('assistant', errData.detail || WIDGET_CFG.fallback_message);
      return;
    }

    var reader = resp.body.getReader();
    var decoder = new TextDecoder();
    var buf = '';
    var eventType = null;
    var citations = null;
    var confidence = null;
    var bubble = null;
    var fullText = '';

    while (true) {
      var res = await reader.read();
      if (res.done) break;
      buf += decoder.decode(res.value, { stream: true });
      var lines = buf.split('\n');
      buf = lines.pop();

      for (var i = 0; i < lines.length; i++) {
        var line = lines[i].trim();
        if (!line) { eventType = null; continue; }
        if (line.startsWith('event:')) {
          eventType = line.slice(6).trim();
        } else if (line.startsWith('data:')) {
          var dataStr = line.slice(5).trim();
          try {
            var data = JSON.parse(dataStr);
            if (eventType === 'meta') {
              _sessionId = data.session_id;
              citations = data.citations || [];
              confidence = data.confidence;
            } else if (eventType === 'token') {
              if (!bubble) {
                var msgWrap = document.createElement('div');
                msgWrap.className = 'dc-msg dc-assistant';
                bubble = document.createElement('div');
                bubble.className = 'dc-bubble';
                msgWrap.appendChild(bubble);
                document.getElementById('dc-messages').appendChild(msgWrap);
              }
              fullText += data.t || '';
              bubble.innerHTML = _renderMarkdown(fullText);
              document.getElementById('dc-messages').scrollTop = 999999;
            } else if (eventType === 'done') {
              if (!bubble) {
                _appendMsg('assistant', WIDGET_CFG.fallback_message);
              } else {
                var parentWrap = bubble.parentElement;
                if (citations && citations.length && WIDGET_CFG.show_citations) {
                  var cr = document.createElement('div');
                  cr.className = 'dc-cites';
                  citations.forEach(function(c) {
                    var b = document.createElement('span');
                    b.className = 'dc-cite-badge';
                    b.title = c.text || '';
                    b.textContent = '[' + c.index + '] ' + (c.filename || '');
                    cr.appendChild(b);
                  });
                  parentWrap.appendChild(cr);
                }
                if (confidence && WIDGET_CFG.show_confidence) {
                  var badge = document.createElement('span');
                  badge.className = 'dc-conf dc-conf-' + confidence;
                  badge.textContent = confidence;
                  parentWrap.appendChild(badge);
                }
                if (WIDGET_CFG.allow_copy) {
                  var copyBtn2 = document.createElement('button');
                  copyBtn2.className = 'dc-copy';
                  copyBtn2.title = 'Copy';
                  copyBtn2.innerHTML = '&#x2398;';
                  var captured = fullText;
                  copyBtn2.onclick = function() {
                    navigator.clipboard && navigator.clipboard.writeText(captured);
                    copyBtn2.innerHTML = '&#x2713;';
                    setTimeout(function(){ copyBtn2.innerHTML = '&#x2398;'; }, 1500);
                  };
                  parentWrap.appendChild(copyBtn2);
                }
              }
            }
          } catch(e) { /* ignore parse errors */ }
        }
      }
    }
  } catch(e) {
    _removeTyping();
    _appendMsg('assistant', WIDGET_CFG.fallback_message || 'Something went wrong. Please try again.');
  } finally {
    _isLoading = false;
    document.getElementById('dc-send').disabled = false;
  }
}

document.addEventListener('DOMContentLoaded', _initWidget);
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _check_flag():
    if not is_enabled("ENABLE_EMBED_WIDGET"):
        raise HTTPException(status_code=404, detail="Feature not enabled")


def _fingerprint(request: Request) -> str:
    ip = request.client.host if request.client else "unknown"
    ua = request.headers.get("user-agent", "")
    return hashlib.sha256(f"{ip}:{ua}".encode()).hexdigest()[:16]


def _extract_host(origin_or_referer: Optional[str]) -> Optional[str]:
    if not origin_or_referer:
        return None
    try:
        parsed = urlparse(origin_or_referer)
        return parsed.hostname or None
    except Exception:
        return None


def _domain_allowed(widget: dict, origin: Optional[str]) -> bool:
    allowed = [d.strip() for d in widget.get("allowed_domains", []) if d.strip()]
    if not allowed:
        return True  # no whitelist = allow all
    host = _extract_host(origin)
    if not host:
        return False
    for pattern in allowed:
        if pattern.startswith("*."):
            suffix = pattern[2:]
            if host == suffix or host.endswith("." + suffix):
                return True
        elif host == pattern:
            return True
    return False


async def _within_rate_limit(widget: dict, visitor_id: str) -> bool:
    hour_limit = widget.get("rate_limit_hour", 20)
    day_limit = widget.get("rate_limit_day", 500)
    now = datetime.now(timezone.utc)
    wid = widget["widget_id"]

    if hour_limit > 0:
        hour_ago = (now - timedelta(hours=1)).isoformat()
        c = await widget_events.count_documents({
            "widget_id": wid,
            "visitor_id": visitor_id,
            "event_type": "query_sent",
            "created_at": {"$gte": hour_ago},
        })
        if c >= hour_limit:
            return False

    if day_limit > 0:
        day_ago = (now - timedelta(days=1)).isoformat()
        c = await widget_events.count_documents({
            "widget_id": wid,
            "event_type": "query_sent",
            "created_at": {"$gte": day_ago},
        })
        if c >= day_limit:
            return False

    return True


async def _log_w(widget_id: str, session_id: Optional[str], visitor_id: str, event_type: str, payload: Optional[dict] = None):
    await widget_events.insert_one({
        "id": str(uuid.uuid4()),
        "widget_id": widget_id,
        "session_id": session_id,
        "visitor_id": visitor_id,
        "event_type": event_type,
        "payload": payload or {},
        "created_at": datetime.now(timezone.utc).isoformat(),
    })


# ---------------------------------------------------------------------------
# HTML / JS builders
# ---------------------------------------------------------------------------

def _build_loader_js(base_url: str) -> str:
    return (
        "(function(){"
        "'use strict';"
        "var cfg=window.DochatConfig||{};"
        "var wid=cfg.widgetId;"
        "if(!wid){console.warn('[DocChat] widgetId missing in window.DochatConfig');return;}"
        "var base=cfg.baseUrl||'" + base_url + "';"
        "var pos=cfg.position||'bottom-right';"
        "var right=pos==='bottom-left'?'auto':'20px';"
        "var left=pos==='bottom-left'?'20px':'auto';"
        "var container=document.createElement('div');"
        "container.id='dochat-wc';"
        "container.style.cssText='position:fixed;bottom:20px;right:'+right+';left:'+left+';z-index:2147483647;';"
        "var btn=document.createElement('button');"
        "btn.id='dochat-btn';"
        "btn.setAttribute('aria-label','Open chat');"
        "btn.style.cssText='width:56px;height:56px;border-radius:50%;background:#2563EB;color:#fff;border:none;cursor:pointer;box-shadow:0 4px 16px rgba(0,0,0,.22);display:flex;align-items:center;justify-content:center;transition:transform .2s,opacity .2s;';"
        "btn.innerHTML='<svg width=\"24\" height=\"24\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2\"><path d=\"M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z\"></path></svg>';"
        "var panel=document.createElement('div');"
        "panel.id='dochat-panel';"
        "panel.style.cssText='display:none;position:absolute;bottom:68px;right:0;width:380px;height:580px;border-radius:16px;overflow:hidden;box-shadow:0 8px 40px rgba(0,0,0,.18);border:1px solid rgba(0,0,0,.1);background:#fff;transition:opacity .2s,transform .2s;opacity:0;transform:translateY(8px);';"
        "if(window.innerWidth<500){"
        "  panel.style.width=(window.innerWidth-24)+'px';"
        "  panel.style.right=pos==='bottom-left'?'auto':'-8px';"
        "  panel.style.left=pos==='bottom-left'?'-8px':'auto';"
        "}"
        "var iframe=document.createElement('iframe');"
        "iframe.src=base+'/api/widget/'+wid+'/iframe';"
        "iframe.style.cssText='width:100%;height:100%;border:none;';"
        "iframe.allow='clipboard-write';"
        "iframe.setAttribute('title','DocChat');"
        "panel.appendChild(iframe);"
        "var open=false;"
        "btn.addEventListener('click',function(){"
        "  open=!open;"
        "  panel.style.display=open?'block':'none';"
        "  setTimeout(function(){panel.style.opacity=open?'1':'0';panel.style.transform=open?'translateY(0)':'translateY(8px)';},10);"
        "  btn.style.transform=open?'scale(.9)':'scale(1)';"
        "  btn.setAttribute('aria-label',open?'Close chat':'Open chat');"
        "});"
        "container.appendChild(panel);"
        "container.appendChild(btn);"
        "document.body.appendChild(container);"
        "fetch(base+'/api/widget/'+wid+'/config').then(function(r){return r.json();})"
        ".then(function(d){"
        "  var c=d.config||{};"
        "  if(c.brand_color)btn.style.background=c.brand_color;"
        "  if(c.launcher_style==='icon-label'){"
        "    btn.style.width='auto';"
        "    btn.style.borderRadius='28px';"
        "    btn.style.padding='0 16px 0 14px';"
        "    btn.style.gap='8px';"
        "    btn.innerHTML+='<span style=\"font-size:14px;font-weight:600;white-space:nowrap;\">'+(c.title||'Chat')+'</span>';"
        "  }"
        "}).catch(function(){});"
        "})();"
    )


def _unavailable_html() -> str:
    return """<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Widget Unavailable</title></head>
<body style="font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;background:#f4f4f5;margin:0">
<div style="text-align:center;color:#71717a;padding:24px">
  <div style="font-size:32px;margin-bottom:12px">&#128274;</div>
  <div style="font-size:15px;font-weight:600;margin-bottom:4px">Widget Unavailable</div>
  <div style="font-size:13px">This chat widget is not authorized on this domain.</div>
</div></body></html>"""


def _build_widget_html(widget: dict) -> str:
    cfg = widget.get("config", {})
    title = cfg.get("title", "Ask our Knowledge Base")
    subtitle = cfg.get("subtitle", "Ask me anything about our docs...")
    brand_color = cfg.get("brand_color", "#2563EB")
    dark_mode = cfg.get("dark_mode", False)
    email_collection = cfg.get("email_collection", "off")
    widget_id = widget["widget_id"]

    # Derived colors
    bg = "#18181b" if dark_mode else "#ffffff"
    text_c = "#fafafa" if dark_mode else "#18181b"
    surface = "#27272a" if dark_mode else "#f4f4f5"
    border_c = "#3f3f46" if dark_mode else "#e4e4e7"
    muted = "#a1a1aa" if dark_mode else "#71717a"

    cfg_json = json.dumps(cfg)

    email_gate_html = ""
    if email_collection in ("required", "optional"):
        required = email_collection == "required"
        ph = "Email address (required)" if required else "Email address (optional)"
        skip = "" if required else (
            f'<button onclick="dcStartChat(true)" style="background:none;border:none;cursor:pointer;'
            f'font-size:12px;color:{muted};margin-top:4px;padding:4px 0;">Skip</button>'
        )
        email_gate_html = (
            f'<div id="dc-email-gate" style="display:none;flex-direction:column;align-items:center;'
            f'justify-content:center;flex:1;padding:28px 24px;gap:16px;">'
            f'<div style="font-size:18px;font-weight:700;color:{text_c}">Welcome</div>'
            f'<div style="font-size:13px;color:{muted};text-align:center;">Share your email to start chatting.</div>'
            f'<input id="dc-email-input" type="email" placeholder="{ph}" '
            f'style="width:100%;padding:10px 12px;border:1px solid {border_c};border-radius:8px;'
            f'font-size:14px;background:{bg};color:{text_c};outline:none;box-sizing:border-box;"/>'
            f'<button onclick="dcStartChat(false)" style="width:100%;padding:10px;background:{brand_color};'
            f'color:#fff;border:none;border-radius:8px;font-size:14px;font-weight:600;cursor:pointer;">Start Chat</button>'
            f'{skip}'
            f'</div>'
        )

    css = f"""*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:{bg};color:{text_c};height:100vh;display:flex;flex-direction:column;overflow:hidden}}
#dc-header{{background:{brand_color};color:#fff;padding:14px 16px;flex-shrink:0;display:flex;align-items:center;gap:10px}}
#dc-header h1{{font-size:14px;font-weight:700;margin:0}}
#dc-header p{{font-size:11px;opacity:.85;margin:0}}
#dc-main{{flex:1;display:none;flex-direction:column;overflow:hidden;min-height:0}}
#dc-messages{{flex:1;overflow-y:auto;padding:14px;display:flex;flex-direction:column;gap:10px;min-height:0}}
#dc-input-area{{padding:10px 12px;border-top:1px solid {border_c};flex-shrink:0;background:{bg}}}
#dc-input-row{{display:flex;gap:8px;align-items:flex-end}}
#dc-query{{flex:1;padding:9px 12px;border:1px solid {border_c};border-radius:10px;font-size:13px;resize:none;outline:none;background:{bg};color:{text_c};font-family:inherit;max-height:100px}}
#dc-query:focus{{border-color:{brand_color}}}
#dc-send{{background:{brand_color};color:#fff;border:none;border-radius:10px;padding:9px 12px;cursor:pointer;font-size:15px;flex-shrink:0;height:40px;display:flex;align-items:center;justify-content:center}}
#dc-send:disabled{{opacity:.45;cursor:not-allowed}}
.dc-msg{{display:flex;flex-direction:column;gap:3px;max-width:90%}}
.dc-user{{align-self:flex-end;align-items:flex-end}}
.dc-assistant{{align-self:flex-start;align-items:flex-start}}
.dc-bubble{{padding:9px 13px;border-radius:14px;font-size:13px;line-height:1.55;word-break:break-word}}
.dc-user .dc-bubble{{background:{brand_color};color:#fff;border-bottom-right-radius:3px}}
.dc-assistant .dc-bubble{{background:{surface};color:{text_c};border-bottom-left-radius:3px}}
.dc-cites{{display:flex;flex-wrap:wrap;gap:3px;margin-top:2px}}
.dc-cite-badge{{font-size:10px;padding:2px 6px;border-radius:4px;background:{surface};border:1px solid {border_c};color:{muted};cursor:default}}
.dc-conf{{font-size:10px;padding:2px 7px;border-radius:99px;font-weight:700;margin-top:2px;display:inline-block}}
.dc-conf-HIGH{{background:#dcfce7;color:#166534}}
.dc-conf-MEDIUM{{background:#fef9c3;color:#854d0e}}
.dc-conf-LOW{{background:#fee2e2;color:#991b1b}}
.dc-copy{{background:none;border:none;cursor:pointer;color:{muted};font-size:11px;padding:2px 5px;border-radius:3px;opacity:0;transition:opacity .15s;align-self:flex-end}}
.dc-msg:hover .dc-copy{{opacity:1}}
.dc-typing{{display:flex;gap:5px;padding:10px 14px;background:{surface};border-radius:14px;border-bottom-left-radius:3px;width:fit-content}}
.dc-typing span{{width:7px;height:7px;border-radius:50%;background:{muted};animation:dcBounce 1.2s infinite}}
.dc-typing span:nth-child(2){{animation-delay:.2s}}
.dc-typing span:nth-child(3){{animation-delay:.4s}}
@keyframes dcBounce{{0%,60%,100%{{transform:translateY(0)}}30%{{transform:translateY(-5px)}}}}
pre{{background:{surface};padding:8px;border-radius:6px;overflow-x:auto;font-size:11px;margin:2px 0}}
code{{background:{surface};padding:1px 4px;border-radius:3px;font-size:11px}}
a{{color:{brand_color}}}
::-webkit-scrollbar{{width:4px}}::-webkit-scrollbar-track{{background:transparent}}::-webkit-scrollbar-thumb{{background:{border_c};border-radius:2px}}"""

    html = (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        f"<head><meta charset=\"UTF-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        f"<title>{title}</title><style>{css}</style></head>\n"
        "<body>\n"
        f'<div id="dc-header">'
        f'<div><h1>{title}</h1><p>{subtitle}</p></div>'
        f"</div>\n"
        f"{email_gate_html}\n"
        f'<div id="dc-main">\n'
        f'  <div id="dc-messages" data-count="0"></div>\n'
        f'  <div id="dc-input-area">\n'
        f'    <div id="dc-input-row">\n'
        f'      <textarea id="dc-query" rows="1" placeholder="Type your question…"'
        f'        oninput="_autoResize(this)" onkeydown="dcHandleKey(event)"></textarea>\n'
        f'      <button id="dc-send" onclick="dcSend()" aria-label="Send">'
        f'        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">'
        f'<line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>'
        f'      </button>\n'
        f'    </div>\n'
        f'  </div>\n'
        f'</div>\n'
        f"<script>\n"
        f"var WIDGET_ID = {json.dumps(widget_id)};\n"
        f"var WIDGET_CFG = {cfg_json};\n"
        f"var DC_API_BASE = window.location.origin + '/api';\n"
        f"{_WIDGET_JS}\n"
        f"</script>\n"
        "</body></html>"
    )
    return html


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/loader.js", response_class=PlainTextResponse)
async def serve_loader(request: Request):
    _check_flag()
    base_url = str(request.base_url).rstrip("/")
    js = _build_loader_js(base_url)
    return PlainTextResponse(
        content=js,
        media_type="application/javascript",
        headers={
            "Cache-Control": "public, max-age=3600",
            "X-Content-Type-Options": "nosniff",
            "Access-Control-Allow-Origin": "*",
        },
    )


@router.get("/{widget_id}/config")
async def widget_config(widget_id: str, request: Request):
    """Public config — used by loader.js. Domain-validated."""
    _check_flag()
    w = await embed_widgets.find_one(
        {"widget_id": widget_id, "is_active": True},
        {"_id": 0, "widget_id": 1, "config": 1, "allowed_domains": 1},
    )
    if not w:
        raise HTTPException(status_code=404, detail="Widget not found or inactive")

    origin = request.headers.get("origin") or request.headers.get("referer")
    if not _domain_allowed(w, origin):
        raise HTTPException(status_code=403, detail="Domain not allowed")

    return {"widget_id": widget_id, "config": w.get("config", {})}


@router.get("/{widget_id}/iframe", response_class=HTMLResponse)
async def serve_iframe(widget_id: str, request: Request):
    _check_flag()
    w = await embed_widgets.find_one({"widget_id": widget_id, "is_active": True}, {"_id": 0})
    if not w:
        return HTMLResponse(content=_unavailable_html(), status_code=404)

    origin = request.headers.get("origin") or request.headers.get("referer")
    if not _domain_allowed(w, origin):
        visitor_id = _fingerprint(request)
        host = _extract_host(origin) or "unknown"
        await _log_w(widget_id, None, visitor_id, "domain_blocked", {"origin": origin, "domain": host})
        return HTMLResponse(content=_unavailable_html(), status_code=403)

    visitor_id = _fingerprint(request)
    host = _extract_host(origin) or "direct"
    await _log_w(widget_id, None, visitor_id, "opened", {"domain": host})

    html = _build_widget_html(w)
    return HTMLResponse(
        content=html,
        headers={
            "Content-Security-Policy": "frame-ancestors *",
            "X-Frame-Options": "ALLOWALL",
            "Cache-Control": "no-cache, no-store",
            "Access-Control-Allow-Origin": "*",
        },
    )


class WidgetChatBody(BaseModel):
    query: str
    session_id: Optional[str] = None
    visitor_email: Optional[str] = None


@router.post("/{widget_id}/chat")
async def widget_chat(widget_id: str, body: WidgetChatBody, request: Request):
    _check_flag()
    w = await embed_widgets.find_one({"widget_id": widget_id, "is_active": True}, {"_id": 0})
    if not w:
        raise HTTPException(status_code=404, detail="Widget not found")

    # Domain check (Origin from the iframe itself will be the DocChat domain — skip strict check;
    # primary domain enforcement is at /config and /iframe level)
    visitor_id = _fingerprint(request)

    # Rate limit
    if not await _within_rate_limit(w, visitor_id):
        overage = w.get("config", {}).get("fallback_message", "You've reached the query limit. Please try again later.")
        await _log_w(widget_id, body.session_id, visitor_id, "rate_limited", {"query": body.query[:100]})
        raise HTTPException(status_code=429, detail=overage)

    # Session
    session_id = body.session_id
    if session_id:
        s = await widget_sessions.find_one({"id": session_id})
    else:
        s = None

    if not s:
        session_id = str(uuid.uuid4())
        now_iso = datetime.now(timezone.utc).isoformat()
        await widget_sessions.insert_one({
            "id": session_id,
            "widget_id": widget_id,
            "visitor_id": visitor_id,
            "visitor_email": body.visitor_email,
            "query_count": 0,
            "started_at": now_iso,
            "last_active_at": now_iso,
        })

    # Max questions per session check
    max_q = w.get("config", {}).get("max_questions_per_session", 0)
    if max_q > 0:
        session_doc = await widget_sessions.find_one({"id": session_id})
        if session_doc and session_doc.get("query_count", 0) >= max_q:
            raise HTTPException(status_code=429, detail="Session question limit reached.")

    # Log + update session
    await _log_w(widget_id, session_id, visitor_id, "query_sent", {"query": body.query[:200]})
    await widget_sessions.update_one(
        {"id": session_id},
        {"$inc": {"query_count": 1}, "$set": {"last_active_at": datetime.now(timezone.utc).isoformat()}},
    )

    # Resolve active document_ids
    raw_ids = w.get("document_ids", [])
    active_docs = await documents.find(
        {"id": {"$in": raw_ids}, "status": "ready"}, {"_id": 0, "id": 1}
    ).to_list(500)
    active_ids = [d["id"] for d in active_docs]

    show_citations = w.get("config", {}).get("show_citations", True)
    show_confidence = w.get("config", {}).get("show_confidence", True)
    fallback_msg = w.get("config", {}).get("fallback_message", "I don't have enough information to answer that.")

    if not active_ids:
        async def _empty_stream():
            yield f"event: meta\ndata: {json.dumps({'session_id': session_id, 'citations': [], 'confidence': 'LOW'})}\n\n"
            yield f"event: token\ndata: {json.dumps({'t': fallback_msg})}\n\n"
            yield f"event: done\ndata: {json.dumps({'session_id': session_id})}\n\n"
        return StreamingResponse(_empty_stream(), media_type="text/event-stream", headers={
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "no-cache",
        })

    async def event_gen():
        import time
        start = time.time()
        try:
            stream_iter, hits, confidence = await rag.answer_stream(body.query, active_ids)
        except Exception:
            yield f"event: meta\ndata: {json.dumps({'session_id': session_id, 'citations': [], 'confidence': 'LOW'})}\n\n"
            yield f"event: token\ndata: {json.dumps({'t': fallback_msg})}\n\n"
            yield f"event: done\ndata: {json.dumps({'session_id': session_id})}\n\n"
            return

        citations = []
        if show_citations:
            citations = [
                {
                    "index": i + 1,
                    "filename": h["filename"],
                    "page": h["page"],
                    "document_id": h["document_id"],
                    "text": h["text"][:300],
                }
                for i, h in enumerate(hits)
            ]

        yield f"event: meta\ndata: {json.dumps({'session_id': session_id, 'citations': citations, 'confidence': confidence if show_confidence else None})}\n\n"

        full_text = []
        async for token in stream_iter:
            full_text.append(token)
            yield f"event: token\ndata: {json.dumps({'t': token})}\n\n"

        await _log_w(widget_id, session_id, visitor_id, "answer_received", {
            "latency_ms": int((time.time() - start) * 1000),
            "confidence": confidence,
        })
        yield f"event: done\ndata: {json.dumps({'session_id': session_id})}\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type",
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
