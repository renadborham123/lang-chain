"""FastAPI API for job discovery, CV generation, and application automation."""

from __future__ import annotations

import re
import os
import time
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from copy import deepcopy
from io import BytesIO
from pathlib import Path
from threading import Lock
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from pypdf import PdfReader
from starlette.concurrency import run_in_threadpool

from apply_agent import application_manager
from application_memory import application_answers
from availability import probe_application_urls
from batch import MAX_BATCH_SIZE, run_batch_search
from career_agent import build_acceptance_plan
from career_memory import career_memory
from career_research import discover_growth_opportunities
from cv_builder import build_cv_document, cv_readiness, render_cv_pdf
from cv_enrichment import enrich_cv_document
from document_store import (
    get_active_document,
    get_cv_metadata,
    get_cv_pdf_path,
    get_cv_text,
    set_active_document,
    store_cv,
    update_cv_metadata,
)
from cv_insights import analyze_cv, discuss_insight
from drafting import draft_application
from graph import graph
from job_brief import build_job_brief
from model_provider import ModelProviderError, list_models, runtime_models
from outreach import discover_contacts, draft_outreach
from qualification import qualify_match
from scrape_jobs import CaptchaBlockedError
from tailored_cv import build_tailored_cv
from employment.migration import migrate_legacy_data
from employment.repository import repository
from backend.employment_api import router as employment_router
from backend.auth import current_user_id, router as auth_router
from employment.scheduler import start_scheduler, stop_scheduler
from backend.security import SecurityMiddleware


@asynccontextmanager
async def lifespan(_app: FastAPI):
    migrate_legacy_data(repository)
    start_scheduler()
    try:
        yield
    finally:
        stop_scheduler()


