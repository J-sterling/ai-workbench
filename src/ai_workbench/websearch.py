"""Web search for the agent through Tavily, with a privacy filter and a daily cap.

Only the model's short query leaves the server, never the log. Queries are trimmed and
stripped of IPs, emails, credentials in URLs and token-like strings first. Results are
cached by query, and the daily count is kept in a small file so a restart of the app
doesn't reset it; if that file can't be read, searches stop for the day (fail closed).
"""

import json
import re
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ai_workbench.config import settings

API = "https://api.tavily.com/search"
MAX_QUERY_CHARS = 200
MAX_RESULTS = 3
MAX_SNIPPET_CHARS = 500

_REDACT = [
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), "[email]"),
    (re.compile(r"\b\w+://[^\s/@]+@\S+"), "[url]"),
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}(?::\d+)?\b"), "[ip]"),
    (re.compile(r"\b(?:[0-9a-f]{1,4}:){2,7}[0-9a-f]{1,4}\b", re.I), "[ip]"),
    # file paths and internal host names (public domains such as php.net stay, they are search terms)
    (re.compile(r"(?<![\w.])(?:~|\.{1,2})?/[\w.-]+(?:/[\w.@-]*)+"), "[path]"),
    (re.compile(r"\b[\w-]+(?:\.[\w-]+)*\.(?:local|lan|internal|intranet|corp|home|localdomain|private|test)\b", re.I), "[host]"),
    # long mixed letter/digit strings: API keys, tokens, hashes
    (re.compile(r"\b(?=[\w+/=-]*\d)(?=[\w+/=-]*[A-Za-z])[\w+/=-]{24,}\b"), "[token]"),
]

# For checking advisories: project, government and distribution security sources only.
OFFICIAL = ["php.net", "nvd.nist.gov", "cve.org", "cisa.gov", "cert.europa.eu", "ncsc.gov.uk",
            "ubuntu.com", "debian.org", "access.redhat.com", "github.com/advisories"]

_lock = threading.Lock()
_cache: dict[str, list[dict]] = {}


@dataclass
class Outcome:
    query: str  # what was actually sent (after the filter), or would have been
    results: list[dict]  # [{title, url, snippet}]
    error: str = ""  # why nothing was searched, for the model and the UI


def enabled() -> bool:
    return bool(settings.tavily_api_key and settings.tavily_api_key.get_secret_value())


def clean(query: str) -> str:
    q = " ".join(str(query).split())
    for pattern, repl in _REDACT:
        q = pattern.sub(repl, q)
    return q[:MAX_QUERY_CHARS].strip()


def _state_path() -> Path:
    return Path(settings.web_search_state_file)


def _spend() -> str:
    """Count one search against today's limit (UTC). Returns an error, or "" if allowed."""
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    path = _state_path()
    with _lock:
        try:
            state = json.loads(path.read_text()) if path.exists() else {}
            count = int(state.get("count", 0)) if state.get("date") == today else 0
        except (OSError, ValueError, AttributeError):
            return "web search is paused: its daily counter could not be read"
        if count >= settings.web_search_daily_limit:
            return f"today's limit of {settings.web_search_daily_limit} web searches is used up"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"date": today, "count": count + 1}))
        except OSError:
            return "web search is paused: its daily counter could not be saved"
    return ""


def _call(query: str, official: bool = False) -> list[dict]:
    payload = {"query": query, "search_depth": "basic", "max_results": MAX_RESULTS}
    if official:
        payload["include_domains"] = OFFICIAL
    body = json.dumps(payload).encode()
    req = urllib.request.Request(API, data=body, method="POST", headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.tavily_api_key.get_secret_value()}",
    })
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read())
    return [
        {"title": str(r.get("title", ""))[:200], "url": str(r.get("url", "")),
         "snippet": " ".join(str(r.get("content", "")).split())[:MAX_SNIPPET_CHARS]}
        for r in data.get("results", [])[:MAX_RESULTS]
        if str(r.get("url", "")).startswith(("https://", "http://"))
    ]


def search(query: str, official: bool = False) -> Outcome:
    q = clean(query)
    if not enabled():
        return Outcome(q, [], "web search is not configured on this server")
    if len(q) < 3:
        return Outcome(q, [], "the query is empty after removing private details; use public terms such as an error string or CVE ID")
    key = ("official:" if official else "") + q.lower()
    if key in _cache:
        return Outcome(q, _cache[key])
    if err := _spend():
        return Outcome(q, [], err)
    try:
        results = _call(q, official)
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as e:
        return Outcome(q, [], f"the search failed ({type(e).__name__}); continue without it")
    _cache[key] = results
    return Outcome(q, results)


def reset() -> None:
    """For tests."""
    with _lock:
        _cache.clear()
