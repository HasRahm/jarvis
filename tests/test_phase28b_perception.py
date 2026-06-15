"""
Phase 28b — Perception Layer: App Intelligence, Element Graph, Clipboard Read, App Resolver

CI-safe tests (mock win32/clipboard/tree/brain; no real screen, GUI, or network):
- clipboard_reader: safe-app reads + restores; unsafe-app marker; graceful on no win32
- element_graph: build_graph nodes/edges over a seeded cache; find_element picks best
- app_resolver: is_installed via mocked which; resolve alternatives + API fallback
- app_intelligence: recall stored guide; CI explore stub + persist
- all three tools registered + cortex-exempt
"""

import os
import sys
import json
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── Clipboard Reader ─────────────────────────────────────────────────────────

def test_read_screen_text_unsafe_app(monkeypatch):
    import tools.clipboard_reader as cr
    monkeypatch.setattr(cr, "_focused_process_name", lambda: "explorer")
    result = cr.read_screen_text()
    assert "[clipboard]" in result
    assert "unsafe" in result.lower()


def test_read_screen_text_no_focus(monkeypatch):
    import tools.clipboard_reader as cr
    monkeypatch.setattr(cr, "_focused_process_name", lambda: "")
    result = cr.read_screen_text()
    assert "[clipboard]" in result


def test_read_screen_text_safe_app_reads_and_restores(monkeypatch):
    import tools.clipboard_reader as cr
    monkeypatch.setattr(cr, "_focused_process_name", lambda: "notepad")

    clip = {"value": "ORIGINAL"}
    reads = {"n": 0}

    def fake_read():
        # first read = save original; second read (after copy) = the captured page text
        reads["n"] += 1
        return clip["value"] if reads["n"] == 1 else "PAGE TEXT"

    restored = {}
    monkeypatch.setattr(cr, "_read_clipboard_text", fake_read)
    monkeypatch.setattr(cr, "_set_clipboard_text", lambda t: restored.setdefault("v", t))

    import tools.desktop_automation as da
    monkeypatch.setattr(da, "desktop_press_keys", lambda keys: "ok")

    result = cr.read_screen_text()
    assert result == "PAGE TEXT"
    assert restored["v"] == "ORIGINAL"  # prior clipboard restored


# ── Element Graph ────────────────────────────────────────────────────────────

_FAKE_ELEMENTS = [
    {"index": 0, "name": "Search", "role": "Edit", "x": 100, "y": 50, "w": 200, "h": 30, "auto_id": "search", "is_enabled": True},
    {"index": 1, "name": "Go", "role": "Button", "x": 320, "y": 50, "w": 40, "h": 30, "auto_id": "", "is_enabled": True},
    {"index": 2, "name": "Settings", "role": "Button", "x": 100, "y": 900, "w": 80, "h": 30, "auto_id": "", "is_enabled": True},
]


@pytest.fixture
def seeded_cache(tmp_path, monkeypatch):
    cache = tmp_path / "desktop_ui_cache.json"
    cache.write_text(json.dumps(_FAKE_ELEMENTS), encoding="utf-8")
    import core.system.element_graph as eg
    monkeypatch.setattr(eg, "_CACHE_FILE", str(cache))
    return eg


def test_build_graph_nodes_and_edges(seeded_cache):
    graph = seeded_cache.build_graph(refresh=False)
    assert len(graph["nodes"]) == 3
    # Search (215,65) and Go (340,65) are ~125px apart -> edge; Settings far below -> none to it
    assert any({e["from"], e["to"]} == {0, 1} for e in graph["edges"])
    assert not any(2 in (e["from"], e["to"]) for e in graph["edges"])


def test_find_element_picks_search(seeded_cache):
    match = seeded_cache.find_element("search box", refresh=False)
    assert match is not None
    assert match["name"] == "Search"
    assert match["cx"] == 200 and match["cy"] == 65


def test_find_element_no_match(seeded_cache):
    assert seeded_cache.find_element("nonexistent purple widget", refresh=False) is None


# ── App Resolver ─────────────────────────────────────────────────────────────

def test_is_installed_via_path(monkeypatch):
    import core.system.app_resolver as ar
    monkeypatch.setattr(ar.shutil, "which", lambda exe: "C:\\fake\\code.exe" if exe == "code" else None)
    assert ar.is_installed("code") is True


def test_resolve_native_when_installed(monkeypatch):
    import core.system.app_resolver as ar
    monkeypatch.setattr(ar, "is_installed", lambda name: name == "excel")
    res = ar.resolve("excel")
    assert res["method"] == "native_app"


def test_resolve_browser_fallback_when_missing(monkeypatch):
    import core.system.app_resolver as ar
    monkeypatch.setattr(ar, "is_installed", lambda name: False)
    monkeypatch.delenv("FIGMA_MCP_TOKEN", raising=False)
    res = ar.resolve("excel")
    assert res["method"] == "browser"
    assert "sheets.google.com" in res["url"]


def test_resolve_api_when_key_present(monkeypatch):
    import core.system.app_resolver as ar
    monkeypatch.setattr(ar, "is_installed", lambda name: False)
    monkeypatch.setenv("FIGMA_MCP_TOKEN", "tok")
    res = ar.resolve("figma")
    assert res["method"] == "api"
    assert res["client"] == "FigmaAPIClient"


def test_resolve_unknown_app_web_search(monkeypatch):
    import core.system.app_resolver as ar
    monkeypatch.setattr(ar, "is_installed", lambda name: False)
    res = ar.resolve("some-obscure-app")
    assert res["method"] == "web_search"


# ── App Intelligence ─────────────────────────────────────────────────────────

def test_get_app_guide_recall(monkeypatch):
    import core.system.app_intelligence as ai
    import brain.get as bg
    monkeypatch.setattr(bg, "brain_get", lambda slug: "# Stored guide for Figma\nUse the canvas.")
    guide = ai.get_app_guide("Figma")
    assert "Stored guide" in guide


def test_get_app_guide_builds_when_absent(monkeypatch):
    monkeypatch.setenv("JARVIS_CI", "true")
    import core.system.app_intelligence as ai
    import brain.get as bg
    monkeypatch.setattr(bg, "brain_get", lambda slug: "")
    persisted = {}
    import brain.supabase_store as ss
    monkeypatch.setattr(ss, "mem_upsert", lambda slug, content: persisted.setdefault(slug, content) or True)
    guide = ai.get_app_guide("BrandNewApp")
    assert "BrandNewApp" in guide
    assert any("brandnewapp" in k for k in persisted)  # persisted under apps/<name>/guide


# ── Tool registration ────────────────────────────────────────────────────────

def test_perception_tools_registered():
    from tools.dispatcher import TOOL_DEFINITIONS
    names = {t["function"]["name"] for t in TOOL_DEFINITIONS}
    for n in ("read_screen_text", "element_graph", "app_guide"):
        assert n in names


def test_perception_tools_cortex_exempt():
    import inspect
    import tools.dispatcher as disp
    src = inspect.getsource(disp.dispatch)
    for n in ("read_screen_text", "element_graph", "app_guide"):
        assert f'"{n}"' in src
