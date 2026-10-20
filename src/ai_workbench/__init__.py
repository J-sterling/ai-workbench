def main() -> None:
    import sys

    import uvicorn

    from ai_workbench.config import settings

    # One worker: runs and the daily cap live in this process's memory.
    # Pass --reload for local development.
    uvicorn.run("ai_workbench.api:app", host=settings.host, port=settings.port, reload="--reload" in sys.argv, workers=1)
