"""
visual_vocab.py — Phase 22f: Universal Visual Vocabulary

Loads icon, app-logo, and UI-pattern vocabulary from visual-vocab/
and injects it into the Hermes system prompt so Jarvis can interpret
ANY app's UI using a shared visual grammar.

Also exposes vocab_learn() so the agent can append new discoveries
to the learned/ directory, growing the dataset over time.
"""
import sys

import os
import datetime
import logging

logger = logging.getLogger(__name__)

# Project root = two levels up from this file (core/system/visual_vocab.py)
_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
_VOCAB_DIR = os.path.join(_PROJECT_ROOT, "visual-vocab")
_LEARNED_DIR = os.path.join(_VOCAB_DIR, "learned")


def _read_file_safe(path: str) -> str:
    """Read a file, return empty string on any error."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception as e:
        print(f"[TRACE] core.system.visual_vocab._read_file_safe: except {str(e)[:80]}", file=sys.stderr, flush=True)
        logger.warning(f"[VisualVocab] Could not read {path}: {e}")
        return ""


class VisualVocabulary:
    """
    Loads the three vocabulary files + any learned patterns and provides
    them as a formatted system-prompt injection block.

    Usage in hermes_cli_runner.py:
        from core.system.visual_vocab import VisualVocabulary
        vocab_addition = VisualVocabulary().get_context_addition()
        messages = [{"role": "system", "content": ... + vocab_addition}, ...]
    """

    def __init__(self, vocab_dir: str = None):
        self.vocab_dir = vocab_dir or _VOCAB_DIR
        self.learned_dir = os.path.join(self.vocab_dir, "learned")
        self.icons: str = ""
        self.logos: str = ""
        self.patterns: str = ""
        self.learned: str = ""
        self._load()

    # ── Loading ───────────────────────────────────────────────────────────────

    def _load(self):
        """Read all vocabulary files into memory."""
        print(f"[TRACE] core.system.visual_vocab.VisualVocabulary._load: enter", file=sys.stderr, flush=True)
        self.icons = _read_file_safe(os.path.join(self.vocab_dir, "icons.md"))
        self.logos = _read_file_safe(os.path.join(self.vocab_dir, "app-logos.md"))
        self.patterns = _read_file_safe(os.path.join(self.vocab_dir, "ui-patterns.md"))
        self.learned = self._load_learned()

    def _load_learned(self) -> str:
        """
        Load all learned/*.md files, sorted by filename (date ascending,
        so most recent is at the end — most recent knowledge read last = highest priority).
        Returns concatenated content, or empty string if none.
        """
        print(f"[TRACE] core.system.visual_vocab.VisualVocabulary._load_learned: enter", file=sys.stderr, flush=True)
        if not os.path.isdir(self.learned_dir):
            return ""
        files = sorted(
            f for f in os.listdir(self.learned_dir) if f.endswith(".md")
        )
        if not files:
            return ""
        parts = []
        for fname in files:
            content = _read_file_safe(os.path.join(self.learned_dir, fname))
            if content:
                parts.append(content)
        return "\n\n".join(parts)

    # ── System Prompt Injection ───────────────────────────────────────────────

    # Compact, always-injected summary (~3 KB instead of the full ~48 KB tables).
    # The full tables are one cheap `vocab_lookup(category)` call away when a hard
    # UI actually needs them — this keeps the per-turn prompt small for every task.
    _CHEATSHEET = """--- VISUAL VOCABULARY (quick reference) ---
Call `vocab_lookup("icons"|"logos"|"patterns")` for the FULL table when you need detail.

ROUTING RULE (most important — pick the fast tool):
- Native/HTML/Electron-chrome UI (real OS controls): try `hybrid_locate_click` FIRST —
  it finds the element via the window graph + accessibility tree in ~1ms, NO vision call.
- WebGL/OpenGL canvas (Figma canvas, Blender, 3D/game/map views): use `visual_click`
  (vision) — the accessibility tree can't see inside a pixel canvas. screen_ocr also fails there.
- When you DO use visual_click, ALWAYS pass window_hint so the screenshot is cropped to that
  window (faster + more accurate). Batch focus+click+type+enter into ONE desktop_batch_actions call.

COMMON ICONS (shape -> meaning):
- magnifying glass = search   - gear/cog = settings        - X = close/dismiss
- ☰ three lines = menu/nav    - + plus = add/create        - trash can = delete
- pencil = edit               - ⋯/⋮ three dots = more menu  - ← / → = back / forward
- house = home                - bell = notifications        - person = profile/account
- ↻ circle arrow = refresh    - funnel = filter            - ↑↓ = sort
- floppy/cloud-up = save      - down-arrow-box = download   - paperclip = attach
- star = favorite             - checkmark = success/confirm - ! in triangle = warning
- ▶ = play   ‖ = pause   ■ = stop   - eye = show/hide   - paper-plane = send

APP ui_type (does screen_ocr / hybrid_locate_click work?):
- Figma = electron_webgl (OCR FAILS on canvas -> visual_click)
- Blender = opengl (OCR FAILS everywhere -> visual_click)
- Chrome/Edge/Firefox = html (DOM ok; address bar = Ctrl+L)
- VS Code = electron (cmd palette Ctrl+Shift+P, terminal Ctrl+`)
- Slack/Discord/Teams/Notion = electron (search Ctrl+K; message input at bottom)
- Word/Excel/PowerPoint = native_win32 + COM (prefer win32com automation)
- File Explorer/Terminal/Notepad = native_win32 (OCR + hybrid_locate_click work)

COMMON LAYOUT (where things live):
- Top bar = global actions/search   - Left sidebar = navigation/file tree
- Right panel = properties/inspector - Bottom bar = status / message input
- Modal w/ dim overlay = must act (OK/Cancel) before continuing
- Loading spinner = wait, don't click yet   - Card grid / list = click item to open
--- END VISUAL VOCABULARY ---"""

    def get_cheatsheet(self) -> str:
        """Return the compact always-injected summary, plus any learned patterns."""
        print(f"[TRACE] core.system.visual_vocab.VisualVocabulary.get_cheatsheet: enter", file=sys.stderr, flush=True)
        cs = self._CHEATSHEET
        if self.learned:
            cs += (
                "\n\n--- RECENTLY LEARNED (high confidence, this/prior sessions) ---\n"
                + self.learned
                + "\n--- END LEARNED ---"
            )
        return cs

    def lookup(self, category: str) -> str:
        """Return the FULL table for a category: 'icons', 'logos', or 'patterns'."""
        print(f"[TRACE] core.system.visual_vocab.VisualVocabulary.lookup: enter", file=sys.stderr, flush=True)
        cat = (category or "").strip().lower()
        if cat in ("icon", "icons"):
            return self.icons or "No icon vocabulary loaded."
        if cat in ("logo", "logos", "app", "apps", "app-logos"):
            return self.logos or "No app-logo vocabulary loaded."
        if cat in ("pattern", "patterns", "ui", "ui-patterns", "layout"):
            return self.patterns or "No UI-pattern vocabulary loaded."
        return (
            f"Unknown vocab category '{category}'. "
            "Valid categories: 'icons', 'logos', 'patterns'."
        )

    def get_context_addition(self) -> str:
        """
        Returns the compact cheatsheet to append to the Hermes system prompt.
        (The full ~48 KB tables are fetched on demand via the vocab_lookup tool.)

        Returns empty string if all vocabulary files are missing (graceful
        degradation — no crash if visual-vocab/ doesn't exist yet).
        """
        print(f"[TRACE] core.system.visual_vocab.VisualVocabulary.get_context_addition: enter", file=sys.stderr, flush=True)
        if not self.icons and not self.logos and not self.patterns:
            return ""
        return "\n\n" + self.get_cheatsheet() + "\n\n"

    # ── Self-Learning ─────────────────────────────────────────────────────────

    def learn(self, heading: str, content: str) -> str:
        """
        Append a newly discovered UI pattern to today's learned file.
        Called by the vocab_learn dispatcher tool after a successful automation.

        File: visual-vocab/learned/YYYY-MM-DD.md
        Each entry is appended as:
            ## {heading}
            {content}

        Returns a confirmation string.
        """
        print(f"[TRACE] core.system.visual_vocab.VisualVocabulary.learn: enter", file=sys.stderr, flush=True)
        if not heading or not heading.strip():
            return "ERROR: heading is required."
        if not content or not content.strip():
            return "ERROR: content is required."

        # Ensure learned/ directory exists
        os.makedirs(self.learned_dir, exist_ok=True)

        today = datetime.date.today().isoformat()  # e.g. "2026-06-09"
        file_path = os.path.join(self.learned_dir, f"{today}.md")

        # Build the entry to append
        entry = f"\n## {heading.strip()}\n{content.strip()}\n"

        try:
            # If file doesn't exist yet, add a header
            if not os.path.isfile(file_path):
                header = f"# Visual Vocabulary — Learned: {today}\n"
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(header)

            # Append the new entry
            with open(file_path, "a", encoding="utf-8") as f:
                f.write(entry)

            return (
                f"Learned: '{heading}' saved to visual-vocab/learned/{today}.md"
            )
        except Exception as e:
            print(f"[TRACE] core.system.visual_vocab.VisualVocabulary.learn: except {str(e)[:80]}", file=sys.stderr, flush=True)
            return f"ERROR saving learned pattern: {e}"


# ── Module-level convenience functions ───────────────────────────────────────

def get_vocab_context_addition() -> str:
    """Convenience function for hermes_cli_runner.py import."""
    return VisualVocabulary().get_context_addition()


def vocab_learn(heading: str, content: str) -> str:
    """Convenience function for dispatcher.py import."""
    return VisualVocabulary().learn(heading, content)


def vocab_lookup(category: str) -> str:
    """Convenience function for dispatcher.py import — full table on demand."""
    return VisualVocabulary().lookup(category)
