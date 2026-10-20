"""Thin wrapper around the OpenAI-compatible Token Factory API."""

from dataclasses import dataclass

from openai import OpenAI

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


def chat(messages: list[dict], model: str | None = None, max_tokens: int = 1024) -> Reply:
    resp = client.chat.completions.create(
        model=model or settings.model_fast,
        messages=messages,
        max_tokens=max_tokens,
    )
    usage = resp.usage
    return Reply(
        text=text_of(resp.choices[0].message),
        model=resp.model,
        prompt_tokens=usage.prompt_tokens if usage else 0,
        completion_tokens=usage.completion_tokens if usage else 0,
    )


def chat_tools(messages: list[dict], tools: list[dict], model: str | None = None, max_tokens: int = 1024):
    """One tool-calling turn. Returns the raw assistant message and the usage."""
    resp = client.chat.completions.create(
        model=model or settings.model_smart,
        messages=messages,
        tools=tools,
        max_tokens=max_tokens,
    )
    return resp.choices[0].message, resp.usage