app = FastAPI(title="Wazzefni API", version="4.0.0", lifespan=lifespan)
app.add_middleware(SecurityMiddleware)
cors_origins = [item.strip() for item in os.getenv("JOBFLOW_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if item.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(employment_router)


def _extract_cv_text(name: str, content: bytes) -> str:
    if name.lower().endswith(".pdf"):
        reader = PdfReader(BytesIO(content))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    return content.decode("utf-8", errors="replace")


def _profile_facts_from_cv(text: str) -> dict[str, Any]:
    """Extract only high-confidence contact facts; richer facts come from the search graph."""
    facts: dict[str, Any] = {}
    email = re.search(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", text)
    phone = re.search(r"(?<!\w)(?:\+?\d[\d\s().-]{7,}\d)(?!\w)", text)
    linkedin = re.search(r"(?:https?://)?(?:www\.)?linkedin\.com/[^\s)]+", text, re.I)
    github = re.search(r"(?:https?://)?(?:www\.)?github\.com/[^\s)]+", text, re.I)
    portfolio = re.search(r"https?://(?![^\s]*(?:linkedin|github)\.com)[^\s)]+", text, re.I)
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines() if line.strip()]
    if lines:
        candidate = next((line for line in lines[:8] if not re.fullmatch(r"(?i)page\s+\d+", line)), lines[0])
        if 1 < len(candidate.split()) <= 6 and len(candidate) <= 100 and not re.search(r"@|https?://|\d{4,}", candidate):
            facts["name"] = candidate
    if email:
        facts["email"] = email.group(0)
    if phone:
        facts["phone"] = re.sub(r"\s+", " ", phone.group(0)).strip()
    if linkedin:
        facts["linkedin"] = "https://" + linkedin.group(0).rstrip(".,;") if not linkedin.group(0).lower().startswith("http") else linkedin.group(0).rstrip(".,;")
    if github:
        facts["github"] = "https://" + github.group(0).rstrip(".,;") if not github.group(0).lower().startswith("http") else github.group(0).rstrip(".,;")
    if portfolio:
        facts["portfolio"] = portfolio.group(0).rstrip(".,;")
    return facts


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


def _title_signature(title: str) -> str:
    """Collapse SEO suffixes so the same vacancy from multiple sources appears once."""
    normalized = title.casefold().replace("back-end", "backend").replace("back end", "backend")
    normalized = re.split(
        r"\s+(?:\||with\s+\d+\s*(?:-|–|—|to)|jobs?\s+in|at\s+[^|]+$)",
        normalized,
        maxsplit=1,
    )[0]
    tokens = re.findall(r"[a-z0-9+#.]{2,}", normalized)
    ignored = {"cairo", "egypt", "job", "jobs", "career", "careers"}
    return " ".join(token for token in tokens if token not in ignored)


def _dedupe_jobs(jobs: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    removed = 0
    for job in jobs:
        signature = _title_signature(str(job.get("title") or ""))
        company = re.sub(r"[^a-z0-9]+", " ", str(job.get("company") or "").casefold()).strip()
        if company and company not in {"n a", "na", "unknown"}:
            signature = f"{signature}|{company}"
        if signature and signature in seen:
            removed += 1
            continue
        if signature:
            seen.add(signature)
        output.append(job)
    return output, removed


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
    jobs, duplicate_count = _dedupe_jobs(
        sorted(active_jobs, key=lambda item: (item["priority"], item["score"]), reverse=True)
    )
    return {
        "profile": profile,
        "document_id": result.get("document_id"),
        "queries": result.get("search_queries", []),
        "discovered": len(result.get("raw_jobs", [])),
        "matched": len(result.get("matched_jobs", [])),
        "qualified": sum(job["status"] == "ready" for job in jobs),
        "review": sum(job["status"] == "review" for job in jobs),
        "excluded": sum(job["status"] == "excluded" for job in qualified) + duplicate_count,
        "jobs": jobs[:limit],
    }


_SEARCH_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="jobflow-search")
_SEARCH_JOBS: dict[str, dict[str, Any]] = {}
_SEARCH_JOBS_LOCK = Lock()
_SEARCH_JOB_TTL_SECONDS = 60 * 60


def _source_breakdown(raw_jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    labels = {
        "linkedin_playwright": "LinkedIn public jobs",
        "duckduckgo_playwright": "Public web listings",
        "adzuna": "Adzuna",
    }
    counts = Counter(str(job.get("source") or "other") for job in raw_jobs)
    return [
        {"key": source, "label": labels.get(source, source.replace("_", " ").title()), "count": count}
        for source, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def _search_event(
    job_id: str,
    stage: str,
    progress: int,
    title: str,
    detail: str,
    *,
    meta: dict[str, Any] | None = None,
) -> None:
    with _SEARCH_JOBS_LOCK:
        job = _SEARCH_JOBS[job_id]
        for event in job["events"]:
            if event["status"] == "active":
                event["status"] = "done"
        job["stage"] = stage
        job["progress"] = progress
        job["headline"] = title
        job["detail"] = detail
        job["updated_at"] = time.time()
        job["events"].append(
            {
                "id": f"{stage}-{len(job['events']) + 1}",
                "stage": stage,
                "status": "active",
                "title": title,
                "detail": detail,
                "meta": meta or {},
            }
        )


def _finish_search_job(job_id: str, result: dict[str, Any]) -> None:
    with _SEARCH_JOBS_LOCK:
        job = _SEARCH_JOBS[job_id]
        arabic = job.get("locale") == "ar"
        for event in job["events"]:
            if event["status"] == "active":
                event["status"] = "done"
        qualified = int(result.get("qualified", 0))
        review = int(result.get("review", 0))
        if qualified:
            cv_note = (f"سيرتك الحالية تدعم {qualified} فرص جاهزة للتقديم. لم يتم تغيير أي حقائق في ملفك." if arabic else f"Your current CV supports {qualified} ready match{'es' if qualified != 1 else ''}. No profile facts were changed.")
        elif review:
            cv_note = ("بعض الوظائف تحتاج مراجعة. يمكنني اقتراح تحسينات واقعية للصياغة بعد اختيار وظيفة، ولم يتم تغيير أي شيء تلقائيًا." if arabic else "Some roles need review. I can suggest factual wording improvements after you choose a role; nothing was changed automatically.")
        else:
            cv_note = ("لم يتم تأكيد تطابق قوي بعد. قد تحتاج سيرتك إلى أدلة أوضح أو نطاق بحث أوسع، ولم يتم تغيير أي شيء تلقائيًا." if arabic else "No strong match was confirmed yet. Your CV may need clearer evidence or a broader search, but nothing was changed automatically.")
        job["events"].append(
            {
                "id": f"complete-{len(job['events']) + 1}",
                "stage": "complete",
                "status": "done",
                "title": "اكتمل البحث" if arabic else "Search complete",
                "detail": cv_note,
                "meta": {
                    "qualified": qualified,
                    "review": review,
                    "discovered": int(result.get("discovered", 0)),
                },
            }
        )
        job.update(
            status="completed",
            stage="complete",
            progress=100,
            headline="نتائجك جاهزة" if arabic else "Your results are ready",
            detail=cv_note,
            result=result,
            updated_at=time.time(),
        )


def _fail_search_job(job_id: str, exc: Exception) -> None:
    message = str(exc) or "Search failed."
    with _SEARCH_JOBS_LOCK:
        job = _SEARCH_JOBS[job_id]
        for event in job["events"]:
            if event["status"] == "active":
                event["status"] = "error"
        job.update(
            status="failed",
            stage="failed",
            headline="Search paused",
            detail=message,
            error=message,
            updated_at=time.time(),
        )


def _run_search_job(job_id: str, state: dict[str, Any], limit: int, locale: str = "en") -> None:
    try:
        arabic = locale == "ar"
        with _SEARCH_JOBS_LOCK:
            _SEARCH_JOBS[job_id]["status"] = "running"
        accumulated = dict(state)
        config = {"configurable": {"thread_id": f"{state['user_id']}:{job_id}"}}
        for update in graph.stream(state, config, stream_mode="updates"):
            for node, values in update.items():
                if isinstance(values, dict):
                    accumulated.update(values)
                if node == "extract_profile":
                    profile = accumulated.get("profile", {})
                    skills = len(profile.get("skills", []) or [])
                    titles = len(profile.get("titles", []) or [])
                    if skills or titles:
                        profile_detail = (f"وجدت {skills} إشارات مهارة و{titles} إشارات وظيفية. نستخدم فقط المعلومات الموجودة بالفعل في سيرتك الذاتية." if arabic else f"I found {skills} skill signal{'s' if skills != 1 else ''} and {titles} role signal{'s' if titles != 1 else ''}. Only information already in your CV is being used.")
                    else:
                        profile_detail = ("انتهيت من قراءة نص السيرة المتاح وسأستخدم هذه الأدلة فقط. إذا كانت الصياغة غير كافية لتطابق قوي فسأوضح ذلك." if arabic else "I finished reading the available CV text and will use only that evidence. If the wording is too limited for a strong match, I will flag it clearly.")
                    _search_event(
                        job_id,
                        "planning",
                        22,
                        "نبني خطة بحث من سيرتك الذاتية" if arabic else "Building a search plan from your CV",
                        profile_detail,
                        meta={"skills": skills, "titles": titles},
                    )
                elif node == "generate_queries":
                    queries = accumulated.get("search_queries", []) or []
                    _search_event(
                        job_id,
                        "sources",
                        38,
                        "نبحث في مصادر الوظائف المباشرة" if arabic else "Searching live job sources",
                        (f"نجري {len(queries)} عمليات بحث مركزة عبر المصادر المتاحة، ومنها وظائف LinkedIn العامة عند توفرها." if arabic else f"Running {len(queries)} focused search quer{'ies' if len(queries) != 1 else 'y'} across configured sources, including LinkedIn public jobs when available."),
                        meta={"query_count": len(queries), "queries": queries[:4]},
                    )
                elif node == "search_jobs":
                    raw_jobs = accumulated.get("raw_jobs", []) or []
                    sources = _source_breakdown(raw_jobs)
                    if arabic:
                        source_labels = {"LinkedIn public jobs": "وظائف LinkedIn العامة", "Public web listings": "إعلانات الويب العامة", "Adzuna": "Adzuna"}
                        source_text = " · ".join(f"{source_labels.get(source['label'], source['label'])} {source['count']}" for source in sources)
                        detail = source_text or "لم تُرجع المصادر المتاحة إعلانات حالية، لذلك نكمل بقية الفحوصات."
                    else:
                        source_text = " · ".join(f"{source['label']} {source['count']}" for source in sources)
                        detail = source_text or "The configured sources returned no current listings, so I am continuing with the remaining checks."
                    _search_event(
                        job_id,
                        "screening",
                        60,
                        f"تم العثور على {len(raw_jobs)} وظيفة حالية" if arabic else f"Found {len(raw_jobs)} current role{'s' if len(raw_jobs) != 1 else ''}",
                        detail,
                        meta={"found": len(raw_jobs), "sources": sources},
                    )
                elif node == "filter_new_jobs":
                    fresh_jobs = accumulated.get("filtered_jobs", []) or []
                    _search_event(
                        job_id,
                        "matching",
                        72,
                        f"تمت تصفية النتائج إلى {len(fresh_jobs)} إعلانات مناسبة" if arabic else f"Screened down to {len(fresh_jobs)} relevant listing{'s' if len(fresh_jobs) != 1 else ''}",
                        ("نزيل الإعلانات المغلقة والمكررة والتي تم التعامل معها سابقًا والمسميات المستبعدة قبل مطابقة السيرة الذاتية." if arabic else "Closed, repeated, previously handled, and excluded-title listings are removed before CV matching."),
                        meta={"remaining": len(fresh_jobs)},
                    )
                elif node == "match_keywords":
                    matches = accumulated.get("matched_jobs", []) or []
                    _search_event(
                        job_id,
                        "verification",
                        88,
                        f"تمت مطابقة {len(matches)} وظائف مع سيرتك الذاتية" if arabic else f"Matched {len(matches)} role{'s' if len(matches) != 1 else ''} to your CV",
                        ("نتحقق من روابط التقديم ومدى الملاءمة. قد نقترح صياغة أوضح، لكننا لن نضيف خبرات أو مهارات لم تقدمها." if arabic else "I am verifying application links and fit. I may recommend clearer wording, but I will not add experience or skills you did not provide."),
                        meta={"matched": len(matches)},
                    )

        view = _result_view(accumulated, min(max(limit, 1), 10))
        user_id = str(accumulated.get("user_id") or "local-user")
        view["jobs"] = repository.sync_opportunities(view["jobs"], user_id=user_id)
        repository.capture_profile_data(view.get("profile") or {}, source="cv", user_id=user_id, document_id=str(accumulated.get("document_id") or ""))
        remembered = career_memory.values(str(accumulated.get("document_id") or ""), user_id)
        if remembered:
            view["profile"] = {**view.get("profile", {}), "career_facts": remembered}
        _finish_search_job(job_id, view)
    except Exception as exc:
        _fail_search_job(job_id, exc)


def _cleanup_search_jobs() -> None:
    cutoff = time.time() - _SEARCH_JOB_TTL_SECONDS
    with _SEARCH_JOBS_LOCK:
        expired = [job_id for job_id, job in _SEARCH_JOBS.items() if job["updated_at"] < cutoff]
        for job_id in expired:
            del _SEARCH_JOBS[job_id]


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "version": app.version, "model": runtime_models.public()}


@app.get("/api/documents/active")
def active_cv_document(request: Request) -> dict[str, Any]:
    active = get_active_document(current_user_id(request))
    return {"document": active}


@app.get("/api/documents")
def list_cv_documents(request: Request) -> dict[str, Any]:
    return {"items": repository.list_documents(current_user_id(request))}


@app.post("/api/documents")
async def upload_cv_document(request: Request, cv: UploadFile = File(...), locale: str = Form(default="en")) -> dict[str, Any]:
    """Save a replacement CV, make it active, and extract only evidence-backed facts."""
    user_id = current_user_id(request)
    name = cv.filename or "cv.pdf"
    if not name.lower().endswith((".pdf", ".txt")):
        raise HTTPException(422, "Upload a PDF or TXT CV.")
    content = await cv.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(413, "CV files must be 5 MB or smaller.")
    text = _extract_cv_text(name, content)
    if not text.strip():
        raise HTTPException(422, "No readable text was found in this CV.")
    pdf_bytes = content if name.lower().endswith(".pdf") else render_cv_pdf(text)
    document_id = store_cv(text, pdf_bytes, source_name=name, user_id=user_id)
    set_active_document(document_id, user_id)
    repository.capture_profile_data(_profile_facts_from_cv(text), source="cv", user_id=user_id, document_id=document_id)
    try:
        insights = await run_in_threadpool(analyze_cv, text, "ar" if locale == "ar" else "en")
    except (ModelProviderError, ValueError) as exc:
        raise HTTPException(503, f"The CV was saved, but AI review could not finish: {exc}") from exc
    update_cv_metadata(document_id, {"cv_insights": insights}, user_id)
    document = next(item for item in repository.list_documents(user_id) if item["id"] == document_id)
    return {"document": document, "insights": insights, "profile_review_required": True}


@app.post("/api/documents/{document_id}/activate")
def activate_cv_document(document_id: str, request: Request) -> dict[str, Any]:
    user_id = current_user_id(request)
    try:
        active = set_active_document(document_id, user_id)
        text = get_cv_text(document_id, user_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    repository.capture_profile_data(_profile_facts_from_cv(text), source="cv", user_id=user_id, document_id=document_id)
    return {"document": active, "profile_review_required": True}


class CVInsightChallengeRequest(BaseModel):
    insight_id: str
    requested_value: str
    message: str = ""
    history: list[dict[str, str]] = Field(default_factory=list)
    locale: str = "en"


def _require_approved_cv_insights(document_id: str, user_id: str) -> None:
    """Keep search and application workflows behind a reviewed CV understanding."""
    metadata = get_cv_metadata(document_id, user_id)
    review = metadata.get("cv_insights")
    if not isinstance(review, dict) or review.get("review_status") != "approved":
        raise HTTPException(
            409,
            "Review and approve the AI's CV understanding before searching or applying.",
        )


@app.get("/api/documents/{document_id}/insights")
async def cv_document_insights(document_id: str, request: Request, locale: str = "en") -> dict[str, Any]:
    user_id = current_user_id(request)
    try:
        text = get_cv_text(document_id, user_id)
        metadata = get_cv_metadata(document_id, user_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    language = "ar" if locale == "ar" else "en"
    insights = metadata.get("cv_insights")
    if not isinstance(insights, dict) or insights.get("language") != language:
        try:
            insights = await run_in_threadpool(analyze_cv, text, language)
        except (ModelProviderError, ValueError) as exc:
            raise HTTPException(503, f"AI review could not finish: {exc}") from exc
        update_cv_metadata(document_id, {"cv_insights": insights}, user_id)
    return {"document_id": document_id, **insights}


@app.post("/api/documents/{document_id}/insights/approve")
def approve_cv_document_insights(document_id: str, request: Request) -> dict[str, Any]:
    user_id = current_user_id(request)
    metadata = get_cv_metadata(document_id, user_id)
    insights = metadata.get("cv_insights")
    if not isinstance(insights, dict):
        raise HTTPException(409, "Review this CV before approving its insights.")
    approved = {**insights, "review_status": "approved", "approved_at": time.time()}
    update_cv_metadata(document_id, {"cv_insights": approved}, user_id)
    return {"document_id": document_id, **approved}


@app.post("/api/documents/{document_id}/insights/challenge")
async def challenge_cv_document_insight(document_id: str, payload: CVInsightChallengeRequest, request: Request) -> dict[str, Any]:
    user_id = current_user_id(request)
    try:
        text = get_cv_text(document_id, user_id)
        metadata = get_cv_metadata(document_id, user_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    insights = metadata.get("cv_insights")
    if not isinstance(insights, dict):
        raise HTTPException(409, "Review this CV before discussing an insight.")
    insight = next((item for item in insights.get("insights") or [] if item.get("id") == payload.insight_id), None)
    if not insight:
        raise HTTPException(404, "CV insight not found.")
    try:
        result = await run_in_threadpool(
            lambda: discuss_insight(
                cv_text=text,
                insight=insight,
                requested_value=payload.requested_value,
                message=payload.message,
                history=payload.history,
                locale=payload.locale,
            )
        )
    except (ModelProviderError, ValueError) as exc:
        raise HTTPException(503, f"The review discussion could not continue: {exc}") from exc
    if result["status"] == "accepted_as_claim":
        updated_items = []
        for item in insights.get("insights") or []:
            if item.get("id") == payload.insight_id:
                updated_items.append({
                    **item,
                    "value": result["updated_value"],
                    "basis": "user_claim",
                    "review_state": "changed_after_discussion",
                    "user_evidence": result["evidence_received"],
                    "confidence": min(float(item.get("confidence") or 0), .7),
                })
            else:
                updated_items.append(item)
        insights = {**insights, "insights": updated_items, "review_status": "pending"}
        update_cv_metadata(document_id, {"cv_insights": insights}, user_id)
    return {"discussion": result, "review": {"document_id": document_id, **insights}}


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
def update_model_settings(payload: ModelSettingsRequest, request: Request) -> dict[str, Any]:
    current_user_id(request)
    try:
        return runtime_models.update(payload.provider, payload.base_url, payload.model, payload.api_key)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/api/model-settings/models")
async def refresh_models(payload: ModelRefreshRequest, request: Request) -> dict[str, Any]:
    current_user_id(request)
    try:
        models = await run_in_threadpool(list_models, payload.provider, payload.base_url, payload.api_key)
        return {"models": models}
    except ModelProviderError as exc:
        raise HTTPException(503, str(exc)) from exc


@app.post("/api/search-jobs", status_code=202)
async def create_search_job(
    request: Request,
    cv: UploadFile | None = File(default=None),
    cv_document_id: str = Form(default=""),
    location: str = Form(default="Cairo"),
    refresh_profile: bool = Form(default=True),
    live_browser: bool = Form(default=False),
    target_roles: str = Form(default=""),
    excluded_title_terms: str = Form(default=""),
    locale: str = Form(default="en"),
    limit: int = Form(default=10),
) -> dict[str, Any]:
    """Start a search and expose factual milestones while it runs."""
    user_id = current_user_id(request)
    document_id = cv_document_id.strip()
    if document_id:
        try:
            text = get_cv_text(document_id, user_id)
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
    elif cv:
        raise HTTPException(409, "Upload and review this CV before starting a search.")
    else:
        raise HTTPException(400, "Upload a PDF/TXT CV or select a generated CV.")

    _require_approved_cv_insights(document_id, user_id)
    set_active_document(document_id, user_id)
    repository.capture_profile_data(_profile_facts_from_cv(text), source="cv", user_id=user_id, document_id=document_id)
    _cleanup_search_jobs()
    job_id = str(uuid.uuid4())
    now = time.time()
    locale = "ar" if locale == "ar" else "en"
    arabic = locale == "ar"
    job = {
        "id": job_id,
        "user_id": user_id,
        "status": "queued",
        "stage": "cv",
        "progress": 8,
        "headline": "نقرأ سيرتك الذاتية" if arabic else "Reading your CV",
        "detail": "نستخرج إشارات الوظائف والمهارات والموقع من سيرتك الذاتية، دون تغيير أي حقائق." if arabic else "I am extracting role, skill, and location signals from your CV. No facts are being changed.",
        "events": [
            {
                "id": "cv-1",
                "stage": "cv",
                "status": "active",
                "title": "نقرأ سيرتك الذاتية" if arabic else "Reading your CV",
                "detail": "نستخرج فقط الخبرات والمهارات والتفضيلات التي قدمتها." if arabic else "Extracting only the experience, skills, and preferences you provided.",
                "meta": {},
            }
        ],
        "result": None,
        "error": None,
        "locale": locale,
        "created_at": now,
        "updated_at": now,
    }
    with _SEARCH_JOBS_LOCK:
        _SEARCH_JOBS[job_id] = job
    state = {
        "user_id": user_id,
        "cv_text": text,
        "document_id": document_id,
        "refresh_profile": refresh_profile,
        "location_override": location,
        "live_browser": live_browser,
        "target_roles": _split_terms(target_roles),
        "excluded_title_terms": _split_terms(excluded_title_terms),
    }
    _SEARCH_EXECUTOR.submit(_run_search_job, job_id, state, limit, locale)
    return {key: value for key, value in deepcopy(job).items() if key != "user_id"}


@app.get("/api/search-jobs/{job_id}")
def get_search_job(job_id: str, request: Request) -> dict[str, Any]:
    user_id = current_user_id(request)
    _cleanup_search_jobs()
    with _SEARCH_JOBS_LOCK:
        job = _SEARCH_JOBS.get(job_id)
        if job is None or job["user_id"] != user_id:
            raise HTTPException(404, "Search not found.")
        snapshot = deepcopy(job)
    snapshot.pop("user_id", None)
    return snapshot


@app.post("/api/search")
async def search(
    request: Request,
    cv: UploadFile | None = File(default=None),
    cv_document_id: str = Form(default=""),
    user_id: str = Form(default=""),
    location: str = Form(default="Cairo"),
    refresh_profile: bool = Form(default=True),
    live_browser: bool = Form(default=False),
    target_roles: str = Form(default=""),
    excluded_title_terms: str = Form(default=""),
    limit: int = Form(default=10),
) -> dict[str, Any]:
    user_id = current_user_id(request)
    document_id = cv_document_id.strip()
    if document_id:
        try:
            text = get_cv_text(document_id, user_id)
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
    elif cv:
        raise HTTPException(409, "Upload and review this CV before starting a search.")
    else:
        raise HTTPException(400, "Upload a PDF/TXT CV or select a generated CV.")

    try:
        _require_approved_cv_insights(document_id, user_id)
        set_active_document(document_id, user_id)
        repository.capture_profile_data(_profile_facts_from_cv(text), source="cv", user_id=user_id, document_id=document_id)
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
        view = _result_view(result, min(max(limit, 1), 10))
        view["jobs"] = repository.sync_opportunities(view["jobs"], user_id=user_id)
        repository.capture_profile_data(view.get("profile") or {}, source="cv", user_id=user_id, document_id=document_id)
        remembered = career_memory.values(document_id, user_id)
        if remembered:
            view["profile"] = {**view.get("profile", {}), "career_facts": remembered}
        return view
    except CaptchaBlockedError as exc:
        raise HTTPException(429, str(exc)) from exc
    except ModelProviderError as exc:
        raise HTTPException(503, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, f"Search failed: {exc}") from exc


@app.post("/api/batch-search")
async def batch_search(
    request: Request,
    cvs: list[UploadFile] = File(...),
    location: str = Form(default="Cairo"),
    target_roles: str = Form(default=""),
    excluded_title_terms: str = Form(default=""),
    limit: int = Form(default=10),
) -> dict[str, Any]:
    current_user_id(request)
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
async def application_draft(payload: ApplicationDraftRequest, request: Request) -> dict[str, str]:
    current_user_id(request)
    try:
        message = await run_in_threadpool(
            draft_application, payload.profile, payload.title, payload.company, payload.keywords
        )
        return {"status": "review_required", "message": message}
    except Exception as exc:
        raise HTTPException(500, f"Could not prepare application: {exc}") from exc


class JobBriefRequest(BaseModel):
    title: str
    company: str = ""
    location: str = ""
    description: str = ""
    url: str
    source: str = ""
    opportunity_type: str = "job"


@app.post("/api/job-brief")
async def job_brief(payload: JobBriefRequest) -> dict[str, Any]:
    try:
        return await run_in_threadpool(build_job_brief, payload.model_dump())
    except Exception as exc:
        raise HTTPException(500, f"Could not build the job brief: {exc}") from exc


class AcceptancePlanRequest(BaseModel):
    document_id: str
    profile: dict[str, Any] = Field(default_factory=dict)
    jobs: list[dict[str, Any]] = Field(default_factory=list)
    search: dict[str, Any] = Field(default_factory=dict)
    location: str = ""


@app.post("/api/career/plan")
async def career_plan(payload: AcceptancePlanRequest, request: Request) -> dict[str, Any]:
    user_id = current_user_id(request)
    try:
        get_cv_text(payload.document_id, user_id)
        return await run_in_threadpool(build_acceptance_plan, payload.model_dump())
    except Exception as exc:
        raise HTTPException(500, f"Could not build the acceptance plan: {exc}") from exc


class CareerAnswerRequest(BaseModel):
    document_id: str
    memory_key: str
    value: str
    question: str = ""
    kind: str = "profile"
    subject: str = ""
    cv_safe: bool = False
    cv_section: str = ""
    update_cv: bool = True


@app.post("/api/career/answers")
async def save_career_answer(request: CareerAnswerRequest, http_request: Request) -> dict[str, Any]:
    user_id = current_user_id(http_request)
    try:
        remembered = await run_in_threadpool(
            career_memory.remember,
            request.document_id,
            request.memory_key,
            request.value,
            question=request.question,
            kind=request.kind,
            subject=request.subject,
            cv_safe=request.cv_safe,
            cv_section=request.cv_section,
            user_id=user_id,
        )
        application_answers.remember(
            request.memory_key,
            request.value,
            question=request.question,
            aliases=[request.subject, request.question],
            user_id=user_id,
        )
        repository.capture_profile_data({request.memory_key: request.value}, source="user_confirmed", user_id=user_id, document_id=request.document_id)
        cv_update = None
        if request.update_cv and request.cv_safe:
            try:
                cv_update = await run_in_threadpool(enrich_cv_document, request.document_id, user_id)
                set_active_document(cv_update["document_id"], user_id)
            except ValueError:
                cv_update = None
        return {
            "remembered": remembered,
            "answer_count": len(career_memory.values(request.document_id, user_id)),
            "cv_update": cv_update,
        }
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(422, str(exc)) from exc


class CareerCVRequest(BaseModel):
    document_id: str


@app.post("/api/career/enrich-cv")
async def enrich_career_cv(request: CareerCVRequest, http_request: Request) -> dict[str, Any]:
    user_id = current_user_id(http_request)
    try:
        result = await run_in_threadpool(enrich_cv_document, request.document_id, user_id)
        set_active_document(result["document_id"], user_id)
        return result
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(422, str(exc)) from exc


class CareerResearchRequest(BaseModel):
    profile: dict[str, Any] = Field(default_factory=dict)
    location: str = ""


@app.post("/api/career/opportunities")
async def career_opportunities(payload: CareerResearchRequest, request: Request) -> dict[str, Any]:
    current_user_id(request)
    return await run_in_threadpool(discover_growth_opportunities, payload.model_dump())


class OutreachDiscoverRequest(BaseModel):
    job: dict[str, Any] = Field(default_factory=dict)
    company_url: str = ""


@app.post("/api/outreach/discover")
async def outreach_discover(payload: OutreachDiscoverRequest, request: Request) -> dict[str, Any]:
    current_user_id(request)
    return await run_in_threadpool(discover_contacts, payload.model_dump())


class OutreachDraftRequest(BaseModel):
    channel: str
    lead: dict[str, Any] = Field(default_factory=dict)
    job: dict[str, Any] = Field(default_factory=dict)
    profile: dict[str, Any] = Field(default_factory=dict)
    matched_skills: list[str] = Field(default_factory=list)


@app.post("/api/outreach/draft")
async def outreach_draft(payload: OutreachDraftRequest, request: Request) -> dict[str, Any]:
    current_user_id(request)
    try:
        return await run_in_threadpool(draft_outreach, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


class CVBuilderRequest(BaseModel):
    answers: dict[str, str] = Field(default_factory=dict)


@app.post("/api/cv/readiness")
def check_cv_readiness(payload: CVBuilderRequest) -> dict[str, Any]:
    return cv_readiness(payload.answers)


@app.post("/api/build-cv")
async def create_cv(request: CVBuilderRequest, http_request: Request) -> dict[str, Any]:
    user_id = current_user_id(http_request)
    try:
        result = await run_in_threadpool(build_cv_document, request.answers, user_id)
        set_active_document(result["document_id"], user_id)
        repository.capture_profile_data(request.answers, source="user_confirmed", user_id=user_id, document_id=result["document_id"])
        return result
    except ValueError as exc:
        detail = getattr(exc, "readiness", None)
        raise HTTPException(422, {"message": str(exc), "readiness": detail}) from exc
    except ModelProviderError as exc:
        raise HTTPException(503, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, f"Could not build the CV: {exc}") from exc


@app.get("/api/documents/{document_id}.pdf")
def download_cv(document_id: str, request: Request) -> FileResponse:
    user_id = current_user_id(request)
    try:
        path = get_cv_pdf_path(document_id, user_id)
        metadata = get_cv_metadata(document_id, user_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=str(metadata.get("source_name") or "wazzefni-ats-cv.pdf"),
    )


class TailoredCVRequest(BaseModel):
    document_id: str
    title: str
    company: str = ""
    description: str = ""
    url: str = ""
    keywords: list[str] = Field(default_factory=list)


@app.post("/api/tailored-cv")
async def create_tailored_cv(request: TailoredCVRequest, http_request: Request) -> dict[str, Any]:
    user_id = current_user_id(http_request)
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
            user_id,
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
    application_id: str = ""
    opportunity_id: str = ""
    approval_id: str = ""
    title: str = ""
    company: str = ""
    location: str = ""
    source: str = ""
    match_score: float = 0


@app.post("/api/application-sessions")
def create_application_session(request: ApplicationSessionRequest, http_request: Request) -> dict[str, Any]:
    user_id = current_user_id(http_request)
    try:
        _require_approved_cv_insights(request.document_id, user_id)
        tracked = request.application_id.strip()
        if not tracked:
            tracked = repository.create_application({
                "opportunity_id": request.opportunity_id or None,
                "title": request.title or "Application",
                "company": request.company,
                "location": request.location,
                "url": request.url,
                "status": "preparing",
                "document_id": request.document_id,
                "source": request.source,
                "match_score": request.match_score,
            }, user_id=user_id)["id"]
        if request.auto_submit and not repository.approval_is_valid(request.approval_id, "submit_application", tracked, user_id=user_id):
            raise ValueError("Auto-submit requires an approved submission request.")
        repository.transition_application(tracked, "applying", source="application_agent", message="Application browser started.", force=True, user_id=user_id)
        return application_manager.start(
            request.url,
            request.document_id,
            request.profile,
            auto_submit=request.auto_submit,
            visible=True,
            tracking_application_id=tracked,
            user_id=user_id,
        )
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/api/application-sessions")
def list_application_sessions(request: Request) -> dict[str, Any]:
    return {"items": application_manager.list(current_user_id(request))}


@app.get("/api/application-sessions/{session_id}")
def application_session_status(session_id: str, request: Request) -> dict[str, Any]:
    try:
        return application_manager.get(session_id, current_user_id(request))
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


class ApplicationCommandRequest(BaseModel):
    command: str
    values: dict[str, str] = Field(default_factory=dict)
    approval_id: str = ""


@app.post("/api/application-sessions/{session_id}/commands")
def application_session_command(session_id: str, request: ApplicationCommandRequest, http_request: Request) -> dict[str, Any]:
    user_id = current_user_id(http_request)
    try:
        if request.command == "submit":
            snapshot = application_manager.get(session_id, user_id)
            application_id = str(snapshot.get("application_id") or "")
            if not application_id or not repository.approval_is_valid(request.approval_id, "submit_application", application_id, user_id=user_id):
                raise ValueError("Submitting requires an approved submission request.")
        return application_manager.command(session_id, request.command, request.values, user_id=user_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


_FRONTEND_DIST = Path(__file__).resolve().parents[1] / "frontend" / "dist"
if _FRONTEND_DIST.is_dir():
    # API routes are registered first; the SPA handles every remaining route.
    app.mount("/", StaticFiles(directory=_FRONTEND_DIST, html=True), name="frontend")
