"""Browser-based public job discovery using one Playwright session per run."""

from __future__ import annotations

import hashlib
import os
import re
import time
from pathlib import Path
from typing import Dict, Iterable, List
from urllib.parse import parse_qs, quote_plus, unquote, urlsplit, urlunsplit

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


class CaptchaBlockedError(RuntimeError):
    """The public search page asked for human verification."""


_CAPTCHA_TERMS = (
    "captcha",
    "verify you are human",
    "unusual traffic",
    "تحقق من أنك إنسان",
    "التحقق من أنك لست روبوت",
)

_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
_CLOSED_RESULT_TERMS = (
    "no longer accepting applications",
    "applications closed",
    "job expired",
    "لم نعد نقبل استمارات",
    "لم نعد نقبل طلبات",
    "التقديم مغلق",
)


def result_looks_inactive(title: str, snippet: str) -> bool:
    """Reject results that already advertise a closed or clearly stale vacancy."""
    text = f"{title} {snippet}".casefold().translate(_ARABIC_DIGITS)
    if any(term in text for term in _CLOSED_RESULT_TERMS):
        return True
    if re.search(r"\b\d+\s*(?:years?|yrs?)\s+ago\b", text):
        return True
    month_match = re.search(r"\b(\d+)\s*(?:months?|mos?)\s+ago\b", text)
    if month_match and int(month_match.group(1)) >= 2:
        return True
    week_match = re.search(r"\b(\d+)\s*weeks?\s+ago\b", text)
    if week_match and int(week_match.group(1)) >= 7:
        return True
    if re.search(r"(?:منذ|قبل)\s*\d+\s*(?:سنة|سنوات|عام|أعوام)", text):
        return True
    arabic_month = re.search(r"(?:منذ|قبل)\s*(\d+)\s*(?:من\s+)?(?:شهر|أشهر|الشهور)", text)
    if arabic_month and int(arabic_month.group(1)) >= 2:
        return True
    arabic_week = re.search(r"(?:منذ|قبل)\s*(\d+)\s*(?:من\s+)?(?:أسبوع|أسابيع)", text)
    return bool(arabic_week and int(arabic_week.group(1)) >= 7)


def contains_captcha(text: str) -> bool:
    normalized = text.casefold()
    return any(term in normalized for term in _CAPTCHA_TERMS)


def _wait_for_manual_captcha(page, timeout_seconds: int = 180) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        page.wait_for_timeout(1000)
        try:
            if not contains_captcha(page.locator("body").inner_text()):
                return True
        except Exception:
            continue
    return False


def _browser_launch_options(live_browser: bool = False) -> dict[str, object]:
    """Use an installed Chromium browser when the managed binary is unavailable."""
    candidates = [
        os.getenv("BROWSER_EXECUTABLE_PATH", ""),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ]
    executable = next((item for item in candidates if item and Path(item).is_file()), "")
    options: dict[str, object] = {
        "headless": not live_browser,
        "args": ["--disable-blink-features=AutomationControlled"],
    }
    if live_browser:
        options["slow_mo"] = 120
    if executable:
        options["executable_path"] = executable
    return options


def _unwrap_duckduckgo_link(link: str) -> str:
    if link.startswith("//"):
        link = f"https:{link}"
    parsed = urlsplit(link)
    destination = parse_qs(parsed.query).get("uddg", [""])[0]
    return unquote(destination) if destination else link


def _search_terms(query: str, location: str) -> tuple[str, str, str]:
    direct_social = quote_plus(
        f"site:linkedin.com/jobs/view {query} {location}"
    )
    direct_ats = quote_plus(
        f"{query} {location} "
        "(site:jobs.lever.co OR site:boards.greenhouse.io OR "
        "site:job-boards.greenhouse.io OR site:myworkdayjobs.com)"
    )
    broad = quote_plus(f"{query} jobs {location}")
    return direct_social, direct_ats, broad


def _linkedin_search_url(query: str, location: str) -> str:
    return (
        "https://www.linkedin.com/jobs/search/"
        f"?keywords={quote_plus(query)}&location={quote_plus(location)}&f_TPR=r2592000"
    )


