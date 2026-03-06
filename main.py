from __future__ import annotations
from datetime import datetime
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.orchestrator import Orchestrator
from app.schemas import AnalysisReport, AnalyzeRequest, JobCreated, JobStatus
from app.storage import Storage

app = FastAPI(title=settings.app_name, version="1.0.0")
cors_origins = [origin.strip() for origin in settings.cors_allow_origins.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_origin_regex=settings.cors_allow_origin_regex or None,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
storage = Storage(settings.database_url)
orchestrator = Orchestrator(settings, storage)
web_dir = Path(__file__).parent / "web"
if web_dir.exists():
    app.mount("/web", StaticFiles(directory=str(web_dir)), name="web")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
def home() -> RedirectResponse:
    if not web_dir.exists():
        raise HTTPException(status_code=404, detail="frontend not found")
    return RedirectResponse(url="/web/index.html")


@app.post("/v1/analyze", response_model=JobCreated)
async def analyze(request: AnalyzeRequest, background_tasks: BackgroundTasks) -> JobCreated:
    payload = request.model_dump()
    payload["symbol"] = request.symbol.upper()
    job_id = storage.create_job(symbol=request.symbol, request_payload=payload)

    background_tasks.add_task(orchestrator.run_job, job_id, payload)
    return JobCreated(job_id=job_id, status="queued")


@app.get("/v1/jobs/{job_id}", response_model=JobStatus)
def get_job(job_id: str) -> JobStatus:
    row = storage.get_job(job_id)
    if not row:
        raise HTTPException(status_code=404, detail="job not found")
    updated_at = datetime.fromisoformat(row["updated_at"])
    return JobStatus(
        job_id=row["job_id"],
        status=row["status"],
        progress=row["progress"],
        error=row["error"],
        updated_at=updated_at,
    )


@app.get("/v1/reports/{job_id}", response_model=AnalysisReport)
def get_report(job_id: str) -> AnalysisReport:
    row = storage.get_report(job_id)
    if not row:
        raise HTTPException(status_code=404, detail="report not found")
    return AnalysisReport.model_validate(row)


@app.get("/v1/reports/{job_id}/readable", response_class=PlainTextResponse)
def get_report_readable(job_id: str, lang: str = Query(default="en", pattern="^(en|zh|both)$")) -> str:
    row = storage.get_report(job_id)
    if not row:
        raise HTTPException(status_code=404, detail="report not found")
    report = AnalysisReport.model_validate(row)
    en_text = report.narrative_en or report.narrative or report.thesis
    zh_text = report.narrative_zh or en_text
    if lang == "zh":
        return zh_text
    if lang == "both":
        return f"[English]\n{en_text}\n\n[中文]\n{zh_text}"
    return en_text
