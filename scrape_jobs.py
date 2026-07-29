"""Free, browser-based job discovery using Playwright."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Dict, List
from urllib.parse import parse_qs, quote_plus, unquote, urlsplit

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


class CaptchaBlockedError(RuntimeError):
    """The public search page asked for human verification."""


def scrape_jobs_with_playwright(query: str, location: str, max_results: int = 10, live_browser: bool = False) -> List[Dict[str, str]]:
    """Return public DuckDuckGo job-search results without an API key.

    Search engines change markup occasionally, so this function returns an empty
    list rather than bringing down the LangGraph run when a page is blocked or a
    result selector changes.
    """
    # First prefer individual job routes. If that returns nothing, retain a
    # broad public search as a review-only fallback instead of showing no jobs.
    focused_term = quote_plus(
        f'"{query}" {location} '
        '(site:linkedin.com/jobs/view OR site:wuzzuf.net/jobs/p OR '
        'site:boards.greenhouse.io/jobs OR site:jobs.lever.co)'
    )
    fallback_term = quote_plus(f"{query} jobs {location}")
    results: List[Dict[str, str]] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(**_browser_launch_options(live_browser))
        page = browser.new_page(user_agent="Mozilla/5.0 (compatible; JobMatcher/1.0)")
        try:
            for search_term in (focused_term, fallback_term):
                page.goto(f"https://html.duckduckgo.com/html/?q={search_term}", wait_until="domcontentloaded", timeout=30_000)
                page_text = page.locator("body").inner_text().lower()
                if any(phrase in page_text for phrase in ("captcha", "verify you are human", "unusual traffic")):
                    raise CaptchaBlockedError("CAPTCHA encountered while searching. Turn off 'Watch browser live' and retry in background mode.")
                if not page.locator(".result__a").count():
                    continue
                for anchor in page.locator(".result__a").all()[:max_results]:
                    title = anchor.inner_text().strip()
                    link = _unwrap_duckduckgo_link(anchor.get_attribute("href") or "")
                    result = anchor.locator("xpath=ancestor::*[contains(@class, 'result')][1]")
                    snippet = result.locator(".result__snippet").inner_text().strip() if result.locator(".result__snippet").count() else ""
                    if title and link:
                        results.append({"title": title, "url": link, "snippet": snippet, "location": location})
                if results:
                    break
        except PlaywrightTimeoutError:
            return []
        finally:
            browser.close()

    return results


def _browser_launch_options(live_browser: bool = False) -> dict[str, object]:
    """Use an installed Chrome when Playwright's managed binary is unavailable."""
    candidates = [
        os.getenv("BROWSER_EXECUTABLE_PATH", ""),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ]
    executable = next((item for item in candidates if item and Path(item).is_file()), "")
    return {"headless": not live_browser, **({"executable_path": executable} if executable else {})}


def _unwrap_duckduckgo_link(link: str) -> str:
    """Store the destination URL rather than DuckDuckGo's tracking redirect."""
    if link.startswith("//"):
        link = f"https:{link}"
    parsed = urlsplit(link)
    destination = parse_qs(parsed.query).get("uddg", [""])[0]
    return unquote(destination) if destination else link


def stable_job_id(url: str, fallback: str) -> str:
    """Stable IDs make the long-term de-duplication memory effective across runs."""
    payload = (url or fallback).encode("utf-8")
    return f"playwright-{hashlib.sha256(payload).hexdigest()[:20]}"
