import sys
from core.trace import trace as _jtrace
# tools/virtual_input.py
"""
Virtual Input — act on UI elements WITHOUT moving the physical mouse (Phase 24)

Uses UIAutomation control patterns (Invoke, Value.SetValue, Toggle,
ExpandCollapse, SelectionItem, LegacyIAccessible.DoDefaultAction,
SetFocus+SendKeys) so the user's mouse stays free while the agent works.
The physical pyautogui click remains the automatic fallback for surfaces
that don't expose patterns (WebGL canvas, some Electron content).

Also home to smart_fill — the graph-first showcase tool:
  GRAPH locates (UI-tree element scoring) and ACTS (virtual input);
  VISION reads/verifies (visual_click fallback + OCR check).

Phase 29: the PHYSICAL cursor is the default — clicks/typing visibly move the real
mouse so the user can see (and trust) what the agent does. Virtual UIA input (no
mouse movement) is opt-in via JARVIS_VIRTUAL_INPUT=1 for headless/no-move scenarios.
"""

import os
import json
import time
import logging

logger = logging.getLogger(__name__)


def virtual_input_enabled() -> bool:
    # Default OFF (physical cursor). Opt in to virtual UIA input with =1.
    return os.environ.get("JARVIS_VIRTUAL_INPUT", "0") == "1"


# ---------------------------------------------------------------------------
# Strategy selection (pure — unit-testable without uiautomation)
# ---------------------------------------------------------------------------

def select_strategies(role: str, action: str) -> list:
    """Ordered list of interaction strategies for a control role + action.

    "physical" is a sentinel meaning: caller should fall back to a real
    pyautogui click/type — it is never executed by this module.
    """
    _jtrace(f"[TRACE] tools.virtual_input.select_strategies: enter")
    role = (role or "").replace("Control", "").strip()
    action = (action or "click").lower()

    if action == "type":
        if role == "Document":
            # Documents are editor buffers (Notepad, Word, IDEs) — never
            # clobber existing content with SetValue/Ctrl+A; insert at cursor.
            return ["focus_sendkeys_append", "physical"]
        return ["value_pattern", "focus_sendkeys", "physical"]

    # click-like actions
    if role == "Button":
        return ["invoke", "legacy_default", "focus_enter", "physical"]
    if role == "CheckBox":
        return ["toggle", "invoke", "physical"]
    if role in ("ComboBox", "TreeItem"):
        return ["expand_collapse", "selection_item", "invoke", "physical"]
    if role in ("ListItem", "TabItem", "MenuItem", "RadioButton"):
        return ["selection_item", "invoke", "legacy_default", "physical"]
    if role in ("Edit", "Document"):
        # clicking an edit field = put focus in it
        return ["focus_only", "physical"]
    if role == "Hyperlink":
        return ["invoke", "legacy_default", "physical"]
    return ["invoke", "legacy_default", "physical"]


def score_element(el: dict, description: str) -> float:
    """Score a cached UI-tree element against a natural-language description.

    Token-overlap ratio over name + auto_id, plus a bonus for fillable roles.
    Pure function — used by smart_fill to pick the best graph match.
    """
    _jtrace(f"[TRACE] tools.virtual_input.score_element: enter")
    if not el.get("is_enabled", True):
        return 0.0
    desc_tokens = {t for t in description.lower().split() if len(t) > 1}
    if not desc_tokens:
        return 0.0
    hay = f"{el.get('name','')} {el.get('auto_id','')}".lower()
    hits = sum(1 for t in desc_tokens if t in hay)
    score = hits / len(desc_tokens)
    if el.get("role") in ("Edit", "ComboBox", "Document"):
        score += 0.3
    return score


# ---------------------------------------------------------------------------
# Live control resolution + pattern execution
# ---------------------------------------------------------------------------

