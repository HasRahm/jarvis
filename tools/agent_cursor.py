import sys
# tools/agent_cursor.py
"""
Agent Cursor — a visible overlay ring showing where the agent is acting (Phase 24)

A small always-on-top, click-through tkinter window draws a teal ring + dot at
the point where the agent is clicking/typing — so the user can watch the agent
work, especially during virtual (UIA pattern) input where the physical mouse
never moves.

Design notes:
  - The tk root lives on a single daemon thread that owns mainloop(); all
    cross-thread commands go through a queue polled with root.after(16ms).
  - Click-through: tkinter's -transparentcolor hides pixels but the window
    still hit-tests. After creation we set WS_EX_LAYERED|WS_EX_TRANSPARENT|
    WS_EX_TOOLWINDOW|WS_EX_NOACTIVATE on the HWND via ctypes so physical
    clicks AND uiautomation ControlFromPoint probes pass straight through.
  - The ring HIDES during every screen capture (cursor_hidden() wraps all
    mss grabs) so it never confuses vision models, OCR, or imprint deltas.
  - Everything is no-op safe: disabled env, missing tkinter, or a wedged tk
    thread mark the cursor broken and all APIs silently do nothing — an
    automation run can never crash because of the overlay.

Enable with JARVIS_AGENT_CURSOR=1 (or the agent_cursor tool / /cursor command).
"""

import os
import queue
import logging
import threading
from contextlib import contextmanager

logger = logging.getLogger(__name__)

_SIZE = 44                 # overlay window is _SIZE x _SIZE px
_TRANSPARENT = "#ff00ff"   # magenta key color — made invisible
_RING = "#5EEAD4"          # teal ring
_DOT = "#F472B6"           # pink center dot
_ANIM_STEPS = 8


def cursor_enabled() -> bool:
    return os.environ.get("JARVIS_AGENT_CURSOR", "0") == "1"


class AgentCursor:
    """Singleton overlay. Use the module-level functions, not this directly."""

    def __init__(self, start_thread: bool = True):
        self._cmds: queue.Queue = queue.Queue()
        self._ready = threading.Event()
        self._broken = False
        self._thread = None
        self._pos = (0, 0)
        if start_thread:
            self._thread = threading.Thread(
                target=self._tk_main, daemon=True, name="agent-cursor")
            self._thread.start()
            if not self._ready.wait(timeout=2.0):
                logger.warning("[AgentCursor] tk window not ready in 2s — disabling overlay")
                self._broken = True

    # ── command senders (any thread) ──────────────────────────────────────

    def send(self, *cmd) -> None:
        if not self._broken:
            self._cmds.put(cmd)

    # ── tk thread ──────────────────────────────────────────────────────────

    def _tk_main(self) -> None:
        try:
            import tkinter as tk
            root = tk.Tk()
            root.overrideredirect(True)
            root.attributes("-topmost", True)
            root.attributes("-transparentcolor", _TRANSPARENT)
            root.configure(bg=_TRANSPARENT)
            root.geometry(f"{_SIZE}x{_SIZE}+{-_SIZE}+{-_SIZE}")  # park offscreen

            canvas = tk.Canvas(root, width=_SIZE, height=_SIZE,
                               bg=_TRANSPARENT, highlightthickness=0)
            canvas.pack()
            ring = canvas.create_oval(6, 6, _SIZE - 6, _SIZE - 6,
                                      outline=_RING, width=3)
            canvas.create_oval(_SIZE // 2 - 3, _SIZE // 2 - 3,
                               _SIZE // 2 + 3, _SIZE // 2 + 3,
                               fill=_DOT, outline=_DOT)

            self._make_clickthrough(root)
            self._ready.set()

            state = {"target": None, "steps_left": 0, "pulse_left": 0}

            def poll():
                print(f"[TRACE] tools.agent_cursor.AgentCursor._tk_main.poll: enter", file=sys.stderr, flush=True)
                try:
                    while True:
                        cmd = self._cmds.get_nowait()
                        op = cmd[0]
                        if op == "move":
                            _, x, y, animate = cmd
                            if animate and self._pos != (0, 0):
                                state["target"] = (x, y)
                                state["steps_left"] = _ANIM_STEPS
                            else:
                                self._place(root, x, y)
                                root.deiconify()
                        elif op == "pulse":
                            state["pulse_left"] = 4
                        elif op == "hide":
                            root.withdraw()
                        elif op == "show":
                            root.deiconify()
                        elif op == "quit":
                            root.destroy()
                            return
                except queue.Empty:
                    print(f"[TRACE] tools.agent_cursor.AgentCursor._tk_main.poll: except Empty", file=sys.stderr, flush=True)
                    pass

                # animation step
                if state["steps_left"] > 0 and state["target"]:
                    tx, ty = state["target"]
                    cx, cy = self._pos
                    n = state["steps_left"]
                    nx = cx + (tx - cx) // n
                    ny = cy + (ty - cy) // n
                    self._place(root, nx, ny)
                    root.deiconify()
                    state["steps_left"] -= 1

                # pulse: briefly thicken the ring at the action moment
                if state["pulse_left"] > 0:
                    width = 6 if state["pulse_left"] > 2 else 3
                    canvas.itemconfigure(ring, width=width)
                    state["pulse_left"] -= 1

                root.after(16, poll)

            root.after(16, poll)
            root.mainloop()
        except Exception as exc:
            print(f"[TRACE] tools.agent_cursor.AgentCursor._tk_main: except {str(exc)[:80]}", file=sys.stderr, flush=True)
            logger.warning("[AgentCursor] tk thread failed: %s — overlay disabled", exc)
            self._broken = True
            self._ready.set()

    def _place(self, root, x: int, y: int) -> None:
        print(f"[TRACE] tools.agent_cursor.AgentCursor._place: enter", file=sys.stderr, flush=True)
        self._pos = (x, y)
        root.geometry(f"+{x - _SIZE // 2}+{y - _SIZE // 2}")

    @staticmethod
    def _make_clickthrough(root) -> None:
        """Set extended window styles so clicks and UIA hit-tests pass through."""
        try:
            import ctypes
            GWL_EXSTYLE = -20
            WS_EX_LAYERED = 0x80000
            WS_EX_TRANSPARENT = 0x20
            WS_EX_TOOLWINDOW = 0x80
            WS_EX_NOACTIVATE = 0x8000000
            root.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
            style = ctypes.windll.user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
            style |= WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
            ctypes.windll.user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, style)
        except Exception as exc:
            print(f"[TRACE] tools.agent_cursor.AgentCursor._make_clickthrough: except {str(exc)[:80]}", file=sys.stderr, flush=True)
            logger.warning("[AgentCursor] click-through style failed: %s", exc)


