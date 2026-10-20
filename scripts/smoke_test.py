"""Check the Token Factory key, list NVIDIA models, and send one chat request.

Run: uv run scripts/smoke_test.py
"""

import sys

from ai_workbench.config import settings
from ai_workbench.llm import chat, client


def main() -> int:
    models = sorted(m.id for m in client.models.list() if m.id.startswith("nvidia/"))
    print(f"{len(models)} NVIDIA models available:")
    for m in models:
        print(f"  {m}")

    if settings.model_smart not in models:
        print(f"\nWARNING: MODEL_SMART={settings.model_smart} is not in the list.")

    raw = client.chat.completions.create(
        model=settings.model_smart,
        messages=[{"role": "user", "content": "Reply with exactly: smoke test ok"}],
        max_tokens=256,
    )
    msg = raw.choices[0].message
    print(f"\nModel:   {raw.model}")
    print(f"content: {msg.content!r}")
    if not msg.content:
        print("content is EMPTY - full message object:")
        print(msg.model_dump_json(indent=2))
    print(f"Wrapper: {chat([{'role': 'user', 'content': 'Say hi in 3 words'}]).text!r}")
    print(f"Usage:   {raw.usage}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
