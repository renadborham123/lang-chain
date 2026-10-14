"""Visible Playwright auto-fill sessions with explicit, auditable submission."""

from __future__ import annotations

import hashlib
import json
import queue
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

from langchain_core.prompts import ChatPromptTemplate
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from application_memory import ApplicationAnswerStore, application_answers, canonical_answer_key
from availability import UNAVAILABLE_TERMS
from config import settings
from document_store import get_cv_pdf_path
from model_provider import invoke_prompt
from scrape_jobs import _browser_launch_options


_BROWSER_PROFILE = Path(__file__).resolve().parent / "memory" / "browser_profiles" / "job-accounts"
_CAPTCHA_TERMS = (
    "captcha",
    "verify you are human",
    "recaptcha",
    "تحقق من أنك إنسان",
    "التحقق من أنك لست روبوت",
)
_SUBMISSION_SUCCESS_TERMS = (
    "application submitted",
    "application received",
    "application complete",
    "thank you for applying",
    "thank you for your application",
    "thanks for applying",
    "we have received your application",
    "your application has been submitted",
    "تم إرسال طلبك",
    "تم تقديم طلبك",
    "شكراً لتقديمك",
)

_QUESTION_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You turn unknown required job-application fields into short, natural questions for the candidate. "
            "Return JSON only: an array with one object per field containing field_id, memory_key, and question. "
            "memory_key must be a stable English snake_case concept that can match the same question on another site "
            "(for example work_authorization, sponsorship_required, notice_period, expected_salary). "
            "Ask only for the exact factual information the field needs; do not invent an answer and do not ask for "
            "information already listed in known_profile_fields. Use the field's language when practical. "
            "If options are supplied, mention them naturally in the question.",
        ),
        (
            "human",
            "Page: {page_context}\nKnown profile fields: {known_profile_fields}\n"
            "Already remembered answer keys: {remembered_keys}\nUnknown required fields:\n{fields}",
        ),
    ]
)


def validate_application_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError("The application URL must be a valid HTTP or HTTPS URL without embedded credentials.")
    return url.strip()


def _profile_values(profile: dict[str, Any]) -> dict[str, str]:
    links = [str(item) for item in profile.get("links", []) if item]
    linkedin = next((item for item in links if "linkedin.com" in item.casefold()), "")
    github = next((item for item in links if "github.com" in item.casefold()), "")
    full_name = str(profile.get("full_name") or "").strip()
    name_parts = full_name.split()
    job_titles = [str(item).strip() for item in profile.get("job_titles", []) if str(item).strip()]
    years_experience = profile.get("years_experience")
    return {
        "name": full_name,
        "full_name": full_name,
        "first_name": name_parts[0] if name_parts else "",
        "last_name": " ".join(name_parts[1:]) if len(name_parts) > 1 else "",
        "email": str(profile.get("email") or ""),
        "phone": str(profile.get("phone") or ""),
        "location": str(profile.get("preferred_location") or ""),
        "city": str(profile.get("preferred_location") or ""),
        "linkedin": linkedin,
        "github": github,
        "website": next(iter(links), ""),
        "current_title": job_titles[0] if job_titles else "",
        "years_experience": "" if years_experience in (None, "") else str(years_experience),
        "education_level": str(profile.get("education_level") or ""),
        "graduation_year": str(profile.get("graduation_year") or ""),
    }


def _field_key(locator) -> str:
    values = [
        locator.get_attribute("name") or "",
        locator.get_attribute("id") or "",
        locator.get_attribute("placeholder") or "",
        locator.get_attribute("autocomplete") or "",
        locator.get_attribute("aria-label") or "",
    ]
    return " ".join(values).casefold()


def _matching_value(
    field_key: str,
    values: dict[str, str],
    answers: dict[str, str],
    memory_key: str = "",
) -> str:
    normalized_field = re.sub(r"[^a-z0-9]+", " ", field_key.casefold()).strip()
    if memory_key and str(answers.get(memory_key) or "").strip():
        return str(answers[memory_key]).strip()
    for question, answer in answers.items():
        normalized_question = re.sub(r"[^a-z0-9]+", " ", question.casefold()).strip()
        if normalized_question and (
            normalized_question in normalized_field or normalized_field in normalized_question
        ):
            return answer
    patterns = (
        (("email",), "email"),
        (("phone", "mobile", "tel", "telephone"), "phone"),
        (("linkedin",), "linkedin"),
        (("github",), "github"),
        (("website", "portfolio"), "website"),
        (("city", "location", "address-level2"), "location"),
        (("first name", "firstname", "first_name", "given-name"), "first_name"),
        (("last name", "lastname", "last_name", "family-name", "surname"), "last_name"),
        (("full name", "fullname", "full_name", "candidate name", "applicant name"), "full_name"),
        (("years of experience", "experience years", "total experience"), "years_experience"),
        (("current title", "current role", "job title"), "current_title"),
        (("education level", "highest education", "degree level"), "education_level"),
        (("graduation year", "year of graduation"), "graduation_year"),
    )
    for aliases, key in patterns:
        if any(alias in field_key for alias in aliases):
            return values.get(key, "")
    return values.get("full_name", "") if field_key.strip() in {"name", "autocomplete name"} else ""