def resolve_control(element: dict):
    """Re-acquire a live UIA Control for a cached element dict.

    Probes ControlFromPoint at the cached center and verifies Name or
    AutomationId still matches — detects stale caches (window moved/changed).
    Returns the Control, or None when unavailable/stale.
    """
    _jtrace(f"[TRACE] tools.virtual_input.resolve_control: enter")
    try:
        import uiautomation as auto
    except ImportError:
        _jtrace(f"[TRACE] tools.virtual_input.resolve_control: except ImportError")
        return None
    try:
        cx = element["x"] + element["w"] // 2
        cy = element["y"] + element["h"] // 2
        ctrl = auto.ControlFromPoint(cx, cy)
        if ctrl is None:
            return None
        cached_name = (element.get("name") or "").lower()
        cached_id = (element.get("auto_id") or "").lower()
        live_name = (ctrl.Name or "").lower()
        live_id = (ctrl.AutomationId or "").lower()
        if cached_name and (cached_name in live_name or live_name in cached_name):
            return ctrl
        if cached_id and cached_id == live_id:
            return ctrl
        # Walk up a couple of ancestors — ControlFromPoint often returns an
        # inner text/image child of the cached control.
        parent = ctrl
        for _ in range(2):
            parent = parent.GetParentControl()
            if parent is None:
                break
            pname = (parent.Name or "").lower()
            pid = (parent.AutomationId or "").lower()
            if cached_name and (cached_name in pname or pname in cached_name):
                return parent
            if cached_id and cached_id == pid:
                return parent
        if not cached_name and not cached_id:
            return ctrl  # nothing to verify against — trust the position
        return None
    except Exception as exc:
        _jtrace(f"[TRACE] tools.virtual_input.resolve_control: except {str(exc)[:80]}")
        logger.warning("[VirtualInput] resolve_control failed: %s", exc)
        return None


def execute_strategy(ctrl, strategy: str, text: str = None) -> tuple:
    """Attempt ONE interaction strategy on a live control.

    Returns (ok: bool, msg: str). Pattern-unsupported / COM errors return
    (False, reason) so the caller continues down the chain — never raises.
    """
    try:
        if strategy == "invoke":
            p = ctrl.GetInvokePattern()
            p.Invoke()
            return True, "InvokePattern.Invoke()"

        if strategy == "value_pattern":
            p = ctrl.GetValuePattern()
            if getattr(p, "IsReadOnly", False):
                return False, "ValuePattern is read-only"
            p.SetValue(text or "")
            return True, f"ValuePattern.SetValue({(text or '')[:30]!r})"

        if strategy == "toggle":
            ctrl.GetTogglePattern().Toggle()
            return True, "TogglePattern.Toggle()"

        if strategy == "expand_collapse":
            ctrl.GetExpandCollapsePattern().Expand()
            return True, "ExpandCollapsePattern.Expand()"

        if strategy == "selection_item":
            ctrl.GetSelectionItemPattern().Select()
            return True, "SelectionItemPattern.Select()"

        if strategy == "legacy_default":
            ctrl.GetLegacyIAccessiblePattern().DoDefaultAction()
            return True, "LegacyIAccessible.DoDefaultAction()"

        if strategy == "focus_sendkeys":
            import uiautomation as auto
            ctrl.SetFocus()
            time.sleep(0.05)
            auto.SendKeys("{Ctrl}a{Del}")
            auto.SendKeys(_escape_sendkeys(text or ""), interval=0.01)
            return True, f"SetFocus + SendKeys({(text or '')[:30]!r})"

        if strategy == "focus_sendkeys_append":
            # Insert at the current caret WITHOUT clearing — used for Document
            # controls where Ctrl+A/SetValue would destroy the user's buffer.
            import uiautomation as auto
            ctrl.SetFocus()
            time.sleep(0.05)
            auto.SendKeys(_escape_sendkeys(text or ""), interval=0.01)
            return True, f"SetFocus + SendKeys-append({(text or '')[:30]!r})"

        if strategy == "focus_enter":
            import uiautomation as auto
            ctrl.SetFocus()
            time.sleep(0.05)
            auto.SendKeys("{Enter}")
            return True, "SetFocus + Enter"

        if strategy == "focus_only":
            ctrl.SetFocus()
            return True, "SetFocus()"

        return False, f"unknown strategy '{strategy}'"
    except Exception as exc:
        _jtrace(f"[TRACE] tools.virtual_input.execute_strategy: except {str(exc)[:80]}")
        return False, f"{strategy}: {type(exc).__name__}: {exc}"


