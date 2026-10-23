import os
import threading
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ai_workbench import agent, guard, kb, usage, websearch
from ai_workbench.config import settings
from ai_workbench.sandbox import SAMPLES
from ai_workbench.triage import triage

STATIC = Path(__file__).parent / "static"

app = FastAPI(title="AI Workbench")
# Every route except /health sits behind the optional demo password.
protected = APIRouter(dependencies=[Depends(guard.password)])

# What the UI shows for each sample. Order is the demo order.
SAMPLE_TITLES = {
    "01-garage-down": "Terraform state backend is down (connection refused on :3900)",
    "02-ci-checkout-dns": "CI job can't resolve the Gitea host during checkout",
    "03-blank-s3-creds": "Terraform gets 403 InvalidAccessKeyId from the S3 backend",
}

_decide_lock = threading.Lock()


class TriageRequest(BaseModel):
    log: str
    use_kb: bool = True
    model: str | None = None


class AgentRequest(BaseModel):
    log: str | None = None
    sample: str | None = None  # a samples/ file name without .log; also picks its sandbox
    model: str | None = None
    use_kb: bool = True


class Decision(BaseModel):
    approve: bool
    note: str = ""


@protected.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@protected.get("/usage", include_in_schema=False)
def usage_page() -> FileResponse:
    return FileResponse(STATIC / "usage.html")


@protected.get("/usage/data")
def usage_data() -> dict:
    """Token counts per call, today and per minute. Holds no prompt or log text."""
    return usage.summary()


@protected.get("/config")
def config() -> dict:
    return {
        "models": settings.allowed_models,
        "default_model": settings.model_smart,
        "max_log_bytes": settings.max_log_bytes,
        "daily_run_limit": settings.daily_run_limit,
        "web_search": websearch.enabled(),
    }


@protected.get("/samples")
def samples() -> list[dict]:
    names = sorted(p.stem for p in SAMPLES.glob("*.log"))
    return [{"name": n, "title": SAMPLE_TITLES.get(n, n), "log": (SAMPLES / f"{n}.log").read_text()} for n in names]


@protected.get("/kb/search")
def kb_search(q: str, k: int = 3) -> list[dict]:
    guard.check_log(q)
    guard.spend_run()  # embeds the query, which costs a Token Factory call
    return [{"source": h.source, "title": h.title, "score": round(h.score, 3)} for h in kb.search(q, min(k, 5))]


@protected.post("/triage")
def triage_log(req: TriageRequest) -> dict:
    guard.check_log(req.log)
    guard.check_model(req.model)
    guard.spend_run()
    t = triage(req.log, use_kb=req.use_kb, model=req.model)
    return {
        "answer": t.answer,
        "model": t.model,
        "runbooks": [{"source": h.source, "title": h.title, "score": round(h.score, 3)} for h in t.runbooks],
        "usage": {"prompt": t.prompt_tokens, "completion": t.completion_tokens},
    }


@protected.post("/agent/runs")
def start_run(req: AgentRequest, tasks: BackgroundTasks) -> dict:
    """Returns at once; the model works in the background. Poll GET /agent/runs/{id}."""
    log = req.log
    if req.sample:
        path = SAMPLES / f"{req.sample}.log"
        if path.parent != SAMPLES or not path.exists():
            raise HTTPException(404, f"no sample named {req.sample!r}")
        log = log or path.read_text()
    if not log or not log.strip():
        raise HTTPException(422, "Send a log or pick a sample.")
    guard.check_log(log)
    guard.check_model(req.model)
    guard.spend_run()
    run = agent.new_run(log, sample=req.sample, model=req.model, use_kb=req.use_kb)
    tasks.add_task(agent.safely, agent.begin, run)
    return agent.view(run)


@protected.get("/agent/runs/{run_id}")
def get_run(run_id: str) -> dict:
    return agent.view(_run(run_id))


@protected.post("/agent/runs/{run_id}/decision")
def decide(run_id: str, d: Decision, tasks: BackgroundTasks) -> dict:
    """Records the decision at once; verification and the report run in the background."""
    run = _run(run_id)
    with _decide_lock:
        if run.status != "awaiting_approval":
            raise HTTPException(409, f"This run is {run.status.replace('_', ' ')}, not waiting for a decision.")
        agent.record_decision(run, d.approve, d.note[:500])
    tasks.add_task(agent.safely, agent.advance, run)
    return agent.view(run)


def _run(run_id: str) -> agent.Run:
    if run_id not in agent.RUNS:
        raise HTTPException(404, "This run no longer exists. Start a new one.")
    return agent.RUNS[run_id]


# /health stays outside the password so a hosting platform can probe it.
@app.get("/health")
def health() -> dict:
    # version is the git commit the image was built from (set by CI), so a promote can be verified.
    return {"status": "ok", "version": os.environ.get("APP_VERSION", "dev")}


app.include_router(protected)
