"""Local FastAPI API for job discovery and reviewed application handoff."""

from __future__ import annotations

from io import BytesIO
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from pypdf import PdfReader
from starlette.concurrency import run_in_threadpool

from batch import MAX_BATCH_SIZE, run_batch_search
from apply_agent import start_visible_application
from cv_builder import build_cv
from drafting import draft_application
from graph import graph
from qualification import qualify_match
from scrape_jobs import CaptchaBlockedError


app = FastAPI(title="Job Match API", version="1.0.0")
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
        "score": match["match_score"],
        "keywords": match["matched_keywords"],
        "status": qualification["status"],
        "rule_reasons": qualification["reasons"],
        "priority": qualification["priority"],
        "direct_listing": qualification["direct_listing"],
    }


def _result_view(result: dict[str, Any], limit: int = 10) -> dict[str, Any]:
    profile = result.get("profile", {})
    qualified = [_job_view(match, profile) for match in result.get("matched_jobs", [])]
    active_jobs = [job for job in qualified if job["status"] != "excluded"]
    jobs = sorted(active_jobs, key=lambda item: (item["priority"], item["score"]), reverse=True)
    return {
        "profile": profile,
        "queries": result.get("search_queries", []),
        "discovered": len(result.get("raw_jobs", [])),
        "matched": len(result.get("matched_jobs", [])),
        "qualified": sum(job["status"] == "ready" for job in active_jobs),
        "review": sum(job["status"] == "review" for job in active_jobs),
        "excluded": sum(job["status"] == "excluded" for job in qualified),
        "jobs": jobs[:limit],
    }


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "model": "gemini"}


@app.post("/api/search")
async def search(
    cv: UploadFile | None = File(default=None),
    user_id: str = Form(default="my-profile"),
    location: str = Form(default="Cairo"),
    refresh_profile: bool = Form(default=True),
    live_browser: bool = Form(default=False),
    target_roles: str = Form(default=""),
    excluded_title_terms: str = Form(default=""),
    limit: int = Form(default=10),
) -> dict[str, Any]:
    if not cv:
        raise HTTPException(400, "Upload a PDF or TXT CV before starting a new search.")
    text = _extract_cv_text(cv.filename or "cv.txt", await cv.read())
    if not text.strip():
        raise HTTPException(422, "No readable text was found in this CV.")
    try:
        result = await run_in_threadpool(
            graph.invoke,
            {"user_id": user_id, "cv_text": text, "refresh_profile": refresh_profile, "location_override": location, "live_browser": live_browser, "target_roles": _split_terms(target_roles), "excluded_title_terms": _split_terms(excluded_title_terms)},
            {"configurable": {"thread_id": user_id}},
        )
        return _result_view(result, min(max(limit, 1), 10))
    except CaptchaBlockedError as exc:
        raise HTTPException(429, str(exc)) from exc
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
        batch_results = await run_in_threadpool(run_batch_search, candidates, location, MAX_BATCH_SIZE, _split_terms(target_roles), _split_terms(excluded_title_terms))
        return {
            "results": [
                {"candidate": item["candidate"], "error": item["error"], "data": _result_view(item["result"], min(max(limit, 1), 10)) if item["result"] else None}
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
    """Prepare text for a human-reviewed application; never submits externally."""
    try:
        message = await run_in_threadpool(draft_application, request.profile, request.title, request.company, request.keywords)
        return {"status": "review_required", "message": message}
    except Exception as exc:
        raise HTTPException(500, f"Could not prepare application: {exc}") from exc


class CVBuilderRequest(BaseModel):
    answers: dict[str, str] = Field(default_factory=dict)


@app.post("/api/build-cv")
async def create_cv(request: CVBuilderRequest) -> dict[str, str]:
    """Build a plain-text CV using only the facts supplied by the person."""
    try:
        return {"cv_text": await run_in_threadpool(build_cv, request.answers)}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, f"Could not build the CV: {exc}") from exc


class ApplicationSessionRequest(BaseModel):
    url: str


@app.post("/api/application-session")
def application_session(request: ApplicationSessionRequest) -> dict[str, str]:
    """Open a visible Playwright session; no personal data is filled or sent."""
    if not request.url.startswith(("https://", "http://")):
        raise HTTPException(422, "The application URL must be a valid web URL.")
    start_visible_application(request.url)
    return {"status": "opened", "message": "A visible Playwright browser has opened the source page for your review."}
