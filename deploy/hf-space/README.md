---
title: AI Workbench
emoji: 🛠️
colorFrom: green
colorTo: gray
sdk: docker
app_port: 8000
pinned: false
license: apache-2.0
short_description: Log triage agent on NVIDIA Nemotron via Nebius Token Factory
---

# AI Workbench

Paste a failed Ansible, Terraform or CI log (or pick a sample). The agent retrieves matching runbooks, checks a
**simulated host** with read-only commands, proposes a fix and waits for you to approve or reject it before
anything runs, then verifies and writes a report.

- Model: NVIDIA Nemotron 3 Super, called at runtime on **Nebius Token Factory**
- Embeddings: Qwen3-Embedding-8B on Nebius Token Factory
- This Space only hosts the web app. It runs the container image built and tested by CI in the source repo.
- Commands run against a simulated host; nothing real is touched.

Source code, tests and docs: https://github.com/J-sterling/ai-workbench

The demo asks for a password (see the hackathon testing instructions). The Space sleeps after 48 hours
without visitors; the first visit after that takes about a minute to wake it.
