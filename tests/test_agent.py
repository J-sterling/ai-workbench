"""The agent loop with a scripted model: no network, no database."""

import pytest
from openai.types.chat import ChatCompletionMessageToolCall

from ai_workbench import agent
from conftest import call, turn

FIX = ["rmdir /srv/garage/garage.toml && cp /srv/garage/garage.toml.bak /srv/garage/garage.toml", "docker start garage"]


def start(script, *turns):
    script.extend(turns)
    return agent.start("fatal: connection refused :3900", sample="01-garage-down")


def tool_replies(run) -> dict[str, str]:
    return {m["tool_call_id"]: m["content"] for m in run.messages if m["role"] == "tool"}


def test_fix_waits_for_approval_then_runs_and_verifies(model):
    script, _ = model
    run = start(script,
                turn(call("run_diagnostic", command="docker ps -a --filter name=garage")),
                turn(call("propose_fix", commands=FIX, reason="restore config", risk="restart")))
    assert run.status == "awaiting_approval"
    assert run.pending["commands"] == FIX
    assert run.sandbox.flags == set()  # nothing applied yet

    script.extend([turn(call("run_diagnostic", command="docker ps")), turn(content="Report: fixed.")])
    run = agent.decide(run, approve=True)
    assert run.status == "done"
    assert run.answer == "Report: fixed."
    assert "running" in run.sandbox.flags
    verify = [s for s in run.steps if s["kind"] == "diagnostic"][-1]
    assert "Up " in verify["output"]
    assert [s["kind"] for s in run.steps] == ["runbooks", "diagnostic", "proposal", "decision", "diagnostic", "answer"]
    assert (run.prompt_tokens, run.completion_tokens) == (400, 40)


def test_rejected_fix_never_runs(model):
    script, sent = model
    run = start(script, turn(call("propose_fix", commands=FIX, reason="r", risk="r")))
    script.append(turn(content="Report: steps for tonight."))
    run = agent.decide(run, approve=False, note="not during business hours")
    assert run.status == "done"
    assert run.sandbox.flags == set()
    last_tool = [m for m in sent[-1] if m["role"] == "tool"][-1]["content"]
    assert "Rejected" in last_tool and "not during business hours" in last_tool


def test_write_in_diagnostic_is_refused_and_not_run(model):
    script, _ = model
    run = start(script,
                turn(call("run_diagnostic", command="docker start garage")),
                turn(call("run_diagnostic", command="docker ps")),
                turn(content="Report."))
    refused = run.steps[1]
    assert refused["refused"] and "not on the read-only list" in refused["output"]
    assert run.sandbox.flags == set()
    assert "Exited (1) 4 days ago" in run.steps[2]["output"]  # still broken: the write never happened


def test_one_fix_at_a_time_and_every_call_answered(model):
    script, _ = model
    first, second = call("propose_fix", commands=["docker start garage"], reason="r", risk="r"), \
        call("propose_fix", commands=["docker restart garage"], reason="r", risk="r")
    run = start(script, turn(first, second))
    assert run.pending["tool_call_id"] == first.id
    replies = tool_replies(run)
    assert "Only one fix" in replies[second.id]
    assert first.id not in replies  # answered by decide()


def test_bad_tool_input_gets_an_error_and_the_run_continues(model):
    script, _ = model
    broken = ChatCompletionMessageToolCall(id="bad", type="function", function={"name": "run_diagnostic", "arguments": "{not json"})
    unknown, empty = call("format_disk"), call("propose_fix", commands=[], reason="r", risk="r")
    run = start(script, turn(broken, unknown, empty), turn(content="Report."))
    replies = tool_replies(run)
    assert "not valid JSON" in replies["bad"]
    assert "unknown tool" in replies[unknown.id]
    assert "at least one command" in replies[empty.id]
    assert run.status == "done"


def test_destructive_fix_is_flagged(model):
    script, _ = model
    run = start(script, turn(call("propose_fix", commands=["docker volume rm garage-data"], reason="r", risk="r")))
    assert run.pending["destructive"] is True


def test_turn_limit_stops_a_looping_model(model):
    script, _ = model
    run = start(script, *[turn(call("run_diagnostic", command="docker ps")) for _ in range(agent.MAX_TURNS)])
    assert run.status == "failed"
    assert run.turns == agent.MAX_TURNS


def test_decide_requires_a_pending_fix(model):
    script, _ = model
    run = start(script, turn(content="Report."))
    with pytest.raises(ValueError):
        agent.decide(run, approve=True)


def test_diagnostic_budget_is_enforced(model):
    script, _ = model
    n = agent.MAX_DIAGNOSTICS + 2
    run = start(script, *[turn(call("run_diagnostic", command="docker ps")) for _ in range(n)], turn(content="Report."))
    diagnostics = [s for s in run.steps if s["kind"] == "diagnostic"]
    assert sum(not s.get("skipped") for s in diagnostics) == agent.MAX_DIAGNOSTICS
    assert diagnostics[-1]["skipped"]
    assert "limit" in diagnostics[-1]["output"]
    assert run.status == "done"


def test_checks_are_kept_for_verifying_a_fix(model):
    script, _ = model
    run = start(script, *[turn(call("run_diagnostic", command="docker ps")) for _ in range(agent.MAX_DIAGNOSTICS)],
                turn(call("propose_fix", commands=FIX, reason="r", risk="r")))
    script.extend([*[turn(call("run_diagnostic", command="docker ps")) for _ in range(agent.VERIFY_DIAGNOSTICS)],
                   turn(content="Report.")])
    run = agent.decide(run, approve=True)
    after = [s for s in run.steps[run.steps.index(next(s for s in run.steps if s["kind"] == "decision")):]
             if s["kind"] == "diagnostic"]
    assert len(after) == agent.VERIFY_DIAGNOSTICS and not any(s.get("skipped") for s in after)
    assert "Up " in after[-1]["output"]