# ---------------------------------------------------------------------------
# Module-level singleton API — all no-op safe
# ---------------------------------------------------------------------------

_instance: AgentCursor | None = None
_lock = threading.Lock()


def _get() -> AgentCursor | None:
    """Lazily start the overlay; None when disabled or broken."""
    print(f"[TRACE] tools.agent_cursor._get: enter", file=sys.stderr, flush=True)
    global _instance
    if not cursor_enabled():
        return None
    with _lock:
        if _instance is None:
            try:
                _instance = AgentCursor()
            except Exception as exc:
                print(f"[TRACE] tools.agent_cursor._get: except {str(exc)[:80]}", file=sys.stderr, flush=True)
                logger.warning("[AgentCursor] failed to start: %s", exc)
                return None
        return None if _instance._broken else _instance


def move_to(x: int, y: int, animate: bool = True) -> None:
    """Move the overlay ring to (x, y). No-op when the cursor is disabled."""
    print(f"[TRACE] tools.agent_cursor.move_to: enter", file=sys.stderr, flush=True)
    inst = _get()
    if inst:
        inst.send("move", int(x), int(y), animate)


def pulse() -> None:
    """Flash the ring — call right before a click/invoke."""
    print(f"[TRACE] tools.agent_cursor.pulse: enter", file=sys.stderr, flush=True)
    inst = _get()
    if inst:
        inst.send("pulse")


def hide() -> None:
    print(f"[TRACE] tools.agent_cursor.hide: enter", file=sys.stderr, flush=True)
    global _instance
    if _instance and not _instance._broken:
        _instance.send("hide")


def show() -> None:
    print(f"[TRACE] tools.agent_cursor.show: enter", file=sys.stderr, flush=True)
    inst = _get()
    if inst:
        inst.send("show")


def shutdown() -> None:
    print(f"[TRACE] tools.agent_cursor.shutdown: enter", file=sys.stderr, flush=True)
    global _instance
    with _lock:
        if _instance and not _instance._broken:
            _instance.send("quit")
        _instance = None


@contextmanager
def cursor_hidden():
    """Hide the ring during screen captures so it never appears in screenshots,
    OCR, vision-model input, or imprint deltas. No-op when the cursor is off."""
    print(f"[TRACE] tools.agent_cursor.cursor_hidden: enter", file=sys.stderr, flush=True)
    global _instance
    active = _instance is not None and not _instance._broken and cursor_enabled()
    if active:
        hide()
        import time
        time.sleep(0.06)  # let the withdraw paint before the grab
    try:
        yield
    finally:
        if active:
            show()


# ---------------------------------------------------------------------------
# Agent-facing tool
# ---------------------------------------------------------------------------

def agent_cursor_tool(action: str = "status") -> str:
    """Control the visible agent-cursor overlay. Actions: on | off | status."""
    print(f"[TRACE] tools.agent_cursor.agent_cursor_tool: enter", file=sys.stderr, flush=True)
    action = (action or "status").lower()
    if action == "on":
        os.environ["JARVIS_AGENT_CURSOR"] = "1"
        inst = _get()
        if inst is None:
            return "Agent cursor enabled, but the overlay could not start (no display / tkinter unavailable)."
        return "Agent cursor ON — a teal ring now shows where the agent acts."
    if action == "off":
        os.environ["JARVIS_AGENT_CURSOR"] = "0"
        shutdown()
        return "Agent cursor OFF"
    if action == "status":
        state = "ON" if cursor_enabled() else "OFF"
        running = _instance is not None and not getattr(_instance, "_broken", True)
        return f"Agent cursor is {state} (overlay {'running' if running else 'not running'})"
    return f"ERROR: unknown agent_cursor action '{action}' (use on|off|status)"
