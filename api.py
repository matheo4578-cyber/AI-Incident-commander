from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi import Path as ApiPath
from fastapi.responses import FileResponse

from incident_commander.models import IncidentInput, IncidentReport, IncidentRequest
from incident_commander.storage import ReportRepository, repository_from_env
from incident_commander.workflow import IncidentWorkflow, build_workflow

STATIC_DIR = Path(__file__).parent / "static"


def create_app(
    llm_mode: str | None = None,
    workflow: IncidentWorkflow | None = None,
    repository: ReportRepository | None = None,
) -> FastAPI:
    app = FastAPI(
        title="AI Incident Commander",
        version="0.1.0",
        description="Read-only, evidence-based cloud incident investigation",
    )
    mode: str = llm_mode if llm_mode is not None else os.environ.get("LLM_MODE", "deterministic")
    active_workflow = workflow or build_workflow(
        llm_mode=mode,
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
    )
    reports = repository or repository_from_env()

    @app.get("/", include_in_schema=False)
    def dashboard() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "incident-commander"}

    @app.post("/api/incidents/analyze", response_model=IncidentReport)
    def analyze(request: IncidentRequest) -> IncidentReport:
        incident = IncidentInput(**request.model_dump())
        report = active_workflow.analyze(incident)
        reports.save(report)
        return report

    @app.get("/api/incidents/{incident_id}", response_model=IncidentReport)
    def get_report(
        incident_id: Annotated[str, ApiPath(pattern=r"^inc-[a-zA-Z0-9-]{3,64}$")],
    ) -> IncidentReport:
        report = reports.get(incident_id)
        if report is None:
            raise HTTPException(status_code=404, detail="Incident report not found")
        return report

    return app


app = create_app()


def run() -> None:
    uvicorn.run(
        "incident_commander.api:app",
        host=os.getenv("HOST", "0.0.0.0"),  # noqa: S104
        port=int(os.getenv("PORT", "8080")),
    )
