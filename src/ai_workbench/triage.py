"""Log triage: retrieve matching runbooks, then ask Nemotron for a diagnosis."""

from dataclasses import dataclass, field

from ai_workbench import kb, llm
from ai_workbench.config import settings

SYSTEM = """You are an infrastructure log triage assistant.
Given a failed run's log, answer with:
1. Error group(s)
2. Most likely root cause
3. Fix, as concrete commands
4. Which step needs human approval, and why

When a runbook below matches the log, base your answer on it and name it.
When none matches, say so and reason from the log alone. Be concise."""

@dataclass
class Triage:
    answer: str
    model: str
    runbooks: list[kb.Hit] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0


def triage(log: str, use_kb: bool = True, model: str | None = None) -> Triage:
    hits = kb.relevant(kb.log_query(log)) if use_kb else []
    context = "\n\n---\n\n".join(f"Runbook: {h.source}\n\n{h.content}" for h in hits)
    user = f"Runbooks:\n\n{context or '(none matched)'}\n\nLog:\n\n{log}"
    reply = llm.chat(
        [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
        model=model or settings.model_smart,
        max_tokens=2048,
    )
    return Triage(reply.text, reply.model, hits, reply.prompt_tokens, reply.completion_tokens)