def _clean_listing_url(url: str) -> str:
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def _extract_linkedin_results(page, query: str, location: str, max_results: int) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    cards = page.locator(".base-card")
    for index in range(min(cards.count(), max_results)):
        card = cards.nth(index)
        try:
            title_locator = card.locator(".base-search-card__title")
            link_locator = card.locator("a.base-card__full-link")
            if not title_locator.count() or not link_locator.count():
                continue
            title = title_locator.inner_text().strip()
            link = _clean_listing_url(link_locator.get_attribute("href") or "")
            company_locator = card.locator(".base-search-card__subtitle")
            location_locator = card.locator(".job-search-card__location")
            date_locator = card.locator("time")
            company = company_locator.inner_text().strip() if company_locator.count() else ""
            card_location = location_locator.inner_text().strip() if location_locator.count() else location
            posted = date_locator.inner_text().strip() if date_locator.count() else ""
            # Do not copy the search query into the job description: a query
            # containing "internship" must not relabel an ordinary full-time role.
            snippet = posted
            if (
                title
                and link.startswith(("http://", "https://"))
                and not result_looks_inactive(title, snippet)
            ):
                results.append(
                    {
                        "title": title,
                        "url": link,
                        "snippet": snippet,
                        "location": card_location or location,
                        "query": query,
                        "source": "linkedin_playwright",
                        "company": company,
                    }
                )
        except Exception:
            continue
    return results


def _extract_results(page, query: str, location: str, max_results: int) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    anchors = page.locator(".result__a")
    for index in range(min(anchors.count(), max_results)):
        anchor = anchors.nth(index)
        title = anchor.inner_text().strip()
        link = _unwrap_duckduckgo_link(anchor.get_attribute("href") or "")
        container = anchor.locator(
            "xpath=ancestor::*[contains(concat(' ', normalize-space(@class), ' '), ' result ')][1]"
        )
        snippet_locator = container.locator(".result__snippet")
        snippet = snippet_locator.inner_text().strip() if snippet_locator.count() else ""
        company = ""
        hiring_match = re.match(r"^(.*?)\s+hiring\s+(.*?)\s+in\s+.+$", title, flags=re.IGNORECASE)
        if hiring_match:
            company = hiring_match.group(1).strip()
            title = hiring_match.group(2).strip()
        title = re.sub(r"\s*[-|]\s*LinkedIn\s*$", "", title, flags=re.IGNORECASE).strip()
        if (
            title
            and link.startswith(("http://", "https://"))
            and not result_looks_inactive(title, snippet)
        ):
            results.append(
                {
                    "title": title,
                    "url": link,
                    "snippet": snippet,
                    "location": location,
                    "query": query,
                    "source": "duckduckgo_playwright",
                    "company": company,
                }
            )
    return results


def scrape_jobs_for_queries(
    queries: Iterable[str],
    location: str,
    max_results_per_query: int = 10,
    live_browser: bool = False,
) -> List[Dict[str, str]]:
    """Search all queries in one browser so live mode is stable and observable."""
    unique: dict[str, Dict[str, str]] = {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(**_browser_launch_options(live_browser))
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
            ),
            viewport={"width": 1360, "height": 900},
            locale="en-US",
        )
        page = context.new_page()
        try:
            for query in list(dict.fromkeys(item.strip() for item in queries if item.strip())):
                page.goto(
                    _linkedin_search_url(query, location),
                    wait_until="domcontentloaded",
                    timeout=35_000,
                )
                page_text = page.locator("body").inner_text().casefold()
                if contains_captcha(page_text):
                    if live_browser and _wait_for_manual_captcha(page):
                        page_text = page.locator("body").inner_text().casefold()
                    else:
                        raise CaptchaBlockedError(
                            "LinkedIn requested human verification. Solve it in live discovery and Jobflow "
                            "will continue automatically."
                        )
                query_results = _extract_linkedin_results(page, query, location, max_results_per_query)
                if not query_results:
                    for search_term in _search_terms(query, location):
                        page.goto(
                            f"https://html.duckduckgo.com/html/?q={search_term}&df=m",
                            wait_until="domcontentloaded",
                            timeout=35_000,
                        )
                        page_text = page.locator("body").inner_text().casefold()
                        if contains_captcha(page_text):
                            continue
                        query_results = _extract_results(page, query, location, max_results_per_query)
                        if query_results:
                            break
                for item in query_results:
                    unique[item["url"]] = item
        except PlaywrightTimeoutError:
            # Return partial results gathered before a slow source timed out.
            pass
        finally:
            context.close()
            browser.close()
    return list(unique.values())


def scrape_jobs_with_playwright(
    query: str,
    location: str,
    max_results: int = 10,
    live_browser: bool = False,
) -> List[Dict[str, str]]:
    """Backward-compatible single-query wrapper."""
    return scrape_jobs_for_queries([query], location, max_results, live_browser)


def stable_job_id(url: str, fallback: str) -> str:
    payload = (url or fallback).encode("utf-8")
    return f"playwright-{hashlib.sha256(payload).hexdigest()[:20]}"
