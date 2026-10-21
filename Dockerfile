# Single-container demo: web UI + agent, runbooks searched in memory (no database).
# Build for Nebius (amd64): docker build --platform linux/amd64 -t ai-workbench .
FROM python:3.14-slim

COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /usr/local/bin/uv
WORKDIR /app

# Dependencies first so code changes don't reinstall them.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --no-install-project

COPY src ./src
COPY runbooks ./runbooks
COPY samples ./samples
RUN uv sync --locked --no-dev

# Public demo defaults. Secrets (NEBIUS_API_KEY, DEMO_PASSWORD) come from the platform, never the image.
ENV HOST=0.0.0.0 \
    PORT=8000 \
    KB_BACKEND=memory \
    ALLOWED_MODELS='["nvidia/nemotron-3-super-120b-a12b"]' \
    PYTHONUNBUFFERED=1

# The app runs from /app/.venv; the base image's pip, setuptools and bundled installers are unused
# and carry vendored copies of certifi/urllib3 that Trivy flags, so drop them.
RUN python -m pip uninstall -y pip setuptools wheel 2>/dev/null; \
    rm -rf /usr/local/lib/python3.*/ensurepip /usr/local/bin/pip*; \
    useradd --create-home app && chown -R app /app
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"
CMD ["/app/.venv/bin/ai-workbench"]
