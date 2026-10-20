"""Thin wrapper around the OpenAI-compatible Token Factory API."""

import time
from dataclasses import dataclass

from openai import OpenAI

from ai_workbench import usage
from ai_workbench.config import settings

client = OpenAI(
    base_url=settings.nebius_base_url,
    api_key=settings.nebius_api_key.get_secret_value(),
)


@dataclass
class Reply:
    text: str
    model: str
    prompt_tokens: int
    completion_tokens: int


def text_of(msg) -> str:
    # Some Nemotron deployments return the answer in reasoning_content and leave
    # content empty, so fall back to it rather than showing a blank reply.
    return (msg.content or getattr(msg, "reasoning_content", None) or "").strip()


def _record(kind: str, model: str, resp, t0: float, tag: str) -> None:
    u = resp.usage
    usage.record(kind, model, u.prompt_tokens if u else 0, getattr(u, "completion_tokens", 0) if u else 0,
                 time.monotonic() - t0, tag)


def chat(messages: list[dict], model: str | None = None, max_tokens: int = 1024, tag: str = "") -> Reply:
    model = model or settings.model_fast
    t0 = time.monotonic()
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
    )
    _record("chat", model, resp, t0, tag)
    usage = resp.usage
    return Reply(
        text=text_of(resp.choices[0].message),
        model=resp.model,
        prompt_tokens=usage.prompt_tokens if usage else 0,
        completion_tokens=usage.completion_tokens if usage else 0,
    )


def chat_tools(messages: list[dict], tools: list[dict], model: str | None = None, max_tokens: int = 1024,
               tag: str = ""):
    """One tool-calling turn. Returns the raw assistant message and the usage."""
    model = model or settings.model_smart
    t0 = time.monotonic()
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        tools=tools,
        max_tokens=max_tokens,
    )
    _record("agent", model, resp, t0, tag)
    return resp.choices[0].message, resp.usage
