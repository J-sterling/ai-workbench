"""Triage agent: diagnoses with read-only commands, then pauses for human approval
before any fix runs.

A run moves running -> awaiting_approval -> running -> ... -> done. advance() calls the
model until it either proposes a fix (pause) or writes its final report (done).
decide() records the human's answer and resumes.
"""

import json
import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from ai_workbench import kb, llm
from ai_workbench.config import settings
from ai_workbench.sandbox import Sandbox, is_destructive, refusal

SYSTEM = """You are an infrastructure triage agent. You get a failed run's log and any matching runbooks.

Work in this order:
1. Confirm the root cause with run_diagnostic (read-only commands only, at most 6; the server stops you after that). Prefer the runbook's diagnose steps.
2. If the fix changes anything, call propose_fix once with the exact commands, in order. A human approves or
   rejects it; nothing changes until then. Never include commands that delete data, volumes or state unless the
   runbook says to.
3. After an approved fix, verify it with one or two diagnostics.
4. Finish (no tool call) with a short report:
   Error group / Root cause (name the runbook, if one matched) / What was done / Follow-up to prevent it.

If no runbook matches, say so and reason from the log and diagnostics. Never print secrets."""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "run_diagnostic",
            "description": "Run one read-only shell command on the affected host and return its output. "
            "Commands that change state or print secrets are refused; use propose_fix for changes. "
            "To check whether a secret is set, print its length (echo ${#VAR}), never its value.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "e.g. docker ps -a --filter name=garage"},
                    "why": {"type": "string", "description": "What this checks, in a few words."},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_runbooks",
            "description": "Search the runbook knowledge base for a symptom or error string.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_fix",
            "description": "Propose commands that change the system. Pauses until a human approves or rejects.",
            "parameters": {
                "type": "object",
                "properties": {
                    "commands": {"type": "array", "items": {"type": "string"}},
                    "reason": {"type": "string", "description": "Why this fixes the root cause."},
                    "risk": {"type": "string", "description": "What could go wrong or be interrupted."},
                },
                "required": ["commands", "reason", "risk"],
            },
        },
    },
]

MAX_TURNS = 12
# Server-side cap so a wandering model cannot burn credits on diagnostics.
MAX_DIAGNOSTICS = 6
# Checks kept free for verifying a fix after the operator decides.
VERIFY_DIAGNOSTICS = 3
MAX_OUTPUT_CHARS = 4000
# Runs live in memory; the oldest are dropped so a public demo cannot grow it forever.
MAX_RUNS = 200

log = logging.getLogger(__name__)


@dataclass
class Run:
    id: str
    model: str
    sandbox: Sandbox
    messages: list[dict]
    runbooks: list[kb.Hit] = field(default_factory=list)
    steps: list[dict] = field(default_factory=list)
    status: str = "running"  # running | awaiting_approval | done | failed
    pending: dict | None = None  # the fix waiting for approval
    answer: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    turns: int = 0
    diagnostics: int = 0
    use_kb: bool = True
    sample: str | None = None
    model_seconds: float = 0.0  # time spent waiting on Token Factory


OnStep = Callable[[dict], None]

RUNS: dict[str, Run] = {}


def new_run(log_text: str, sample: str | None = None, model: str | None = None, use_kb: bool = True) -> Run:
    """Register a run without calling any model. begin() does the work."""
    while len(RUNS) >= MAX_RUNS:
        RUNS.pop(next(iter(RUNS)))
    run = Run(
        id=uuid.uuid4().hex[:12],
        model=model or settings.model_smart,
        sandbox=Sandbox.for_sample(sample) if sample else Sandbox(),
        messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": log_text}],
        use_kb=use_kb,
        sample=sample,
    )
    RUNS[run.id] = run
    return run


def begin(run: Run, on_step: OnStep | None = None) -> Run:
    """Retrieve runbooks (unless disabled), then let the model work until it pauses or finishes."""
    log_text = run.messages[1]["content"]
    if run.use_kb:
        run.runbooks = kb.relevant(kb.log_query(log_text))
        context = "\n\n---\n\n".join(f"Runbook: {h.source}\n\n{h.content}" for h in run.runbooks)
        run.messages[1]["content"] = f"Runbooks:\n\n{context or '(none matched)'}\n\nLog:\n\n{log_text}"
        matched = [{"source": h.source, "score": round(h.score, 3)} for h in run.runbooks]
        _step(run, on_step, kind="runbooks", matched=matched)
    else:
        run.messages[1]["content"] = f"Runbooks: (knowledge base turned off for this run)\n\nLog:\n\n{log_text}"
        _step(run, on_step, kind="runbooks", matched=[], disabled=True)
    return advance(run, on_step)


def start(log_text: str, sample: str | None = None, model: str | None = None, on_step: OnStep | None = None,
          use_kb: bool = True) -> Run:
    return begin(new_run(log_text, sample, model, use_kb), on_step)


def record_decision(run: Run, approve: bool, note: str = "", on_step: OnStep | None = None) -> None:
    """Apply (or not) the pending fix and hand the result to the model. advance() continues."""
    if run.status != "awaiting_approval" or not run.pending:
        raise ValueError(f"run {run.id} is not waiting for approval (status: {run.status})")
    fix, run.pending = run.pending, None
    if approve:
        outputs = [f"$ {c}\n{run.sandbox.apply(c)}".rstrip() for c in fix["commands"]]
        result = "Approved by the operator and executed:\n\n" + "\n\n".join(outputs)
    else:
        result = (
            f"Rejected by the operator. Note: {note or '(none)'}\n"
            "Nothing was run. Finish with a report saying what the operator should do instead."
        )
    _step(run, on_step, kind="decision", approved=approve, note=note, output=result)
    run.messages.append({"role": "tool", "tool_call_id": fix["tool_call_id"], "content": result})
    # However many checks diagnosis used, keep a few for verifying the outcome.
    run.diagnostics = min(run.diagnostics, MAX_DIAGNOSTICS - VERIFY_DIAGNOSTICS)
    run.status = "running"