def _escape_sendkeys(text: str) -> str:
    """Escape uiautomation SendKeys special characters in literal text."""
    _jtrace(f"[TRACE] tools.virtual_input._escape_sendkeys: enter")
    out = []
    for ch in text:
        if ch in "{}()+^%~":
            out.append("{" + ch + "}")
        else:
            out.append(ch)
    return "".join(out)


def virtual_interact(element: dict, action: str = "click", text: str = None,
                     view_session=None) -> tuple:
    """Act on a cached element via UIA patterns, no physical mouse.

    Returns (ok, trace_msg, used_physical_fallback). When the third value is
    True the CALLER should perform the physical click/type — pyautogui is
    deliberately kept out of this module.
    """
    _jtrace(f"[TRACE] tools.virtual_input.virtual_interact: enter")
    from tools import agent_cursor

    trace = []
    if not virtual_input_enabled():
        return False, "virtual input disabled (JARVIS_VIRTUAL_INPUT=0)", True

    ctrl = resolve_control(element)
    if ctrl is None:
        return False, "could not resolve live control (stale cache? re-run desktop_get_ui_tree)", True

    cx = element["x"] + element["w"] // 2
    cy = element["y"] + element["h"] // 2
    agent_cursor.move_to(cx, cy)
    agent_cursor.pulse()
    if view_session is not None:
        view_session.add_match_box(element["x"], element["y"],
                                   element["w"], element["h"],
                                   element.get("name", ""))

    role = element.get("role", "")
    for strategy in select_strategies(role, action):
        if strategy == "physical":
            break
        ok, msg = execute_strategy(ctrl, strategy, text)
        trace.append(("OK " if ok else "no ") + msg)
        if ok:
            return True, "; ".join(trace), False

    return False, "; ".join(trace) or "no virtual strategies applicable", True


# ---------------------------------------------------------------------------
# smart_fill — graph locates & acts, vision reads & verifies
# ---------------------------------------------------------------------------

