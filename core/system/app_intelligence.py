"""
App Intelligence — self-building app knowledge base (Phase 28b).

First encounter with an app: passively explore its structure (accessibility tree +
density zones) and synthesize a concise guide, stored permanently in GBrain. Every
encounter after: recall the guide in milliseconds. Over time Jarvis becomes an expert
on every app on the machine without anyone writing a guide by hand.

PASSIVE by default — exploration only READS the screen. Active probing (sending
shortcuts, clicking menus) has side effects and is gated behind explore_active=True
(deferred, off by default). Never raises.
"""
import sys
from core.trace import trace as _jtrace

import os
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def _guide_slug(app_name: str) -> str:
    return f"apps/{app_name.strip().lower().replace(' ', '_')}/guide"


def get_app_guide(app_name: str) -> str:
    """Return a stored guide from GBrain, or build + persist one on first encounter."""
    _jtrace(f"[TRACE] core.system.app_intelligence.get_app_guide: enter")
    app_name = (app_name or "").strip()
    if not app_name:
        return "[app_guide] no app name provided."

    slug = _guide_slug(app_name)

    # 1. Recall
    try:
        from brain.get import brain_get
        existing = brain_get(slug)
        if existing and existing.strip():
            return existing
    except Exception as e:
        _jtrace(f"[TRACE] core.system.app_intelligence.get_app_guide: except {str(e)[:80]}")
        logger.warning(f"[app_intel] recall failed: {e}")

    # 2. First encounter — explore + synthesize
    structure = explore_app(app_name)
    guide = _synthesize_guide(app_name, structure)

    # 3. Persist (synchronous so the next recall sees it)
    try:
        from brain.supabase_store import mem_upsert
        mem_upsert(slug, guide)
        logger.info(f"[app_intel] stored guide: {slug}")
    except Exception as e:
        _jtrace(f"[TRACE] core.system.app_intelligence.get_app_guide: except {str(e)[:80]}")
        logger.warning(f"[app_intel] persist failed: {e}")

    return guide


def explore_app(app_name: str, explore_active: bool = False) -> dict:
    """PASSIVE structural read of the active app. Active probing deferred (off)."""
    _jtrace(f"[TRACE] core.system.app_intelligence.explore_app: enter")
    structure = {
        "app": app_name,
        "explored_at": datetime.now().isoformat(),
        "key_elements": [],
        "visual_zones": {},
    }

    if os.environ.get("JARVIS_CI") == "true":
        return structure

    # Accessibility tree -> key interactive elements
    try:
        from core.system.element_graph import build_graph
        graph = build_graph(refresh=True)
        structure["key_elements"] = [
            {"role": n["role"], "name": n["name"], "cx": n["cx"], "cy": n["cy"]}
            for n in graph["nodes"][:40] if n.get("name")
        ]
    except Exception as e:
        _jtrace(f"[TRACE] core.system.app_intelligence.explore_app: except {str(e)[:80]}")
        logger.warning(f"[app_intel] tree read failed: {e}")

    # Density zones -> rough layout
    try:
        from core.system.screen_imprint import ScreenImprintGraph
        result = ScreenImprintGraph().imprint()
        imp = result.get("imprint", {})
        structure["visual_zones"] = {
            "resolution": imp.get("resolution"),
            "grid_dims": imp.get("grid_dims"),
            "has_density_map": bool(imp.get("ascii_map")),
        }
    except Exception as e:
        _jtrace(f"[TRACE] core.system.app_intelligence.explore_app: except {str(e)[:80]}")
        logger.warning(f"[app_intel] density read failed: {e}")

    # Active probing intentionally NOT performed unless explicitly enabled.
    if explore_active:
        logger.info("[app_intel] explore_active requested but deferred in this phase.")

    return structure


def _synthesize_guide(app_name: str, structure: dict) -> str:
    """Ask the orchestrator model to write a concise (<300-word) usage guide."""
    _jtrace(f"[TRACE] core.system.app_intelligence._synthesize_guide: enter")
    if os.environ.get("JARVIS_CI") == "true":
        return (f"# Guide: {app_name}\n"
                f"(CI stub) Use desktop_get_ui_tree / element_graph to locate elements, "
                f"read_screen_text for text, and verify_outcome after actions.")

    try:
        from core.system.llm_adapter import call_llm
        from agents.model_router import get_model
        prompt = (
            f'I explored the app "{app_name}". Here is its structure:\n'
            f'{json.dumps(structure, indent=2)[:4000]}\n\n'
            f"Write a concise guide (UNDER 300 words) telling an AI agent how to use "
            f"this app: how to navigate, how to perform the most common actions, and "
            f"what to do if lost. Be concrete and practical."
        )
        result = call_llm(messages=[{"role": "user", "content": prompt}],
                          model=get_model("orchestrator"))
        guide = (result.get("content") if isinstance(result, dict) else str(result)) or ""
        guide = guide.strip()
        return guide or f"# Guide: {app_name}\n(No synthesis available — explore with desktop_get_ui_tree.)"
    except Exception as e:
        _jtrace(f"[TRACE] core.system.app_intelligence._synthesize_guide: except {str(e)[:80]}")
        logger.warning(f"[app_intel] synthesis failed: {e}")
        return (f"# Guide: {app_name}\n"
                f"Use desktop_get_ui_tree / element_graph to locate elements, "
                f"read_screen_text for text, verify_outcome after actions.")