def decide(run: Run, approve: bool, note: str = "", on_step: OnStep | None = None) -> Run:
    record_decision(run, approve, note, on_step)
    return advance(run, on_step)


def safely(work: Callable[[Run], Run], run: Run) -> None:
    """For background tasks: a crash marks the run failed instead of leaving it 'running' forever."""
    try:
        work(run)
    except Exception:
        log.exception("run %s failed", run.id)
        run.status, run.pending = "failed", None
        run.answer = "The run stopped because a model or database call failed. Try again in a moment."


def advance(run: Run, on_step: OnStep | None = None) -> Run:
    while run.status == "running":
        if run.turns >= MAX_TURNS:
            run.status, run.answer = "failed", f"Stopped after {MAX_TURNS} model turns without a final report."
            break
        run.turns += 1
        tools = TOOLS if run.use_kb else [t for t in TOOLS if t["function"]["name"] != "search_runbooks"]
        t0 = time.monotonic()
        msg, usage = llm.chat_tools(run.messages, tools, model=run.model, max_tokens=2048, tag=run.id)
        run.model_seconds += time.monotonic() - t0
        if usage:
            run.prompt_tokens += usage.prompt_tokens
            run.completion_tokens += usage.completion_tokens
        calls = msg.tool_calls or []
        run.messages.append(
            {
                "role": "assistant",
                "content": msg.content or "",
                **({"tool_calls": [c.model_dump(include={"id", "type", "function"}) for c in calls]} if calls else {}),
            }
        )
        if not calls:
            run.status, run.answer = "done", llm.text_of(msg)
            _step(run, on_step, kind="answer", text=run.answer)
            break
        for call in calls:
            _handle(run, call, on_step)
    return run


def _handle(run: Run, call, on_step: OnStep | None) -> None:
    """Answer one tool call, or park it as the pending fix. Every call gets a reply
    except the pending one, which decide() answers."""
    name = call.function.name
    try:
        args = json.loads(call.function.arguments or "{}")
    except json.JSONDecodeError:
        return _reply(run, call, f"Error: arguments were not valid JSON: {call.function.arguments!r}")

    if name == "run_diagnostic":
        cmd = str(args.get("command", "")).strip()
        if run.diagnostics >= MAX_DIAGNOSTICS:
            out = f"Not run: the limit of {MAX_DIAGNOSTICS} diagnostics is used up. Propose a fix or write the report now."
            _step(run, on_step, kind="diagnostic", command=cmd, why=args.get("why", ""), skipped=True, output=out)
            return _reply(run, call, out)
        run.diagnostics += 1
        reason = refusal(cmd)
        if reason:
            out = f"Refused: {reason}. Diagnostics must be read-only; use propose_fix for anything that changes the system."
            _step(run, on_step, kind="diagnostic", command=cmd, why=args.get("why", ""), refused=True, output=out)
        else:
            out = run.sandbox.run(cmd)[:MAX_OUTPUT_CHARS]
            _step(run, on_step, kind="diagnostic", command=cmd, why=args.get("why", ""), output=out)
        return _reply(run, call, out)

    if name == "search_runbooks":
        hits = kb.relevant(str(args.get("query", "")))
        _step(run, on_step, kind="search", query=args.get("query"), matched=[h.source for h in hits])
        body = "\n\n---\n\n".join(f"Runbook: {h.source}\n\n{h.content}" for h in hits)
        return _reply(run, call, body or "No runbook matched.")

    if name == "propose_fix":
        if run.pending:
            return _reply(run, call, "Only one fix at a time. Propose it again after the current one is decided.")
        commands = [str(c) for c in args.get("commands", []) if str(c).strip()]
        if not commands:
            return _reply(run, call, "Error: propose_fix needs at least one command.")
        run.pending = {
            "tool_call_id": call.id,
            "commands": commands,
            "reason": args.get("reason", ""),
            "risk": args.get("risk", ""),
            "destructive": is_destructive(commands),
        }
        run.status = "awaiting_approval"
        _step(run, on_step, kind="proposal", **{k: v for k, v in run.pending.items() if k != "tool_call_id"})
        return None

    return _reply(run, call, f"Error: unknown tool {name!r}.")


def _reply(run: Run, call, content: str) -> None:
    run.messages.append({"role": "tool", "tool_call_id": call.id, "content": content})


def _step(run: Run, on_step: OnStep | None, **step) -> None:
    run.steps.append(step)
    if on_step:
        on_step(step)


def view(run: Run) -> dict:
    """What the API returns: everything except the raw message history."""
    return {
        "id": run.id,
        "status": run.status,
        "model": run.model,
        "sample": run.sample,
        "use_kb": run.use_kb,
        "turns": run.turns,
        "diagnostics": run.diagnostics,
        "limits": {"turns": MAX_TURNS, "diagnostics": MAX_DIAGNOSTICS},
        "runbooks": [{"source": h.source, "title": h.title, "score": round(h.score, 3)} for h in run.runbooks],
        "steps": run.steps,
        "pending": {k: v for k, v in run.pending.items() if k != "tool_call_id"} if run.pending else None,
        "answer": run.answer,
        "usage": {"prompt": run.prompt_tokens, "completion": run.completion_tokens,
                  "model_seconds": round(run.model_seconds, 1)},
    }