def _field_label(locator) -> str:
    try:
        label = locator.evaluate(
            """element => {
                const explicit = element.labels && element.labels.length ? element.labels[0].innerText : '';
                return explicit || element.getAttribute('aria-label') || element.getAttribute('placeholder') ||
                    element.getAttribute('name') || element.id || 'Required field';
            }"""
        )
        return re.sub(r"\s+", " ", str(label)).strip()[:120]
    except Exception:
        return _field_key(locator)[:120] or "Required field"


def _field_descriptor(locator, index: int) -> dict[str, Any]:
    details = locator.evaluate(
        """element => {
            const labelText = label => {
                if (!label) return '';
                const copy = label.cloneNode(true);
                copy.querySelectorAll('input, textarea, select, option, button').forEach(node => node.remove());
                return copy.textContent.trim();
            };
            const explicit = element.labels && element.labels.length ? labelText(element.labels[0]) : '';
            const fieldset = element.closest('fieldset');
            const legend = fieldset && fieldset.querySelector('legend')
                ? fieldset.querySelector('legend').innerText : '';
            const tag = element.tagName.toLowerCase();
            const type = (element.getAttribute('type') || tag).toLowerCase();
            let options = [];
            if (tag === 'select') {
                options = Array.from(element.options)
                    .filter(option => option.value)
                    .map(option => option.textContent.trim() || option.value);
            } else if (type === 'radio' && element.name) {
                options = Array.from(document.getElementsByName(element.name)).map(candidate => {
                    const label = candidate.labels && candidate.labels.length
                        ? candidate.labels[0].innerText.trim() : '';
                    return label || candidate.value || candidate.id;
                }).filter(Boolean);
            }
            return {
                tag,
                input_type: type,
                name: element.getAttribute('name') || '',
                element_id: element.id || '',
                placeholder: element.getAttribute('placeholder') || '',
                autocomplete: element.getAttribute('autocomplete') || '',
                aria_label: element.getAttribute('aria-label') || '',
                label: legend.trim() || explicit.trim() || element.getAttribute('aria-label') ||
                    element.getAttribute('placeholder') || element.getAttribute('name') || element.id || '',
                options,
            };
        }"""
    )
    aliases = list(
        dict.fromkeys(
            str(details.get(key) or "").strip()
            for key in ("label", "name", "element_id", "placeholder", "autocomplete", "aria_label")
            if str(details.get(key) or "").strip()
        )
    )
    signature_parts = [
        str(details.get("tag") or ""),
        str(details.get("input_type") or ""),
        str(details.get("name") or ""),
        str(details.get("label") or ""),
    ]
    if details.get("input_type") != "radio":
        signature_parts.append(str(details.get("element_id") or ""))
    signature = "|".join(part.casefold().strip() for part in signature_parts)
    details["field_id"] = hashlib.sha256((signature or str(index)).encode("utf-8")).hexdigest()[:16]
    details["label"] = str(details.get("label") or f"Required field {index + 1}").strip()[:160]
    details["aliases"] = aliases
    details["options"] = list(dict.fromkeys(str(item).strip() for item in details.get("options", []) if str(item).strip()))[:30]
    return details


def _field_has_value(locator, descriptor: dict[str, Any]) -> bool:
    field_type = descriptor.get("input_type")
    tag = descriptor.get("tag")
    if field_type == "radio":
        return bool(
            locator.evaluate(
                """element => Array.from(document.getElementsByName(element.name))
                    .some(candidate => candidate.checked)"""
            )
        )
    if field_type == "checkbox":
        return bool(locator.is_checked())
    if tag == "select":
        return bool(str(locator.input_value() or "").strip())
    return bool(str(locator.input_value() or "").strip())


def _answer_is_yes(value: str) -> bool:
    return str(value).strip().casefold() in {"1", "true", "yes", "y", "agree", "accepted", "نعم", "موافق"}


def _fill_answer(page, locator, descriptor: dict[str, Any], value: str) -> bool:
    clean = str(value).strip()
    if not clean:
        return False
    field_type = descriptor.get("input_type")
    tag = descriptor.get("tag")
    if field_type == "radio":
        name = str(descriptor.get("name") or "")
        if not name:
            return False
        candidates = page.locator("input[type=radio]")
        for index in range(candidates.count()):
            candidate = candidates.nth(index)
            if (candidate.get_attribute("name") or "") != name:
                continue
            label = _field_label(candidate)
            candidate_value = candidate.get_attribute("value") or ""
            if clean.casefold() in {label.casefold(), candidate_value.casefold()} or (
                clean.casefold() in label.casefold() or label.casefold() in clean.casefold()
            ):
                candidate.check()
                return True
        return False
    if field_type == "checkbox":
        if _answer_is_yes(clean):
            locator.check()
            return True
        if locator.is_checked():
            locator.uncheck()
        return False
    if tag == "select":
        options = locator.locator("option")
        for index in range(options.count()):
            option = options.nth(index)
            label = option.inner_text().strip()
            option_value = option.get_attribute("value") or ""
            if clean.casefold() in {label.casefold(), option_value.casefold()} or (
                clean.casefold() in label.casefold() or label.casefold() in clean.casefold()
            ):
                locator.select_option(value=option_value)
                return True
        return False
    locator.fill(clean)
    return True


