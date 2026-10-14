"""Small, bounded public-web search helper for source-linked career research."""

from __future__ import annotations

import re
from html import unescape
from html.parser import HTMLParser
from urllib.parse import parse_qs, quote_plus, unquote, urlsplit

import requests


class _DuckResultParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[dict[str, str]] = []
        self._active: dict[str, str] | None = None
        self._capture = ""
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value or "" for key, value in attrs}
        classes = set(values.get("class", "").split())
        if tag == "a" and "result__a" in classes:
            self._active = {"url": values.get("href", ""), "title": "", "snippet": ""}
            self._capture = "title"
            self._parts = []
        elif self._active is not None and "result__snippet" in classes:
            self._capture = "snippet"
            self._parts = []

    def handle_endtag(self, tag: str) -> None:
        if self._active is None or not self._capture:
            return
        if self._capture == "title" and tag == "a":
            self._active["title"] = _space(" ".join(self._parts))
            self._capture = ""
            self._parts = []
        elif self._capture == "snippet" and tag in {"a", "div", "td"}:
            self._active["snippet"] = _space(" ".join(self._parts))
            if self._active.get("title") and self._active.get("url"):
                self.results.append(self._active)
            self._active = None
            self._capture = ""
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._active is not None and self._capture:
            self._parts.append(data)


def _space(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(str(value or ""))).strip()


def _unwrap(url: str) -> str:
    if url.startswith("//"):
        url = f"https:{url}"
    parsed = urlsplit(url)
    target = parse_qs(parsed.query).get("uddg", [""])[0]
    return unquote(target) if target else url


def public_search(query: str, limit: int = 6) -> list[dict[str, str]]:
    """Return visible public result metadata; never fabricate a person or opportunity."""
    try:
        response = requests.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
                ),
                "Accept-Language": "en-US,en;q=0.8",
            },
            timeout=(4, 15),
        )
        response.raise_for_status()
    except requests.RequestException:
        return []
    parser = _DuckResultParser()
    try:
        parser.feed(response.text[:1_500_000])
    except Exception:
        return []
    output: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in parser.results:
        url = _unwrap(item.get("url", ""))
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or url in seen:
            continue
        seen.add(url)
        output.append({"title": _space(item.get("title", "")), "url": url, "snippet": _space(item.get("snippet", ""))})
        if len(output) >= limit:
            break
    return output


def public_search_url(query: str) -> str:
    return f"https://duckduckgo.com/?q={quote_plus(query)}"
