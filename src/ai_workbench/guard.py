"""Limits for the public demo: an optional password, a daily run cap and a log size cap.

The demo stays up until judging ends and every run spends Token Factory credits,
so anything that calls a model goes through these checks.
"""

import secrets
import threading
from datetime import UTC, datetime

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from ai_workbench.config import settings

_basic = HTTPBasic(auto_error=False, realm="AI Workbench demo")
_lock = threading.Lock()
_day = ""
_count = 0


def password(creds: HTTPBasicCredentials | None = Depends(_basic)) -> None:
    """Any username; the password must match DEMO_PASSWORD when one is set."""
    expected = settings.demo_password.get_secret_value() if settings.demo_password else ""
    if not expected:
        return
    given = creds.password if creds else ""
    if not secrets.compare_digest(given.encode(), expected.encode()):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "This demo needs the password from the testing instructions.",
            headers={"WWW-Authenticate": 'Basic realm="AI Workbench demo"'},
        )


def spend_run() -> None:
    """Count one model-calling request against today's limit (UTC)."""
    global _day, _count
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    with _lock:
        if today != _day:
            _day, _count = today, 0
        if _count >= settings.daily_run_limit:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                f"The demo has reached today's limit of {settings.daily_run_limit} runs. It resets at 00:00 UTC.",
            )
        _count += 1


def check_log(log: str) -> None:
    if len(log.encode()) > settings.max_log_bytes:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            f"Logs are limited to {settings.max_log_bytes // 1000} KB. Paste the failing part, around the error lines.",
        )


def check_model(model: str | None) -> None:
    if model and model not in settings.allowed_models:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Model not available in this demo. Choose one of: {', '.join(settings.allowed_models)}",
        )


def reset() -> None:
    """For tests."""
    global _day, _count
    with _lock:
        _day, _count = "", 0