def _fallback_question(field: dict[str, Any]) -> dict[str, Any]:
    label = str(field.get("label") or "this required field").strip()
    key_source = str(field.get("name") or label)
    return {
        "field_id": field["field_id"],
        "memory_key": canonical_answer_key(key_source) or f"application_field_{field['field_id']}",
        "question": f"What should I enter for “{label}”?",
    }


def generate_application_questions(
    fields: list[dict[str, Any]],
    *,
    page_context: str,
    known_profile_fields: list[str],
    remembered_keys: list[str],
) -> list[dict[str, Any]]:
    """Use the selected local model to phrase and canonicalize unknown form fields."""
    if not fields:
        return []
    public_fields = [
        {
            "field_id": item["field_id"],
            "label": item["label"],
            "name": item.get("name", ""),
            "input_type": item.get("input_type", ""),
            "options": item.get("options", []),
        }
        for item in fields
    ]
    try:
        content = invoke_prompt(
            _QUESTION_PROMPT,
            {
                "page_context": page_context[:500],
                "known_profile_fields": ", ".join(known_profile_fields),
                "remembered_keys": ", ".join(remembered_keys) or "none",
                "fields": json.dumps(public_fields, ensure_ascii=False),
            },
            json_mode=True,
            timeout=60,
        )
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", str(content).strip(), flags=re.IGNORECASE)
        generated = json.loads(cleaned)
        if not isinstance(generated, list):
            raise ValueError("Question model did not return a list.")
    except Exception:
        return [_fallback_question(item) for item in fields]

    by_id = {str(item.get("field_id") or ""): item for item in generated if isinstance(item, dict)}
    output = []
    for item in fields:
        candidate = by_id.get(item["field_id"], {})
        key = canonical_answer_key(str(candidate.get("memory_key") or ""))
        question = re.sub(r"\s+", " ", str(candidate.get("question") or "")).strip()
        output.append(
            {
                "field_id": item["field_id"],
                "memory_key": key or _fallback_question(item)["memory_key"],
                "question": question[:240] or _fallback_question(item)["question"],
            }
        )
    return output


def _visible_submit_locator(page):
    selectors = (
        "form:has(input[type=file]) button[type=submit]",
        "form:has(input[type=file]) input[type=submit]",
        "form:has(input[name*=email i]) button[type=submit]",
        "button:has-text('Submit application')",
        "button:has-text('Send application')",
        "button:has-text('Submit Application')",
        "button:has-text('إرسال الطلب')",
        "button:has-text('تقديم الطلب')",
        "button:has-text('إرسال الاستمارة')",
    )
    for selector in selectors:
        candidates = page.locator(selector)
        for index in range(candidates.count()):
            candidate = candidates.nth(index)
            try:
                aria_label = (candidate.get_attribute("aria-label") or "").casefold()
                if candidate.is_visible() and candidate.is_enabled() and "search" not in aria_label:
                    return candidate
            except Exception:
                continue
    return None


def _visible_progress_locator(page):
    selectors = (
        "button[aria-label*='next step' i]",
        "button[aria-label*='continue' i]",
        "button[aria-label*='review' i]",
        "button:has-text('Next')",
        "button:has-text('Continue')",
        "button:has-text('Review your application')",
        "button:has-text('التالي')",
        "button:has-text('متابعة')",
        "button:has-text('مراجعة الطلب')",
        "button:has-text('الانتقال إلى الخطوة التالية')",
    )
    for selector in selectors:
        candidates = page.locator(selector)
        for index in range(candidates.count()):
            candidate = candidates.nth(index)
            try:
                button_type = (candidate.get_attribute("type") or "button").casefold()
                text = candidate.inner_text().strip().casefold()
                if (
                    candidate.is_visible()
                    and candidate.is_enabled()
                    and button_type != "submit"
                    and "submit" not in text
                    and "إرسال" not in text
                    and "تقديم الطلب" not in text
                ):
                    return candidate
            except Exception:
                continue
    return None


