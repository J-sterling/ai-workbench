import json

import pytest
from pydantic import SecretStr

from ai_workbench import agent, websearch
from ai_workbench.config import settings
from conftest import TOOLS_SEEN, call, turn

RESULTS = [{"title": "CISA: Critical Vulnerabilities in PHP", "url": "https://www.cisa.gov/x", "snippet": "Update to 8.3.36"}]


@pytest.fixture
def web_on(monkeypatch):
    monkeypatch.setattr(settings, "tavily_api_key", SecretStr("tvly-test"))
    sent = []
    monkeypatch.setattr(websearch, "_call", lambda q, official=False: sent.append(q) or RESULTS)
    return sent


def test_tool_offered_only_with_a_key(model, monkeypatch):
    script, _ = model
    script.append(turn(content="Report"))
    agent.start("log")
    assert "search_web" not in TOOLS_SEEN[-1]
    monkeypatch.setattr(settings, "tavily_api_key", SecretStr("tvly-test"))
    script.append(turn(content="Report"))
    run = agent.start("log")
    assert "search_web" in TOOLS_SEEN[-1]
    assert "Runbook check" in run.messages[0]["content"]
    script.append(turn(content="Report"))
    assert "never say a runbook matched" in agent.start("log", use_kb=False).messages[0]["content"]


def test_results_reach_the_model_and_per_run_cap(model, web_on):
    script, sent = model
    script += [
        turn(call("search_web", query="CVE-2026-109618 PHP fixed version")),
        turn(call("search_web", query="php 8.3.36 release")),
        turn(call("search_web", query="third search")),
        turn(call("propose_fix", commands=["apt-get install --only-upgrade php8.3-fpm"], reason="r", risk="k",
                  sources=["https://www.cisa.gov/x", "https://cert.europa.eu/not-searched", "javascript:alert(1)"])),
    ]
    run = agent.start("log")
    assert web_on == ["CVE-2026-109618 PHP fixed version", "php 8.3.36 release"]  # third never sent
    tool_replies = [m["content"] for m in sent[-1] if m["role"] == "tool"]
    assert "https://www.cisa.gov/x" in tool_replies[0] and "<untrusted_web_content>" in tool_replies[0]
    assert "limit of 2 web searches" in tool_replies[2]
    assert run.pending["sources"] == ["https://www.cisa.gov/x"]  # only links the search returned
    assert [s["kind"] for s in run.steps].count("web") == 3


def test_daily_cap_and_fail_closed(web_on, monkeypatch):
    monkeypatch.setattr(settings, "web_search_daily_limit", 2)
    assert websearch.search("query one").results
    assert websearch.search("query one").results  # cached, not counted
    assert websearch.search("query two").results
    assert "limit of 2" in websearch.search("query three").error
    assert web_on == ["query one", "query two"]
    # a counter file that can't be read stops searches instead of resetting them
    with open(settings.web_search_state_file, "w") as f:
        f.write("not json")
    assert "paused" in websearch.search("query four").error


def test_private_details_never_leave(web_on):
    q = ("dial tcp 10.0.0.5:3900 refused for admin@example.com via https://user:pw@git.example/x "
         "key AbCdEf0123456789XyZabcd012 in /srv/garage/garage.toml on db1.corp.internal php.net")
    out = websearch.search(q)
    sent = web_on[0]
    for secret in ("10.0.0.5", "admin@example.com", "user:pw", "AbCdEf0123456789XyZabcd012", "/srv/garage", "db1.corp"):
        assert secret not in sent
    assert "[ip]" in sent and "[email]" in sent and "[token]" in sent and "[path]" in sent and "[host]" in sent
    assert "php.net" in sent  # public domains are search terms
    assert len(websearch.clean("x" * 500)) <= websearch.MAX_QUERY_CHARS
    assert out.query == sent
    assert json.loads(open(settings.web_search_state_file).read())["count"] == 1


def test_fix_from_a_cve_runbook_is_checked_live_first(model, web_on, monkeypatch):
    from ai_workbench import kb
    monkeypatch.setattr(agent.kb, "relevant", lambda q, k=3: [kb.Hit("runbooks/php2shell.md", "PHP2Shell", "Fixed in 8.3.36 (CVE-2026-109618)", 0.9)])
    script, sent = model
    fix = dict(commands=["apt-get install --only-upgrade php8.3-fpm"], reason="r", risk="k")
    script += [turn(call("propose_fix", **fix)), turn(call("search_web", query="CVE-2026-109618 fixed version")),
               turn(call("propose_fix", **fix, sources=["https://www.cisa.gov/x"]))]
    run = agent.start("log")
    first_reply = [m["content"] for m in sent[1] if m["role"] == "tool"][0]
    assert "cites CVE-2026-109618" in first_reply
    assert web_on == ["CVE-2026-109618 fixed version"]
    assert run.status == "awaiting_approval" and run.pending["sources"] == ["https://www.cisa.gov/x"]