def smart_fill(field_description: str, text: str, window_hint: str = None,
               press_enter: bool = False) -> str:
    """Fill a form field located by description — graph-first, vision-fallback.

    1. Focus the window (window graph).
    2. Locate via UI tree: refresh desktop_get_ui_tree, score cached elements.
    3. Act via virtual input (UIA ValuePattern/SendKeys — mouse stays free);
       physical click+type only as fallback.
    4. No graph match → vision fallback: visual_click(description) + type.
    5. Verify by OCR that the text appears (soft check — password/canvas
       fields legitimately won't show it).
    """
    _jtrace(f"[TRACE] tools.virtual_input.smart_fill: enter")
    if not field_description or not field_description.strip():
        return "ERROR: smart_fill requires a non-empty 'field_description'"
    if text is None:
        return "ERROR: smart_fill requires 'text'"
    field_description = field_description.strip()

    from tools.agent_view import AgentViewSession
    session = AgentViewSession(f"smart_fill_{field_description[:20]}")
    trace = []

    # ── 1. focus window ────────────────────────────────────────────────────
    if window_hint:
        from tools.hybrid_cursor import _layer1_graph_focus
        ok, msg, _node = _layer1_graph_focus(window_hint)
        trace.append(f"Focus: {'OK' if ok else 'FAILED'} — {msg}")
        if not ok:
            session.add_note("\n".join(trace))
            session.save()
            return "[SmartFill] FAILED\n" + "\n".join(trace)
        try:
            from tools.windows import get_3d_window_graph
            session.add_window_graph(get_3d_window_graph())
        except Exception:
            _jtrace(f"[TRACE] tools.virtual_input.smart_fill: except Exception")
            pass

    # ── 2. graph locate ────────────────────────────────────────────────────
    best = None
    try:
        from tools.desktop_ui_tree import desktop_get_ui_tree, CACHE_FILE
        tree_result = desktop_get_ui_tree(max_depth=8)
        if not tree_result.startswith("ERROR"):
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                elements = json.load(f)
            scored = sorted(
                ((score_element(el, field_description), el) for el in elements),
                key=lambda t: t[0], reverse=True,
            )
            if scored and scored[0][0] >= 0.5:
                best = scored[0][1]
                trace.append(
                    f"Graph locate: [{best['role']}] '{best['name']}' "
                    f"score={scored[0][0]:.2f} at ({best['x']},{best['y']})"
                )
            else:
                top = scored[0] if scored else (0, {})
                trace.append(
                    f"Graph locate: no match >= 0.5 "
                    f"(best {top[0]:.2f}: '{top[1].get('name','')[:30]}')"
                )
        else:
            trace.append(f"Graph locate: tree failed — {tree_result[:100]}")
    except Exception as exc:
        _jtrace(f"[TRACE] tools.virtual_input.smart_fill: except {str(exc)[:80]}")
        trace.append(f"Graph locate: exception — {exc}")

    typed = False
    # ── 3. graph act (virtual first, physical fallback) ───────────────────
    if best is not None:
        ok, vmsg, need_physical = virtual_interact(best, "type", text, session)
        trace.append(f"Virtual input: {'OK' if ok else 'FAILED'} — {vmsg}")
        if ok:
            typed = True
        elif need_physical:
            try:
                from tools.desktop_automation import desktop_smooth_click, desktop_type_text
                cx = best["x"] + best["w"] // 2
                cy = best["y"] + best["h"] // 2
                desktop_smooth_click(cx, cy, duration=0.4)
                time.sleep(0.2)
                desktop_type_text(text)
                trace.append(f"Physical fallback: clicked ({cx},{cy}) + typed")
                typed = True
            except Exception as exc:
                _jtrace(f"[TRACE] tools.virtual_input.smart_fill: except {str(exc)[:80]}")
                trace.append(f"Physical fallback: FAILED — {exc}")

    # ── 4. vision fallback (no graph match) ────────────────────────────────
    if not typed and best is None:
        try:
            from tools.visual_click import visual_click
            from tools.desktop_automation import desktop_type_text
            vres = visual_click(field_description, window_hint)
            trace.append(f"Vision fallback: {vres.splitlines()[0]}")
            if "SUCCESS" in vres:
                time.sleep(0.2)
                desktop_type_text(text)
                trace.append("Vision fallback: typed after visual click")
                typed = True
        except Exception as exc:
            _jtrace(f"[TRACE] tools.virtual_input.smart_fill: except {str(exc)[:80]}")
            trace.append(f"Vision fallback: FAILED — {exc}")

    if not typed:
        session.add_note("\n".join(trace))
        session.save()
        return "[SmartFill] FAILED\n" + "\n".join(trace)

    # ── 5. verify (vision/OCR = the read channel; soft) ────────────────────
    try:
        from tools.hybrid_cursor import _check_text_on_screen
        snippet = text[:30]
        found, loc = _check_text_on_screen(snippet)
        trace.append(f"Verify (OCR '{snippet}'): {'OK — ' + loc if found else 'not visible (may be masked/canvas — soft check)'}")
    except Exception as exc:
        _jtrace(f"[TRACE] tools.virtual_input.smart_fill: except {str(exc)[:80]}")
        trace.append(f"Verify: skipped — {exc}")

    # ── 6. optional Enter ──────────────────────────────────────────────────
    if press_enter:
        try:
            from tools.desktop_automation import desktop_press_keys
            desktop_press_keys(["enter"])
            trace.append("Pressed Enter")
        except Exception as exc:
            _jtrace(f"[TRACE] tools.virtual_input.smart_fill: except {str(exc)[:80]}")
            trace.append(f"Enter failed: {exc}")

    session.add_note("\n".join(trace))
    saved = session.save()
    if saved:
        trace.append(f"Agent view: {saved}")
    return "[SmartFill] SUCCESS\n" + "\n".join(trace)
