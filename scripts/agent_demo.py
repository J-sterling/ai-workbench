"""Run the triage agent on a sample log in the terminal, approving fixes by hand.

Run: uv run scripts/agent_demo.py 01-garage-down
"""

import sys
import textwrap

from ai_workbench import agent
from ai_workbench.sandbox import SAMPLES

BOLD, DIM, RED, GREEN, YELLOW, RESET = "\033[1m", "\033[2m", "\033[31m", "\033[32m", "\033[33m", "\033[0m"


def indent(text: str, width: int = 12) -> str:
    lines = text.strip().splitlines()
    shown = lines[:width] + ([f"... ({len(lines) - width} more lines)"] if len(lines) > width else [])
    return textwrap.indent("\n".join(shown), "    ")


def show(step: dict) -> None:
    kind = step["kind"]
    if kind == "runbooks":
        found = ", ".join(f"{m['source']} ({m['score']})" for m in step["matched"]) or "none"
        print(f"{BOLD}Runbooks retrieved:{RESET} {found}\n")
    elif kind == "search":
        print(f"{BOLD}Search:{RESET} {step['query']} -> {', '.join(step['matched']) or 'none'}\n")
    elif kind == "diagnostic":
        tag = f" {RED}[refused]{RESET}" if step.get("refused") else ""
        why = f"  {DIM}# {step['why']}{RESET}" if step.get("why") else ""
        print(f"{YELLOW}$ {step['command']}{RESET}{tag}{why}\n{DIM}{indent(step['output'])}{RESET}\n")
    elif kind == "proposal":
        warn = f"  {RED}{BOLD}DESTRUCTIVE{RESET}" if step["destructive"] else ""
        print(f"{BOLD}Proposed fix{RESET}{warn}")
        for c in step["commands"]:
            print(f"    {c}")
        print(f"  reason: {step['reason']}\n  risk:   {step['risk']}\n")
    elif kind == "decision":
        verdict = f"{GREEN}approved{RESET}" if step["approved"] else f"{RED}rejected{RESET}"
        print(f"Operator {verdict}\n{DIM}{indent(step['output'])}{RESET}\n")
    elif kind == "answer":
        print(f"{BOLD}Report{RESET}\n{step['text']}\n")


def main() -> int:
    name = sys.argv[1] if len(sys.argv) > 1 else "01-garage-down"
    log = (SAMPLES / f"{name}.log").read_text()
    print(f"{BOLD}Log:{RESET} samples/{name}.log\n")
    run = agent.start(log, sample=name, on_step=show)
    while run.status == "awaiting_approval":
        approve = input(f"{BOLD}Approve this fix? [y/N]{RESET} ").strip().lower() == "y"
        note = "" if approve else input("Note for the agent (optional): ").strip()
        print()
        run = agent.decide(run, approve, note, on_step=show)
    print(f"{DIM}status={run.status}  turns={run.turns}  tokens: {run.prompt_tokens} in / {run.completion_tokens} out{RESET}")
    return 0 if run.status == "done" else 1


if __name__ == "__main__":
    sys.exit(main())
