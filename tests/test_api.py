"""The HTTP API and demo guards, with a scripted model. Background tasks run before
TestClient returns, so each response is followed by a poll to see the result."""

import pytest
from fastapi.testclient import TestClient

from ai_workbench import api, guard
from ai_workbench.config import settings
from conftest import TOOLS_SEEN, call, turn

FIX = ["rmdir /srv/garage/garage.toml && cp /srv/garage/garage.toml.bak /srv/garage/garage.toml", "docker start garage"]


@pytest.fixture
def client(monkeypatch):
    guard.reset()
    monkeypatch.setattr(settings, "demo_password", None)
    return TestClient(api.app)


def run_until_paused(client, script, **body):
    script.extend([turn(call("run_diagnostic", command="docker ps -a")),
                   turn(call("propose_fix", commands=FIX, reason="restore config", risk="restart"))])
    started = client.post("/agent/runs", json={"sample": "01-garage-down", **body})
    assert started.status_code == 200
    return client.get(f"/agent/runs/{started.json()['id']}").json()


def test_health_reports_version(client, monkeypatch):
    assert client.get("/health").json() == {"status": "ok", "version": "dev"}
    monkeypatch.setenv("APP_VERSION", "abc123")
    assert client.get("/health").json()["version"] == "abc123"


def test_page_config_and_samples(client):
    assert "Simulated host" in client.get("/").text
    assert settings.model_smart in client.get("/config").json()["models"]
    names = [s["name"] for s in client.get("/samples").json()]
    assert names == ["01-garage-down", "02-ci-checkout-dns", "03-blank-s3-creds"]


def test_run_pauses_for_approval_then_finishes(client, model):
    script, _ = model
    run = run_until_paused(client, script)
    assert run["status"] == "awaiting_approval"
    assert run["pending"]["commands"] == FIX
    assert "tool_call_id" not in run["pending"]

    script.extend([turn(call("run_diagnostic", command="docker ps")), turn(content="Report: fixed.")])
    assert client.post(f"/agent/runs/{run['id']}/decision", json={"approve": True}).status_code == 200
    done = client.get(f"/agent/runs/{run['id']}").json()
    assert done["status"] == "done" and done["answer"] == "Report: fixed."
    assert done["usage"]["model_seconds"] >= 0

    again = client.post(f"/agent/runs/{run['id']}/decision", json={"approve": True})
    assert again.status_code == 409


def test_runbooks_off_removes_search_tool(client, model):
    script, _ = model
    run = run_until_paused(client, script, use_kb=False)
    assert run["use_kb"] is False
    assert run["steps"][0] == {"kind": "runbooks", "matched": [], "disabled": True}
    assert "search_runbooks" not in TOOLS_SEEN[-1]


def test_model_crash_marks_run_failed(client, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("Token Factory down")
    monkeypatch.setattr(api.agent.llm, "chat_tools", boom)
    monkeypatch.setattr(api.agent.kb, "relevant", lambda q, k=3: [])
    rid = client.post("/agent/runs", json={"sample": "01-garage-down"}).json()["id"]
    run = client.get(f"/agent/runs/{rid}").json()
    assert run["status"] == "failed" and "Try again" in run["answer"]


def test_password_required_when_set(client, monkeypatch):
    from pydantic import SecretStr
    monkeypatch.setattr(settings, "demo_password", SecretStr("judges-2026"))
    assert client.get("/health").status_code == 200  # open for the hosting platform
    assert client.get("/samples").status_code == 401
    assert client.get("/samples", auth=("judge", "wrong")).status_code == 401
    assert client.get("/samples", auth=("judge", "judges-2026")).status_code == 200


def test_log_size_limit(client):
    r = client.post("/agent/runs", json={"log": "x" * (settings.max_log_bytes + 1)})
    assert r.status_code == 413 and "KB" in r.json()["detail"]


def test_unknown_model_refused(client):
    r = client.post("/agent/runs", json={"sample": "01-garage-down", "model": "nvidia/some-expensive-model"})
    assert r.status_code == 422


def test_daily_limit(client, model, monkeypatch):
    script, _ = model
    monkeypatch.setattr(settings, "daily_run_limit", 1)
    run_until_paused(client, script)
    r = client.post("/agent/runs", json={"sample": "01-garage-down"})
    assert r.status_code == 429 and "limit" in r.json()["detail"]


def test_bad_requests(client):
    assert client.post("/agent/runs", json={"sample": "../pyproject"}).status_code == 404
    assert client.post("/agent/runs", json={"log": "   "}).status_code == 422
    assert client.get("/agent/runs/nope").status_code == 404
    assert client.post("/chat", json={"message": "hi"}).status_code in (404, 405)  # open proxy removed
