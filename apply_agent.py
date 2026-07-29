"""Visible Playwright handoff for human-reviewed job applications."""

from __future__ import annotations

import threading
import time

from playwright.sync_api import sync_playwright

from scrape_jobs import _browser_launch_options


def _open_application(url: str) -> None:
    """Open the page visibly and keep it available for the human to review."""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(**_browser_launch_options(live_browser=True))
        page = browser.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=45_000)
        while browser.is_connected():
            time.sleep(1)


def start_visible_application(url: str) -> None:
    thread = threading.Thread(target=_open_application, args=(url,), daemon=True, name="playwright-application-review")
    thread.start()
