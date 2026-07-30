"""FastAPI API for job discovery, CV generation, and application automation."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from pypdf import PdfReader
from starlette.concurrency import run_in_threadpool

from apply_agent import application_manager
from availability import probe_application_urls
from batch import MAX_BATCH_SIZE, run_batch_search
from cv_builder import build_cv_document, cv_readiness, render_cv_pdf
from document_store import (
    get_active_document,
    get_cv_metadata,
    get_cv_pdf_path,
    get_cv_text,
    set_active_document,
    store_cv,
)
from drafting import draft_application
from graph import graph
from model_provider import ModelProviderError, list_models, runtime_models
from qualification import qualify_match
from scrape_jobs import CaptchaBlockedError
from tailored_cv import build_tailored_cv


app = FastAPI(title="Jobflow API", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _extract_cv_text(name: str, content: bytes) -> str:
    if name.lower().endswith(".pdf"):
        reader = PdfReader(BytesIO(content))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    return content.decode("utf-8", errors="replace")


def _split_terms(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _job_view(match: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    job = match["job"]
    qualification = qualify_match(match, profile)
    return {
        "id": job["id"],
        "title": job["title"],
        "company": job["company"],
        "location": job["location"],
        "description": job["description"],
        "url": job["url"],
        "source": job["source"],
        "opportunity_type": job.get("opportunity_type", "job"),
        "score": match["match_score"],
        "score_breakdown": match.get("score_breakdown", {}),
        "match_reasons": match.get("match_reasons", []),
        "keywords": match["matched_keywords"],
        "status": qualification["status"],
        "rule_reasons": qualification["reasons"],
        "priority": qualification["priority"],
        "direct_listing": qualification["direct_listing"],
    }


def _result_view(result: dict[str, Any], limit: int = 10) -> dict[str, Any]:
    profile = result.get("profile", {})
    qualified = [_job_view(match, profile) for match in result.get("matched_jobs", [])]
    availability = probe_application_urls(
        job["url"] for job in qualified
        if job["direct_listing"] and job["status"] != "excluded"
    )
    for job in qualified:
        if availability.get(job["url"]) is False:
            job["status"] = "excluded"
            job["priority"] = 0
            job["rule_reasons"] = ["The employer is no longer accepting applications for this role."]
    active_jobs = [job for job in qualified if job["status"] != "excluded"]
    jobs = sorted(active_jobs, key=lambda item: (item["priority"], item["score"]), reverse=True)
    return {
        "profile": profile,
        "document_id": result.get("document_id"),
        "queries": result.get("search_queries", []),
        "discovered": len(result.get("raw_jobs", [])),
        "matched": len(result.get("matched_jobs", [])),
        "qualified": sum(job["status"] == "ready" for job in active_jobs),
        "review": sum(job["status"] == "review" for job in active_jobs),
        "excluded": sum(job["status"] == "excluded" for job in qualified),
        "jobs": jobs[:limit],
    }


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "version": app.version, "model": runtime_models.public()}


@app.get("/api/documents/active")
def active_cv_document() -> dict[str, Any]:
    active = get_active_document()
    return {"document": active}


class ModelSettingsRequest(BaseModel):
    provider: str
    base_url: str = ""
    model: str = ""
    api_key: str | None = None


class ModelRefreshRequest(BaseModel):
    provider: str
    base_url: str = ""
    api_key: str | None = None


@app.get("/api/model-settings")
def get_model_settings() -> dict[str, Any]:
    return runtime_models.public()


@app.put("/api/model-settings")
def update_model_settings(request: ModelSettingsRequest) -> dict[str, Any]:
    try:
        return runtime_models.update(request.provider, request.base_url, request.model, request.api_key)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/api/model-settings/models")
async def refresh_models(request: ModelRefreshRequest) -> dict[str, Any]:
    try:
        models = await run_in_threadpool(list_models, request.provider, request.base_url, request.api_key)
        return {"models": models}
    except ModelProviderError as exc:
        raise HTTPException(503, str(exc)) from exc


@app.post("/api/search")
async def search(
    cv: UploadFile | None = File(default=None),
    cv_document_id: str = Form(default=""),
    user_id: str = Form(default="my-profile"),
    location: str = Form(default="Cairo"),
    refresh_profile: bool = Form(default=True),
    live_browser: bool = Form(default=False),
    target_roles: str = Form(default=""),
    excluded_title_terms: str = Form(default=""),
    limit: int = Form(default=10),
) -> dict[str, Any]:
    document_id = cv_document_id.strip()
    if document_id:
        try:
            text = get_cv_text(document_id)
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
    elif cv:
        name = cv.filename or "cv.txt"
        content = await cv.read()
        text = _extract_cv_text(name, content)
        if not text.strip():
            raise HTTPException(422, "No readable text was found in this CV.")
        pdf_bytes = content if name.lower().endswith(".pdf") else render_cv_pdf(text)
        document_id = store_cv(text, pdf_bytes, source_name=name)
    else:
        raise HTTPException(400, "Upload a PDF/TXT CV or select a generated CV.")

    try:
        set_active_document(document_id)
        result = await run_in_threadpool(
            graph.invoke,
            {
                "user_id": user_id,
                "cv_text": text,
                "document_id": document_id,
                "refresh_profile": refresh_profile,
                "location_override": location,
                "live_browser": live_browser,
                "target_roles": _split_terms(target_roles),
                "excluded_title_terms": _split_terms(excluded_title_terms),
            },
            {"configurable": {"thread_id": user_id}},
        )
        return _result_view(result, min(max(limit, 1), 10))
    except CaptchaBlockedError as exc:
        raise HTTPException(429, str(exc)) from exc
    except ModelProviderError as exc:
        raise HTTPException(503, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, f"Search failed: {exc}") from exc


@app.post("/api/batch-search")
async def batch_search(
    cvs: list[UploadFile] = File(...),
    location: str = Form(default="Cairo"),
    target_roles: str = Form(default=""),
    excluded_title_terms: str = Form(default=""),
    limit: int = Form(default=10),
) -> dict[str, Any]:
    if not cvs or len(cvs) > MAX_BATCH_SIZE:
        raise HTTPException(422, f"Upload between 1 and {MAX_BATCH_SIZE} CVs.")
    candidates = []
    for cv in cvs:
        name = cv.filename or "candidate.txt"
        text = _extract_cv_text(name, await cv.read())
        if not text.strip():
            raise HTTPException(422, f"No readable text was found in {name}.")
        candidates.append((name, text))
    try:
        batch_results = await run_in_threadpool(
            run_batch_search,
            candidates,
            location,
            MAX_BATCH_SIZE,
            _split_terms(target_roles),
            _split_terms(excluded_title_terms),
        )
        return {
            "results": [
                {
                    "candidate": item["candidate"],
                    "error": item["error"],
                    "data": _result_view(item["result"], min(max(limit, 1), 10)) if item["result"] else None,
                }
                for item in batch_results
            ]
        }
    except Exception as exc:
        raise HTTPException(500, f"Batch search failed: {exc}") from exc


class ApplicationDraftRequest(BaseModel):
    title: str
    company: str
    keywords: list[str] = Field(default_factory=list)
    profile: dict[str, Any] = Field(default_factory=dict)


@app.post("/api/application-draft")
async def application_draft(request: ApplicationDraftRequest) -> dict[str, str]:
    try:
        message = await run_in_threadpool(
            draft_application, request.profile, request.title, request.company, request.keywords
        )
        return {"status": "review_required", "message": message}
    except Exception as exc:
        raise HTTPException(500, f"Could not prepare application: {exc}") from exc


class CVBuilderRequest(BaseModel):
    answers: dict[str, str] = Field(default_factory=dict)


@app.post("/api/cv/readiness")
def check_cv_readiness(request: CVBuilderRequest) -> dict[str, Any]:
    return cv_readiness(request.answers)


@app.post("/api/build-cv")
async def create_cv(request: CVBuilderRequest) -> dict[str, Any]:
    try:
        result = await run_in_threadpool(build_cv_document, request.answers)
        set_active_document(result["document_id"])
        return result
    except ValueError as exc:
        detail = getattr(exc, "readiness", None)
        raise HTTPException(422, {"message": str(exc), "readiness": detail}) from exc
    except ModelProviderError as exc:
        raise HTTPException(503, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, f"Could not build the CV: {exc}") from exc


@app.get("/api/documents/{document_id}.pdf")
def download_cv(document_id: str) -> FileResponse:
    try:
        path = get_cv_pdf_path(document_id)
        metadata = get_cv_metadata(document_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=str(metadata.get("source_name") or "jobflow-ats-cv.pdf"),
    )


class TailoredCVRequest(BaseModel):
    document_id: str
    title: str
    company: str = ""
    description: str = ""
    url: str = ""
    keywords: list[str] = Field(default_factory=list)


@app.post("/api/tailored-cv")
async def create_tailored_cv(request: TailoredCVRequest) -> dict[str, Any]:
    try:
        return await run_in_threadpool(
            build_tailored_cv,
            request.document_id,
            {
                "title": request.title,
                "company": request.company,
                "description": request.description,
                "url": request.url,
                "keywords": request.keywords,
            },
        )
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, f"Could not tailor the CV: {exc}") from exc


class ApplicationSessionRequest(BaseModel):
    url: str
    document_id: str
    profile: dict[str, Any] = Field(default_factory=dict)
    auto_submit: bool = False


@app.post("/api/application-sessions")
def create_application_session(request: ApplicationSessionRequest) -> dict[str, Any]:
    try:
        return application_manager.start(
            request.url,
            request.document_id,
            request.profile,
            auto_submit=request.auto_submit,
            visible=True,
        )
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/api/application-sessions/{session_id}")
def application_session_status(session_id: str) -> dict[str, Any]:
    try:
        return application_manager.get(session_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


class ApplicationCommandRequest(BaseModel):
    command: str
    values: dict[str, str] = Field(default_factory=dict)


@app.post("/api/application-sessions/{session_id}/commands")
def application_session_command(session_id: str, request: ApplicationCommandRequest) -> dict[str, Any]:
    try:
        return application_manager.command(session_id, request.command, request.values)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


_FRONTEND_DIST = Path(__file__).resolve().parents[1] / "frontend" / "dist"
if _FRONTEND_DIST.is_dir():
    # API routes are registered first; the SPA handles every remaining route.
    app.mount("/", StaticFiles(directory=_FRONTEND_DIST, html=True), name="frontend")
