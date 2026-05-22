"""AI input controls (Stream 6).

Detects prompt-injection attempts, dangerous keywords and crude cost estimation
BEFORE the natural-language input is sent to the LLM. Returns a verdict and
risk score so the orchestrator can short-circuit unsafe requests.
"""
import re
from dataclasses import dataclass

# Patterns that strongly suggest prompt injection / jailbreak
INJECTION_PATTERNS = [
    r"ignore (the )?(previous|prior) (instructions|prompts)",
    r"you are now",
    r"pretend (to be|you are)",
    r"system\s*:\s*",
    r"developer mode",
    r"act as (?:an?\s+)?(admin|root|dba)",
]

# Dangerous SQL keywords — must never appear in user input, even verbatim
DANGEROUS_KEYWORDS = [
    "drop table", "drop database", "truncate", "delete from",
    "alter table", "create table", "create user", "grant ",
    "revoke ", "insert into", "update ", "merge ", "exec ",
    "execute ", "xp_cmdshell", "pg_read_server_files", "copy from",
    "copy to", "; --",
]


@dataclass
class GuardVerdict:
    allowed: bool
    risk: int          # 0 (low) to 100 (high)
    reasons: list[str]


def check_user_input(text: str) -> GuardVerdict:
    if not text or not text.strip():
        return GuardVerdict(False, 100, ["Empty query"])
    if len(text) > 2000:
        return GuardVerdict(False, 70, ["Query exceeds 2000 characters"])

    lower = text.lower()
    reasons: list[str] = []
    risk = 0

    for pat in INJECTION_PATTERNS:
        if re.search(pat, lower):
            reasons.append(f"Possible prompt injection pattern: {pat}")
            risk += 35

    for kw in DANGEROUS_KEYWORDS:
        if kw in lower:
            reasons.append(f"Dangerous keyword in user input: {kw}")
            risk += 50

    risk = min(risk, 100)
    return GuardVerdict(allowed=(risk < 50), risk=risk, reasons=reasons)


def estimate_query_cost(sql: str) -> int:
    """Very rough heuristic cost estimate (0-100) used to gate execution.

    Real cost would come from EXPLAIN; this is a fast offline heuristic so the
    LLM call itself can be skipped when the user input looks impossibly broad.
    """
    if not sql:
        return 0
    s = sql.lower()
    cost = 0
    if "select *" in s:
        cost += 25
    cost += s.count(" join ") * 15
    cost += s.count("group by") * 10
    cost += s.count("order by") * 5
    if "limit" not in s:
        cost += 30
    return min(cost, 100)
