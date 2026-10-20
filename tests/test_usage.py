"""Usage records and the summary behind the live Usage page."""

import time
from types import SimpleNamespace

from fastapi.testclient import TestClient

from ai_workbench import api, guard, llm, usage
from ai_workbench.config import settings

SUPER = "nvidia/nemotron-3-super-120b-a12b"


def test_summary_counts_today_minutes_and_models(monkeypatch):
    monkeypatch.setattr(settings, "prices", {SUPER: [1.0, 2.0]})
    usage.record("agent", SUPER, 1000, 100, 1.5, "run1")
    usage.record("agent", SUPER, 2000, 200, 2.5, "run1")
    usage.record("embed", "Qwen/Qwen3-Embedding-8B", 50, 0, 0.2, "retrieval")
    s = usage.summary()
    assert s["today"]["calls"] == 3 and s["today"]["in"] == 3050 and s["today"]["out"] == 300
    assert s["today"]["cost"] == round((3000 * 1 + 300 * 2) / 1e6, 6)
    assert s["today"]["unpriced_calls"] == 1  # the embedding has no price
    assert s["by_model"][0]["model"] == SUPER and s["by_model"][0]["calls"] == 2
    assert len(s["per_minute"]) == 60 and s["per_minute"][-1]["in"] == 3050
    assert s["recent"][0]["kind"] == "embed"  # newest first


def test_old_calls_count_all_time_but_not_today():
    usage.record("chat", SUPER, 10, 1, 0.1)
    s = usage.summary(now=time.time() + 3 * 86400)
    assert s["today"]["calls"] == 0 and s["all_time"]["calls"] == 1
    assert sum(m["calls"] for m in s["per_minute"]) == 0


def test_no_prices_means_no_cost():
    usage.record("chat", SUPER, 10, 1, 0.1)
    assert usage.summary()["today"]["cost"] is None


def test_model_calls_are_recorded(monkeypatch):
    resp = SimpleNamespace(usage=SimpleNamespace(prompt_tokens=7, completion_tokens=3),
                           choices=[SimpleNamespace(message=SimpleNamespace(content="ok", tool_calls=None))], model=SUPER)
    monkeypatch.setattr(llm.client.chat.completions, "create", lambda **kw: resp)
    llm.chat_tools([{"role": "user", "content": "x"}], [], model=SUPER, tag="abc")
    last = usage.summary()["recent"][0]
    assert (last["kind"], last["in"], last["out"], last["tag"]) == ("agent", 7, 3, "abc")
    assert "content" not in last  # counts only, never text


def test_usage_endpoints(monkeypatch):
    guard.reset()
    monkeypatch.setattr(settings, "demo_password", None)
    client = TestClient(api.app)
    usage.record("agent", SUPER, 5, 1, 0.1, "r")
    assert "Token usage" in client.get("/usage").text
    assert client.get("/usage/data").json()["today"]["calls"] == 1
