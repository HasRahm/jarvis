"""
web_search — live knowledge tool (Phase 27).

Lets Jarvis pull information from beyond its training cutoff: new technology,
library versions, prices, releases, news, current events.

Backend priority:
  1. TAVILY_API_KEY  -> Tavily Search API (structured, high quality)
  2. BRAVE_API_KEY   -> Brave Search API
  3. (no key)        -> DuckDuckGo HTML endpoint (no signup, no dependency)

Returns a compact numbered list of {title, url, snippet}. Never raises — on any
failure it returns a descriptive string so the model can pick another approach.
"""
import sys
from core.trace import trace as _jtrace

import os
import re
import html
import logging
from html.parser import HTMLParser
from urllib.parse import unquote

import httpx

logger = logging.getLogger(__name__)

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
_TIMEOUT = 15.0


def web_search(query: str, max_results: int = 5) -> str:
    """Search the web for current information. Returns a numbered result list as a string."""
    _jtrace(f"[TRACE] tools.web_search.web_search: enter")
    query = (query or "").strip()
    if not query:
        return "[web_search] empty query."

    max_results = max(1, min(int(max_results or 5), 10))

    try:
        if os.environ.get("TAVILY_API_KEY"):
            results = _search_tavily(query, max_results)
        elif os.environ.get("BRAVE_API_KEY"):
            results = _search_brave(query, max_results)
        else:
            results = _search_duckduckgo(query, max_results)
    except Exception as e:
        _jtrace(f"[TRACE] tools.web_search.web_search: except {str(e)[:80]}")
        logger.warning(f"[web_search] backend failed: {e}")
        return f"[web_search] unavailable: {e}"

    if not results:
        return f"[web_search] no results for: {query}"

    lines = [f"Web search results for: {query}\n"]
    for i, r in enumerate(results, 1):
        title = r.get("title", "").strip() or "(untitled)"
        url = r.get("url", "").strip()
        snippet = r.get("snippet", "").strip()
        lines.append(f"{i}. {title}\n   {url}\n   {snippet}".rstrip())
    return "\n".join(lines)


# ── DuckDuckGo (default, no key) ─────────────────────────────────────────────

class _DDGParser(HTMLParser):
    """Minimal parser for DuckDuckGo HTML results — defensive against markup drift."""

    def __init__(self):
        super().__init__()
        self.results = []
        self._in_result_link = False
        self._in_snippet = False
        self._cur_url = ""
        self._cur_title_parts = []
        self._cur_snippet_parts = []

    def handle_starttag(self, tag, attrs):
        _jtrace(f"[TRACE] tools.web_search._DDGParser.handle_starttag: enter")
        d = dict(attrs)
        cls = d.get("class", "")
        if tag == "a" and "result__a" in cls:
            self._in_result_link = True
            self._cur_url = self._clean_url(d.get("href", ""))
            self._cur_title_parts = []
        elif tag == "a" and "result__snippet" in cls:
            self._in_snippet = True
            self._cur_snippet_parts = []

    def handle_endtag(self, tag):
        if tag == "a" and self._in_result_link:
            self._in_result_link = False
            title = "".join(self._cur_title_parts).strip()
            if self._cur_url and title:
                self.results.append({
                    "title": html.unescape(title),
                    "url": self._cur_url,
                    "snippet": "",
                })
        elif tag == "a" and self._in_snippet:
            self._in_snippet = False
            snippet = html.unescape("".join(self._cur_snippet_parts).strip())
            if self.results:
                self.results[-1]["snippet"] = snippet

    def handle_data(self, data):
        if self._in_result_link:
            self._cur_title_parts.append(data)
        elif self._in_snippet:
            self._cur_snippet_parts.append(data)

    @staticmethod
    def _clean_url(href: str) -> str:
        # DuckDuckGo wraps results as /l/?uddg=<encoded-real-url>
        m = re.search(r"uddg=([^&]+)", href or "")
        if m:
            return unquote(m.group(1))
        if href and href.startswith("//"):
            return "https:" + href
        return href or ""


def _search_duckduckgo(query: str, max_results: int) -> list[dict]:
    _jtrace(f"[TRACE] tools.web_search._search_duckduckgo: enter")
    resp = httpx.get(
        "https://html.duckduckgo.com/html/",
        params={"q": query},
        headers={"User-Agent": _UA},
        timeout=_TIMEOUT,
        follow_redirects=True,
    )
    resp.raise_for_status()
    parser = _DDGParser()
    parser.feed(resp.text)
    return parser.results[:max_results]


# ── Tavily (optional, keyed) ─────────────────────────────────────────────────

def _search_tavily(query: str, max_results: int) -> list[dict]:
    _jtrace(f"[TRACE] tools.web_search._search_tavily: enter")
    resp = httpx.post(
        "https://api.tavily.com/search",
        json={
            "api_key": os.environ["TAVILY_API_KEY"],
            "query": query,
            "max_results": max_results,
        },
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    return [
        {"title": r.get("title", ""), "url": r.get("url", ""), "snippet": r.get("content", "")}
        for r in data.get("results", [])
    ][:max_results]


# ── Brave (optional, keyed) ──────────────────────────────────────────────────

def _search_brave(query: str, max_results: int) -> list[dict]:
    _jtrace(f"[TRACE] tools.web_search._search_brave: enter")
    resp = httpx.get(
        "https://api.search.brave.com/res/v1/web/search",
        params={"q": query, "count": max_results},
        headers={
            "Accept": "application/json",
            "X-Subscription-Token": os.environ["BRAVE_API_KEY"],
        },
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    return [
        {"title": r.get("title", ""), "url": r.get("url", ""), "snippet": r.get("description", "")}
        for r in data.get("web", {}).get("results", [])
    ][:max_results]