def _fill_page(
    page,
    document_id: str,
    profile: dict[str, Any],
    answers: dict[str, str] | None = None,
    *,
    field_bindings: dict[str, str] | None = None,
    answer_store: ApplicationAnswerStore | None = None,
) -> dict[str, Any]:
    values = _profile_values(profile)
    answers = answers if answers is not None else {}
    field_bindings = field_bindings if field_bindings is not None else {}
    filled: list[str] = []
    reused_answers: list[str] = []
    uploaded = False

    file_inputs = page.locator("input[type=file]")
    for index in range(file_inputs.count()):
        file_input = file_inputs.nth(index)
        try:
            file_input.set_input_files(str(get_cv_pdf_path(document_id)))
            uploaded = True
            filled.append("CV PDF")
            break
        except Exception:
            continue

    fields = page.locator(
        "input:not([type=hidden]):not([type=file]):not([type=submit]):not([type=button]):not([type=password]), "
        "textarea, select"
    )
    processed: set[str] = set()
    for index in range(fields.count()):
        locator = fields.nth(index)
        try:
            if not locator.is_visible() or locator.is_disabled():
                continue
            descriptor = _field_descriptor(locator, index)
            field_id = descriptor["field_id"]
            if field_id in processed:
                continue
            processed.add(field_id)
            if _field_has_value(locator, descriptor):
                continue
            memory_key = field_bindings.get(field_id, "")
            searchable = " ".join([*descriptor.get("aliases", []), descriptor["label"]])
            value = _matching_value(searchable, values, answers, memory_key)
            if not value and answer_store is not None:
                remembered = answer_store.lookup(memory_key, descriptor.get("aliases", []))
                if remembered:
                    remembered_key, value = remembered
                    field_bindings[field_id] = remembered_key
                    answers.setdefault(remembered_key, value)
                    reused_answers.append(remembered_key)
            if value and _fill_answer(page, locator, descriptor, value):
                filled.append(descriptor["label"])
        except Exception:
            continue

    missing: list[dict[str, Any]] = []
    required = page.locator(
        "input[required]:not([type=hidden]), textarea[required], select[required], "
        "input[aria-required=true]:not([type=hidden]), textarea[aria-required=true], select[aria-required=true]"
    )
    seen_required: set[str] = set()
    password_required = False
    for index in range(required.count()):
        locator = required.nth(index)
        try:
            if not locator.is_visible():
                continue
            descriptor = _field_descriptor(locator, index)
            if descriptor["field_id"] in seen_required:
                continue
            seen_required.add(descriptor["field_id"])
            if descriptor.get("input_type") == "password":
                password_required = True
                continue
            if not _field_has_value(locator, descriptor):
                missing.append(descriptor)
        except Exception:
            continue
    body = page.locator("body").inner_text().casefold()
    blocked = []
    unavailable = []
    if any(term in body for term in UNAVAILABLE_TERMS):
        unavailable.append("This employer is no longer accepting applications for this role.")
    if any(term in body for term in _CAPTCHA_TERMS):
        blocked.append("Human verification is required.")
    if any(term in body for term in ("sign in to apply", "log in to apply", "login to apply")):
        blocked.append("Sign-in is required in the visible browser.")
    if password_required:
        blocked.append("Sign-in is required in the visible browser.")
    if "linkedin.com" in page.url.casefold() and not uploaded and any(
        term in body for term in ("sign in", "join now")
    ):
        blocked.append("Sign in to LinkedIn once in the visible browser, then press retry.")
    submit = _visible_submit_locator(page)
    return {
        "filled_fields": list(dict.fromkeys(filled)),
        "cv_uploaded": uploaded,
        "missing_required": [],
        "_missing_fields": missing,
        "reused_answers": list(dict.fromkeys(reused_answers)),
        "blockers": blocked,
        "unavailable": unavailable,
        "submit_available": submit is not None,
    }


def _try_open_form(page):
    if page.locator("input[type=file], form input[required], form textarea[required]").count():
        return page
    apply_name = re.compile(
        r"^(?:(?:easy )?apply(?: now| for this job)?|"
        r"التقدم(?: الآن| لهذه الوظيفة| بسهولة)?|"
        r"تقديم(?: الطلب| طلب| الآن)?(?: بسهولة)?)$",
        re.IGNORECASE,
    )
    candidates = page.get_by_role("button", name=apply_name)
    if not candidates.count():
        candidates = page.get_by_role("link", name=apply_name)
    before_pages = len(page.context.pages)
    for index in range(candidates.count()):
        candidate = candidates.nth(index)
        try:
            if not candidate.is_visible() or not candidate.is_enabled():
                continue
            candidate.click(timeout=10_000)
            page.wait_for_timeout(1000)
            if len(page.context.pages) > before_pages:
                page = page.context.pages[-1]
                page.wait_for_load_state("domcontentloaded", timeout=15_000)
            break
        except Exception:
            continue
    return page


def _submission_confirmed(page, previous_url: str) -> bool:
    try:
        body = page.locator("body").inner_text().casefold()
    except Exception:
        body = ""
    if any(term in body for term in _SUBMISSION_SUCCESS_TERMS):
        return True
    current_url = page.url.casefold()
    confirmation_url = any(
        marker in current_url
        for marker in ("/confirmation", "/thank-you", "/thank_you", "/application-complete", "/submitted")
    )
    return current_url != previous_url.casefold() and confirmation_url


