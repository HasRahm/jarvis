"""
Element Graph — spatial map of interactive elements (Phase 28b).

Wraps the accessibility-tree cache that desktop_get_ui_tree already writes
(scratch/desktop_ui_cache.json) into a node/edge graph, and locates elements by
natural-language description using the existing token-overlap scorer (no embeddings,
no extra deps). Lets the agent navigate to elements by coordinates instead of blind
pixel guessing.
"""
import sys
from core.trace import trace as _jtrace

import os
import json
import math
import logging

logger = logging.getLogger(__name__)

_CACHE_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "scratch", "desktop_ui_cache.json",
)
_EDGE_MAX_DIST = 150.0  # px — nearby elements are connected
_FIND_THRESHOLD = 0.5


def _load_cache() -> list[dict]:
    try:
        with open(_CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        _jtrace(f"[TRACE] core.system.element_graph._load_cache: except Exception")
        return []


def build_graph(refresh: bool = True) -> dict:
    """Build a spatial element graph of the active window.

    nodes = interactive elements with center coords (cx, cy);
    edges = pairs of nodes within ~150px of each other.
    """
    _jtrace(f"[TRACE] core.system.element_graph.build_graph: enter")
    if refresh and os.environ.get("JARVIS_CI") != "true":
        try:
            from tools.desktop_ui_tree import desktop_get_ui_tree
            desktop_get_ui_tree()  # repopulates the cache file
        except Exception as e:
            _jtrace(f"[TRACE] core.system.element_graph.build_graph: except {str(e)[:80]}")
            logger.warning(f"[element_graph] tree refresh failed: {e}")

    raw = _load_cache()
    nodes = []
    for el in raw:
        try:
            cx = el["x"] + el["w"] // 2
            cy = el["y"] + el["h"] // 2
        except Exception:
            _jtrace(f"[TRACE] core.system.element_graph.build_graph: except Exception")
            continue
        nodes.append({
            "index": el.get("index"),
            "name": el.get("name", ""),
            "role": el.get("role", ""),
            "auto_id": el.get("auto_id", ""),
            "is_enabled": el.get("is_enabled", True),
            "x": el.get("x"), "y": el.get("y"),
            "w": el.get("w"), "h": el.get("h"),
            "cx": cx, "cy": cy,
        })

    edges = []
    for i in range(len(nodes)):
        for j in range(i + 1, len(nodes)):
            dist = math.hypot(nodes[i]["cx"] - nodes[j]["cx"],
                              nodes[i]["cy"] - nodes[j]["cy"])
            if dist < _EDGE_MAX_DIST:
                edges.append({"from": nodes[i]["index"], "to": nodes[j]["index"],
                              "distance": round(dist, 1)})

    return {"nodes": nodes, "edges": edges}


def find_element(description: str, refresh: bool = True) -> dict | None:
    """Return the best element matching *description*, or None if none clears the threshold."""
    _jtrace(f"[TRACE] core.system.element_graph.find_element: enter")
    description = (description or "").strip()
    if not description:
        return None

    graph = build_graph(refresh=refresh)
    try:
        from tools.virtual_input import score_element
    except Exception as e:
        _jtrace(f"[TRACE] core.system.element_graph.find_element: except {str(e)[:80]}")
        logger.warning(f"[element_graph] scorer unavailable: {e}")
        return None

    best, best_score = None, 0.0
    for node in graph["nodes"]:
        score = score_element(node, description)
        if score > best_score:
            best, best_score = node, score

    if best and best_score >= _FIND_THRESHOLD:
        result = dict(best)
        result["match_score"] = round(best_score, 3)
        return result
    return None


def element_graph_tool(description: str | None = None, refresh: bool = True) -> str:
    """Tool entry: with a description -> matched element + coords; without -> node list."""
    _jtrace(f"[TRACE] core.system.element_graph.element_graph_tool: enter")
    if description:
        match = find_element(description, refresh=refresh)
        if match:
            return json.dumps({"found": True, "element": match}, indent=2)
        return json.dumps({"found": False, "description": description,
                           "hint": "No element matched. Try visual_click for canvas/WebGL UIs."})
    graph = build_graph(refresh=refresh)
    compact = [
        {"index": n["index"], "role": n["role"], "name": n["name"],
         "cx": n["cx"], "cy": n["cy"]}
        for n in graph["nodes"][:100]
    ]
    return json.dumps({"count": len(graph["nodes"]), "elements": compact}, indent=2)
