"""Visible Playwright auto-fill sessions with explicit, auditable submission."""

from __future__ import annotations

import queue
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from availability import UNAVAILABLE_TERMS
from config import settings
from document_store import get_cv_pdf_path
from scrape_jobs import _browser_launch_options


_BROWSER_PROFILE = Path(__file__).resolve().parent / "memory" / "browser_profiles" / "job-accounts"
_CAPTCHA_TERMS = (
    "captcha",
    "verify you are human",
    "recaptcha",
    "تحقق من أنك إنسان",
    "التحقق من أنك لست روبوت",
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


def _matching_value(field_key: str, values: dict[str, str], answers: dict[str, str]) -> str:
    normalized_field = re.sub(r"[^a-z0-9]+", " ", field_key.casefold()).strip()
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
) -> dict[str, Any]:
    values = _profile_values(profile)
    answers = answers or {}
    filled: list[str] = []
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
        "input:not([type=hidden]):not([type=file]):not([type=submit]):not([type=button]):not([type=password]), textarea"
    )
    for index in range(fields.count()):
        field = fields.nth(index)
        try:
            if not field.is_visible() or field.is_disabled() or field.input_value().strip():
                continue
            label = _field_label(field)
            key = f"{_field_key(field)} {label}"
            value = _matching_value(key, values, answers)
            if value:
                field.fill(value)
                filled.append(label or f"field {index + 1}")
        except Exception:
            continue

    missing: list[str] = []
    required = page.locator(
        "input[required]:not([type=hidden]):not([type=password]), textarea[required], select[required]"
    )
    for index in range(required.count()):
        field = required.nth(index)
        try:
            if not field.is_visible():
                continue
            tag = field.evaluate("(element) => element.tagName.toLowerCase()")
            field_type = (field.get_attribute("type") or "").casefold()
            if field_type == "radio":
                value = field.evaluate(
                    """element => Array.from(document.getElementsByName(element.name))
                        .some(candidate => candidate.checked)"""
                )
            elif field_type == "checkbox":
                value = field.is_checked()
            else:
                value = (
                    field.input_value()
                    if tag != "select"
                    else field.locator("option:checked").get_attribute("value")
                )
            if not value:
                missing.append(_field_label(field) or f"Required field {index + 1}")
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
    if "linkedin.com" in page.url.casefold() and not uploaded and any(
        term in body for term in ("sign in", "join now")
    ):
        blocked.append("Sign in to LinkedIn once in the visible browser, then press retry.")
    submit = _visible_submit_locator(page)
    return {
        "filled_fields": list(dict.fromkeys(filled)),
        "cv_uploaded": uploaded,
        "missing_required": list(dict.fromkeys(missing)),
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


@dataclass
class ApplicationSession:
    id: str
    url: str
    document_id: str
    profile: dict[str, Any]
    auto_submit: bool = False
    visible: bool = True
    answers: dict[str, str] = field(default_factory=dict)
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
            }

    def update(self, status: str, message: str, details: dict[str, Any] | None = None) -> None:
        with self._lock:
            self.status = status
            self.message = message
            if details is not None:
                self.details = details


class ApplicationManager:
    def __init__(self) -> None:
        self._sessions: dict[str, ApplicationSession] = {}
        self._lock = threading.RLock()

    def start(
        self,
        url: str,
        document_id: str,
        profile: dict[str, Any],
        *,
        auto_submit: bool = False,
        visible: bool = True,
    ) -> dict[str, Any]:
        get_cv_pdf_path(document_id)
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
            auto_submit=auto_submit,
            visible=visible,
            answers={
                str(key): str(value)
                for key, value in (profile.get("application_answers") or {}).items()
                if value
            },
        )
        with self._lock:
            if visible and any(
                item.visible
                and item.status not in {"submitted", "closed", "failed", "expired", "unavailable"}
                for item in self._sessions.values()
            ):
                raise ValueError("Close the current visible application session before starting another one.")
            self._sessions[session.id] = session
        thread = threading.Thread(
            target=self._run,
            args=(session,),
            daemon=True,
            name=f"application-{session.id[:8]}",
        )
        thread.start()
        return session.snapshot()

    def get(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            session = self._sessions.get(session_id)
        if not session:
            raise KeyError("Application session was not found.")
        return session.snapshot()

    def command(
        self,
        session_id: str,
        command: str,
        values: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            session = self._sessions.get(session_id)
        if not session:
            raise KeyError("Application session was not found.")
        if command not in {"submit", "close", "retry"}:
            raise ValueError("Command must be submit, retry, or close.")
        clean_values = {
            str(key).strip(): str(value).strip()
            for key, value in (values or {}).items()
            if str(key).strip() and str(value).strip()
        }
        session._commands.put((command, clean_values))
        return session.snapshot()

    def _run(self, session: ApplicationSession) -> None:
        try:
            with sync_playwright() as playwright:
                if session.visible:
                    _BROWSER_PROFILE.mkdir(parents=True, exist_ok=True)
                    persistent_options = _browser_launch_options(True)
                    persistent_options["args"] = [
                        *list(persistent_options.get("args", [])),
                        "--disable-features=FedCm",
                    ]
                    context = playwright.chromium.launch_persistent_context(
                        str(_BROWSER_PROFILE),
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
                    for _ in range(8):
                        prepared = _fill_page(
                            page,
                            session.document_id,
                            session.profile,
                            session.answers,
                        )
                        all_filled.extend(prepared["filled_fields"])
                        prepared["filled_fields"] = list(dict.fromkeys(all_filled))
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
                            "This job is closed, so Jobflow will not try to submit it.",
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
                                    "Jobflow will continue automatically when it is solved."
                                )
                            ),
                            prepared,
                        )
                    elif prepared["missing_required"]:
                        session.update(
                            "needs_input",
                            "Add the missing factual answers, then Jobflow can continue.",
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
                        session.answers.update(values)
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
                        submit.click(timeout=10_000)
                        try:
                            page.wait_for_load_state("domcontentloaded", timeout=10_000)
                        except PlaywrightTimeoutError:
                            pass
                        session.update("submitted", "The application form was submitted.", details)
                        if not session.visible:
                            break
                if time.time() >= deadline and session.status not in {"submitted", "closed"}:
                    session.update("expired", "Application session expired without submission.", details)
                context.close()
                if not session.visible and browser:
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