@dataclass
class ApplicationSession:
    id: str
    url: str
    document_id: str
    profile: dict[str, Any]
    user_id: str = "local-user"
    auto_submit: bool = False
    visible: bool = True
    tracking_application_id: str = ""
    answers: dict[str, str] = field(default_factory=dict)
    field_bindings: dict[str, str] = field(default_factory=dict)
    field_questions: dict[str, dict[str, Any]] = field(default_factory=dict)
    status: str = "starting"
    message: str = "Opening the application page."
    details: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    _commands: queue.Queue[tuple[str, dict[str, str]]] = field(default_factory=queue.Queue, repr=False)
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "id": self.id,
                "status": self.status,
                "message": self.message,
                "details": self.details,
                "created_at": self.created_at,
                "application_id": self.tracking_application_id or None,
                "recoverable": self.status == "recoverable",
            }

    def recovery_payload(self) -> dict[str, Any]:
        with self._lock:
            return {
                "id": self.id,
                "url": self.url,
                "document_id": self.document_id,
                "profile": self.profile,
                "user_id": self.user_id,
                "auto_submit": False,
                "visible": self.visible,
                "tracking_application_id": self.tracking_application_id,
                "answers": self.answers,
                "field_bindings": self.field_bindings,
                "field_questions": self.field_questions,
                "status": self.status,
                "message": self.message,
                "details": self.details,
                "created_at": self.created_at,
            }

    def persist(self) -> None:
        if not self.tracking_application_id:
            return
        try:
            from employment.repository import repository
            repository.save_application_session(self.id, self.tracking_application_id, self.recovery_payload(), user_id=self.user_id)
        except Exception:
            # A database problem must not interrupt the employer form interaction.
            pass

    def update(self, status: str, message: str, details: dict[str, Any] | None = None) -> None:
        with self._lock:
            self.status = status
            self.message = message
            if details is not None:
                self.details = details
        self.persist()
        if self.tracking_application_id:
            lifecycle = {
                "starting": "applying",
                "needs_input": "needs_input",
                "ready_to_submit": "ready_to_submit",
                "submitted": "applied",
                "blocked": "blocked",
                "failed": "failed",
                "expired": "expired",
                "unavailable": "closed",
            }
            if status in lifecycle:
                try:
                    from employment.repository import repository
                    repository.transition_application(
                        self.tracking_application_id,
                        lifecycle[status],
                        source="application_agent",
                        message=message,
                        evidence={"session_status": status, "details": details or {}},
                        force=True,
                        user_id=self.user_id,
                    )
                except Exception:
                    # Browser automation must keep running even when persistence is temporarily unavailable.
                    pass


