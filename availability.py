"""Fast, cached vacancy availability checks used before jobs reach the board."""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Iterable
from urllib.parse import urlsplit

import requests


UNAVAILABLE_TERMS = (
    "no longer accepting applications",
    "this job is no longer available",
    "applications are closed",
    "position has been filled",
    "job has expired",
    "لم نعد نقبل استمارات",
    "لم نعد نقبل طلبات",
    "لم يعد يقبل طلبات",
    "لم يعد هذا الإعلان متاح",
    "التقديم مغلق",
    "انتهت صلاحية الوظيفة",
)
_CACHE_TTL_SECONDS = 10 * 60
_cache: dict[str, tuple[float, bool | None]] = {}
_cache_lock = threading.RLock()


def text_indicates_unavailable(text: str) -> bool:
    normalized = text.casefold()
    return any(term in normalized for term in UNAVAILABLE_TERMS)


def probe_application_url(url: str) -> bool | None:
    """Return False for a confirmed closed URL, True for a live response, None on uncertainty."""
    now = time.monotonic()
    with _cache_lock:
        cached = _cache.get(url)
        if cached and now - cached[0] < _CACHE_TTL_SECONDS:
            return cached[1]
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    result: bool | None
    try:
        response = requests.get(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
                ),
                "Accept-Language": "en-US,en;q=0.9,ar;q=0.7",
            },
            timeout=(4, 10),
            allow_redirects=True,
        )
        if response.status_code in {404, 410}:
            result = False
        elif response.status_code >= 500 or response.status_code in {401, 403, 429, 999}:
            result = None
        else:
            decoded_variants = [response.text]
            try:
                decoded_variants.append(response.content.decode("utf-8"))
            except UnicodeDecodeError:
                pass
            result = not any(text_indicates_unavailable(text) for text in decoded_variants)
    except requests.RequestException:
        result = None
    with _cache_lock:
        _cache[url] = (now, result)
    return result


def probe_application_urls(urls: Iterable[str]) -> dict[str, bool | None]:
    unique = list(dict.fromkeys(url for url in urls if url))
    if not unique:
        return {}
    results: dict[str, bool | None] = {}
    with ThreadPoolExecutor(max_workers=min(6, len(unique))) as pool:
        futures = {pool.submit(probe_application_url, url): url for url in unique}
        for future in as_completed(futures):
            url = futures[future]
            try:
                results[url] = future.result()
            except Exception:
                results[url] = None
    return results
