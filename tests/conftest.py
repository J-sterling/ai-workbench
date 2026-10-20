import json
import os

# config.Settings requires a key and llm.py builds its client at import time.
# Tests never call the API, so a placeholder is enough.
os.environ.setdefault("NEBIUS_API_KEY", "test-placeholder")

import pytest  # noqa: E402
from openai.types.chat import ChatCompletionMessage, ChatCompletionMessageToolCall  # noqa: E402

from ai_workbench import agent, kb  # noqa: E402

@pytest.fixture(autouse=True)
def _usage_file(tmp_path, monkeypatch):
    """Keep tests from writing to the real var/usage.jsonl."""
    from ai_workbench.config import settings
    monkeypatch.setattr(settings, "usage_file", str(tmp_path / "usage.jsonl"))


# Tool names offered on each scripted model call, newest last.
TOOLS_SEEN: list[list[str]] = []


class Usage:
    prompt_tokens = 100
    completion_tokens = 10


def call(name: str, **args) -> ChatCompletionMessageToolCall:
    call.n = getattr(call, "n", 0) + 1
    return ChatCompletionMessageToolCall(
        id=f"call_{call.n}", type="function", function={"name": name, "arguments": json.dumps(args)}
    )


def turn(*calls, content: str = "") -> ChatCompletionMessage:
    return ChatCompletionMessage(role="assistant", content=content, tool_calls=list(calls) or None)


@pytest.fixture
def model(monkeypatch):
    """Replays scripted assistant turns and records what the agent sent back."""
    script: list[ChatCompletionMessage] = []
    sent: list[list[dict]] = []

    def chat_tools(messages, tools, model=None, max_tokens=1024, tag=""):
        sent.append([dict(m) for m in messages])
        TOOLS_SEEN.append([t["function"]["name"] for t in tools])
        return script.pop(0), Usage()

    monkeypatch.setattr(agent.llm, "chat_tools", chat_tools)
    monkeypatch.setattr(agent.kb, "relevant", lambda q, k=3: [kb.Hit("runbooks/s3-backend-garage-down.md", "Garage down", "...", 0.8)])
    return script, sent