class ApplicationManager:
    def __init__(
        self,
        *,
        answer_store: ApplicationAnswerStore | None = None,
        question_generator: Callable[..., list[dict[str, Any]]] | None = None,
        browser_profile: Path | str | None = None,
    ) -> None:
        self._sessions: dict[str, ApplicationSession] = {}
        self._lock = threading.RLock()
        self.answer_store = answer_store or application_answers
        self._database_answer_store = answer_store is None or answer_store is application_answers
        self.question_generator = question_generator or generate_application_questions
        self.browser_profile = Path(browser_profile) if browser_profile is not None else _BROWSER_PROFILE
        self._restore_sessions()

    def _restore_sessions(self) -> None:
        try:
            from employment.database import init_database
            from employment.repository import repository
            init_database()
            artifacts = repository.list_application_sessions(recoverable_only=True)
        except Exception:
            return
        for artifact in artifacts:
            payload = artifact.get("payload") or {}
            try:
                session = ApplicationSession(
                    id=str(payload.get("id") or artifact["session_id"]),
                    url=str(payload["url"]),
                    document_id=str(payload["document_id"]),
                    profile=dict(payload.get("profile") or {}),
                    user_id=str(payload.get("user_id") or artifact.get("user_id") or "local-user"),
                    auto_submit=False,
                    visible=bool(payload.get("visible", True)),
                    tracking_application_id=str(payload.get("tracking_application_id") or artifact.get("application_id") or ""),
                    answers=dict(payload.get("answers") or {}),
                    field_bindings=dict(payload.get("field_bindings") or {}),
                    field_questions=dict(payload.get("field_questions") or {}),
                    status="recoverable",
                    message="The previous browser session stopped. Review it, then resume safely.",
                    details={**dict(payload.get("details") or {}), "previous_status": payload.get("status")},
                    created_at=float(payload.get("created_at") or time.time()),
                )
            except (KeyError, TypeError, ValueError):
                continue
            self._sessions[session.id] = session

    def _questions_for_missing(
        self,
        session: ApplicationSession,
        fields: list[dict[str, Any]],
        page,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        new_fields = [item for item in fields if item["field_id"] not in session.field_questions]
        if new_fields:
            profile_values = _profile_values(session.profile)
            try:
                page_context = f"{page.title()} | {page.url}"
            except Exception:
                page_context = session.url
            try:
                generated = self.question_generator(
                    new_fields,
                    page_context=page_context,
                    known_profile_fields=[key for key, value in profile_values.items() if value],
                    remembered_keys=self.answer_store.keys(user_id=session.user_id if self._database_answer_store else None),
                )
            except Exception:
                generated = [_fallback_question(item) for item in new_fields]
            by_id = {
                str(item.get("field_id") or ""): item
                for item in generated
                if isinstance(item, dict)
            }
            for field_details in new_fields:
                candidate = by_id.get(field_details["field_id"], {})
                fallback = _fallback_question(field_details)
                memory_key = canonical_answer_key(str(candidate.get("memory_key") or ""))
                question = re.sub(r"\s+", " ", str(candidate.get("question") or "")).strip()
                session.field_bindings[field_details["field_id"]] = memory_key or fallback["memory_key"]
                session.field_questions[field_details["field_id"]] = {
                    "field_id": field_details["field_id"],
                    "memory_key": memory_key or fallback["memory_key"],
                    "label": field_details["label"],
                    "question": question[:240] or fallback["question"],
                    "options": field_details.get("options", []),
                    "input_type": field_details.get("input_type", "text"),
                    "aliases": field_details.get("aliases", []),
                }

        unresolved: list[dict[str, Any]] = []
        reused: list[str] = []
        for field_details in fields:
            question = session.field_questions.get(field_details["field_id"])
            if not question:
                continue
            memory_key = question["memory_key"]
            current_value = str(session.answers.get(memory_key) or "").strip()
            remembered = None
            if not current_value:
                remembered = self.answer_store.lookup(
                    memory_key,
                    [question["question"], question["label"], *question.get("aliases", [])],
                    user_id=session.user_id if self._database_answer_store else None,
                )
            if remembered:
                remembered_key, current_value = remembered
                session.field_bindings[field_details["field_id"]] = remembered_key
                session.answers[remembered_key] = current_value
                reused.append(remembered_key)
            if current_value:
                continue
            unresolved.append({key: value for key, value in question.items() if key != "aliases"})
        return unresolved, list(dict.fromkeys(reused))

    def _remember_answers(self, session: ApplicationSession, values: dict[str, str]) -> None:
        for memory_key, value in values.items():
            matching = next(
                (
                    question
                    for question in session.field_questions.values()
                    if question.get("memory_key") == memory_key
                ),
                None,
            )
            if matching:
                stored_key = self.answer_store.remember(
                    memory_key,
                    value,
                    question=str(matching.get("question") or ""),
                    aliases=[matching.get("label", ""), *matching.get("aliases", [])],
                    user_id=session.user_id if self._database_answer_store else None,
                )
                session.answers[stored_key] = value
            else:
                stored_key = self.answer_store.remember(
                    memory_key,
                    value,
                    question=memory_key,
                    aliases=[memory_key],
                    user_id=session.user_id if self._database_answer_store else None,
                )
                session.answers[stored_key] = value

    def start(
        self,
        url: str,
        document_id: str,
        profile: dict[str, Any],
        *,
        auto_submit: bool = False,
        visible: bool = True,
        tracking_application_id: str = "",
        user_id: str = "local-user",
    ) -> dict[str, Any]:
        get_cv_pdf_path(document_id, user_id)
        legacy_answers = {
            str(key): str(value)
            for key, value in (profile.get("application_answers") or {}).items()
            if str(key).strip() and str(value).strip()
        }
        self.answer_store.remember_bulk(legacy_answers, user_id=user_id if self._database_answer_store else None)
        cutoff = time.time() - settings.APPLICATION_SESSION_TTL_MINUTES * 60
        with self._lock:
            self._sessions = {
                key: value for key, value in self._sessions.items()
                if value.created_at >= cutoff
                or value.status not in {"submitted", "closed", "failed", "expired", "unavailable"}
            }
        session = ApplicationSession(
            id=str(uuid.uuid4()),
            url=validate_application_url(url),
            document_id=document_id,
            profile=profile,
            user_id=user_id,
            auto_submit=auto_submit,
            visible=visible,
            tracking_application_id=tracking_application_id,
            answers={},
        )
        with self._lock:
            if visible and any(
                item.visible
                and item.status not in {"closed", "failed", "expired", "unavailable"}
                for item in self._sessions.values()
            ):
                raise ValueError("Close the current visible application session before starting another one.")
            self._sessions[session.id] = session
        session.persist()
        thread = threading.Thread(
            target=self._run,
            args=(session,),
            daemon=True,
            name=f"application-{session.id[:8]}",
        )
        thread.start()
        return session.snapshot()

    def get(self, session_id: str, user_id: str | None = None) -> dict[str, Any]:
        with self._lock:
            session = self._sessions.get(session_id)
        if not session or (user_id is not None and session.user_id != user_id):
            raise KeyError("Application session was not found.")
        return session.snapshot()

    def list(self, user_id: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            sessions = [item for item in self._sessions.values() if user_id is None or item.user_id == user_id]
        return [session.snapshot() for session in sorted(sessions, key=lambda item: item.created_at, reverse=True)]

    def command(
        self,
        session_id: str,
        command: str,
        values: dict[str, str] | None = None,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            session = self._sessions.get(session_id)
        if not session or (user_id is not None and session.user_id != user_id):
            raise KeyError("Application session was not found.")
        if command not in {"submit", "close", "retry"}:
            raise ValueError("Command must be submit, retry, or close.")
        clean_values = {
            str(key).strip(): str(value).strip()
            for key, value in (values or {}).items()
            if str(key).strip() and str(value).strip()
        }
        if session.status == "recoverable":
            if command == "close":
                session.update("closed", "Recovered browser session closed.", session.details)
                return session.snapshot()
            if command != "retry":
                raise ValueError("Resume the recovered browser session before submitting.")
            self._remember_answers(session, clean_values)
            session.update("starting", "Restoring the application page from the saved checkpoint.", session.details)
            thread = threading.Thread(target=self._run, args=(session,), daemon=True, name=f"application-{session.id[:8]}-recovered")
            thread.start()
            return session.snapshot()
        session._commands.put((command, clean_values))
        return session.snapshot()

    def _run(self, session: ApplicationSession) -> None:
        try:
            with sync_playwright() as playwright:
                if session.visible:
                    self.browser_profile.mkdir(parents=True, exist_ok=True)
                    persistent_options = _browser_launch_options(True)
                    persistent_options["args"] = [
                        *list(persistent_options.get("args", [])),
                        "--disable-features=FedCm",
                    ]
                    context = playwright.chromium.launch_persistent_context(
                        str(self.browser_profile),
                        **persistent_options,
                    )
                    browser = context.browser
                    page = context.pages[0] if context.pages else context.new_page()
                else:
                    browser = playwright.chromium.launch(**_browser_launch_options(False))
                    context = browser.new_context()
                    page = context.new_page()

                def prepare(*, navigate: bool = True) -> dict[str, Any]:
                    nonlocal page
                    for open_page in list(context.pages):
                        if open_page != page and "accounts.google.com" in open_page.url.casefold():
                            open_page.close()
                    if navigate:
                        page.goto(session.url, wait_until="domcontentloaded", timeout=45_000)
                    page = _try_open_form(page)
                    prepared: dict[str, Any] = {}
                    all_filled: list[str] = []
                    all_reused: list[str] = []
                    for _ in range(8):
                        prepared = _fill_page(
                            page,
                            session.document_id,
                            session.profile,
                            session.answers,
                            field_bindings=session.field_bindings,
                            answer_store=self.answer_store,
                        )
                        all_filled.extend(prepared["filled_fields"])
                        all_reused.extend(prepared.get("reused_answers", []))
                        missing_fields = prepared.pop("_missing_fields", [])
                        if missing_fields and not prepared["unavailable"] and not prepared["blockers"]:
                            questions, reused = self._questions_for_missing(session, missing_fields, page)
                            all_reused.extend(reused)
                            if reused:
                                prepared = _fill_page(
                                    page,
                                    session.document_id,
                                    session.profile,
                                    session.answers,
                                    field_bindings=session.field_bindings,
                                    answer_store=self.answer_store,
                                )
                                all_filled.extend(prepared["filled_fields"])
                                all_reused.extend(prepared.get("reused_answers", []))
                                missing_fields = prepared.pop("_missing_fields", [])
                                questions, extra_reused = self._questions_for_missing(
                                    session, missing_fields, page
                                )
                                all_reused.extend(extra_reused)
                            prepared["missing_required"] = questions
                        prepared["filled_fields"] = list(dict.fromkeys(all_filled))
                        prepared["reused_answers"] = list(dict.fromkeys(all_reused))
                        prepared["answer_memory_count"] = self.answer_store.count()
                        prepared["login_session_persistent"] = session.visible
                        if (
                            prepared["unavailable"]
                            or prepared["blockers"]
                            or prepared["missing_required"]
                            or prepared["submit_available"]
                        ):
                            break
                        progress = _visible_progress_locator(page)
                        if progress is None:
                            break
                        pages_before = len(context.pages)
                        progress.click(timeout=10_000)
                        page.wait_for_timeout(700)
                        if len(context.pages) > pages_before:
                            page = context.pages[-1]
                            page.wait_for_load_state("domcontentloaded", timeout=15_000)
                    if prepared["unavailable"]:
                        session.update(
                            "unavailable",
                            "This job is closed, so Wazzefni will not try to submit it.",
                            prepared,
                        )
                    elif prepared["blockers"]:
                        linkedin_login = any(
                            "sign in to linkedin" in blocker.casefold()
                            for blocker in prepared["blockers"]
                        )
                        if linkedin_login:
                            page.goto(
                                "https://www.linkedin.com/login",
                                wait_until="domcontentloaded",
                                timeout=30_000,
                            )
                        session.update(
                            "blocked",
                            (
                                "Sign in with your LinkedIn email and password in the visible browser, then retry. "
                                "Do not use the Google sign-in popup."
                                if linkedin_login
                                else (
                                    "Complete the human verification in the visible browser. "
                                    "Wazzefni will continue automatically when it is solved."
                                )
                            ),
                            prepared,
                        )
                    elif prepared["missing_required"]:
                        session.update(
                            "needs_input",
                            "Add the missing factual answers, then Wazzefni can continue.",
                            prepared,
                        )
                    elif not prepared["submit_available"]:
                        session.update(
                            "needs_review",
                            "The available fields were filled, but this page has no visible application submit button.",
                            prepared,
                        )
                    else:
                        session.update("ready_to_submit", "The form is filled and ready for final submission.", prepared)
                    return prepared

                details = prepare()

                if session.auto_submit and session.status == "ready_to_submit":
                    session._commands.put(("submit", {}))
                if session.status == "unavailable":
                    context.close()
                    if not session.visible and browser:
                        browser.close()
                    return

                deadline = time.time() + settings.APPLICATION_SESSION_TTL_MINUTES * 60
                next_login_check = time.monotonic()
                while browser.is_connected() and time.time() < deadline:
                    try:
                        command, values = session._commands.get(timeout=0.5)
                    except queue.Empty:
                        if (
                            session.auto_submit
                            and session.status == "blocked"
                            and time.monotonic() >= next_login_check
                        ):
                            next_login_check = time.monotonic() + 1.5
                            linkedin_blocked = any(
                                "sign in to linkedin" in blocker.casefold()
                                for blocker in details.get("blockers", [])
                            )
                            captcha_blocked = any(
                                "human verification" in blocker.casefold()
                                for blocker in details.get("blockers", [])
                            )
                            current_url = page.url.casefold()
                            login_in_progress = any(
                                marker in current_url
                                for marker in (
                                    "/login",
                                    "/checkpoint/",
                                    "/authwall",
                                    "accounts.google.com",
                                )
                            )
                            if linkedin_blocked and not login_in_progress:
                                details = prepare()
                                if session.status == "unavailable":
                                    break
                                if session.status == "ready_to_submit":
                                    session._commands.put(("submit", {}))
                            elif captcha_blocked:
                                try:
                                    current_body = page.locator("body").inner_text().casefold()
                                except Exception:
                                    current_body = ""
                                challenge_url = any(
                                    marker in current_url
                                    for marker in ("/checkpoint/", "/challenge/", "/captcha/")
                                )
                                if (
                                    current_body
                                    and not any(term in current_body for term in _CAPTCHA_TERMS)
                                    and not challenge_url
                                ):
                                    details = prepare(navigate=False)
                                    if session.status == "unavailable":
                                        break
                                    if session.status == "ready_to_submit":
                                        session._commands.put(("submit", {}))
                        continue
                    if command == "close":
                        session.update("closed", "Application session closed.")
                        break
                    if command == "retry":
                        self._remember_answers(session, values)
                        details = prepare()
                        if session.auto_submit and session.status == "ready_to_submit":
                            session._commands.put(("submit", {}))
                        continue
                    if command == "submit" and session.status == "ready_to_submit":
                        submit = _visible_submit_locator(page)
                        if submit is None:
                            session.update(
                                "needs_review",
                                "The application submit button is no longer visible. Review the browser and retry.",
                                details,
                            )
                            continue
                        previous_url = page.url.casefold()
                        submit.click(timeout=10_000)
                        try:
                            page.wait_for_load_state("domcontentloaded", timeout=10_000)
                        except PlaywrightTimeoutError:
                            pass
                        confirmed = False
                        for _ in range(10):
                            if _submission_confirmed(page, previous_url):
                                confirmed = True
                                break
                            page.wait_for_timeout(500)
                        if confirmed:
                            session.update("submitted", "The application was submitted and confirmed.", details)
                            if not session.visible:
                                break
                        else:
                            details = prepare(navigate=False)
                            if session.status == "ready_to_submit":
                                session.update(
                                    "needs_review",
                                    "Submit was clicked, but the site did not show a reliable confirmation. Review the visible browser before retrying.",
                                    details,
                                )
                terminal_statuses = {"submitted", "closed", "failed", "expired", "unavailable"}
                if time.time() >= deadline and session.status not in terminal_statuses:
                    session.update("expired", "Application session expired without submission.", details)
                elif not browser.is_connected() and session.status not in terminal_statuses:
                    session.update("closed", "The application browser was closed.", details)
                try:
                    context.close()
                except Exception:
                    pass
                if not session.visible and browser and browser.is_connected():
                    browser.close()
        except Exception as exc:
            concise = str(exc).split("Call log:")[0].strip()
            session.update("failed", f"Application automation stopped: {concise[:240]}")


application_manager = ApplicationManager()


def start_visible_application(url: str) -> None:
    """Legacy handoff retained for older callers."""
    validate_application_url(url)
    thread = threading.Thread(target=_open_only, args=(url,), daemon=True, name="playwright-application-review")
    thread.start()


def _open_only(url: str) -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(**_browser_launch_options(True))
        page = browser.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=45_000)
        deadline = time.time() + settings.APPLICATION_SESSION_TTL_MINUTES * 60
        while browser.is_connected() and time.time() < deadline:
            time.sleep(0.5)
