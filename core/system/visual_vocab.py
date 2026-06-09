"""
visual_vocab.py — Phase 22f: Universal Visual Vocabulary

Loads icon, app-logo, and UI-pattern vocabulary from visual-vocab/
and injects it into the Hermes system prompt so Jarvis can interpret
ANY app's UI using a shared visual grammar.

Also exposes vocab_learn() so the agent can append new discoveries
to the learned/ directory, growing the dataset over time.
"""

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

    def get_context_addition(self) -> str:
        """
        Returns a formatted markdown block to append to the Hermes system prompt.
        The agent can reference these tables when interpreting visual_inspect
        output or forming visual_click descriptions.

        Returns empty string if all vocabulary files are missing (graceful
        degradation — no crash if visual-vocab/ doesn't exist yet).
        """
        if not self.icons and not self.logos and not self.patterns:
            return ""

        sections = []

        sections.append(
            "--- VISUAL VOCABULARY LOADED ---\n"
            "Use these reference tables when:\n"
            "  1. Interpreting visual_inspect output — match described shapes to icon names\n"
            "  2. Forming visual_click descriptions — use standard icon/pattern names\n"
            "  3. Checking if OCR will work — see ui_type column in App Logo Guide\n"
            "  4. Identifying which app is open — match logo description to App Logo Guide\n"
        )

        if self.icons:
            sections.append("## Icon Dictionary\n" + self.icons)

        if self.logos:
            sections.append("## App Logo & Identity Guide\n" + self.logos)

        if self.patterns:
            sections.append("## UI Layout Patterns\n" + self.patterns)

        if self.learned:
            sections.append(
                "## Recently Learned Patterns\n"
                "> These were discovered in recent sessions — high confidence.\n"
                + self.learned
            )

        sections.append("--- END VISUAL VOCABULARY ---")

        return "\n\n" + "\n\n".join(sections) + "\n\n"

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
            return f"ERROR saving learned pattern: {e}"


# ── Module-level convenience functions ───────────────────────────────────────

def get_vocab_context_addition() -> str:
    """Convenience function for hermes_cli_runner.py import."""
    return VisualVocabulary().get_context_addition()


def vocab_learn(heading: str, content: str) -> str:
    """Convenience function for dispatcher.py import."""
    return VisualVocabulary().learn(heading, content)
