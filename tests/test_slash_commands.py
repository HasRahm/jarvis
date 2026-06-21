"""Tests for the TUI slash command registry and inline routing.

These tests import only the pure data (SLASH_COMMANDS, _INLINE_COMMANDS,
_THEMES, _build_css) without starting a Textual App.
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.cli.app import SLASH_COMMANDS, _INLINE_COMMANDS, _THEMES, _build_css


class TestCommandRegistry:
    def test_minimum_command_count(self):
        assert len(SLASH_COMMANDS) >= 20, \
            f"Expected ≥20 commands, got {len(SLASH_COMMANDS)}"

    def test_all_commands_start_with_slash(self):
        for cmd, desc, autocomplete in SLASH_COMMANDS:
            assert cmd.startswith("/"), f"Command '{cmd}' does not start with '/'"

    def test_all_descriptions_non_empty(self):
        for cmd, desc, _ in SLASH_COMMANDS:
            assert desc.strip(), f"Command '{cmd}' has an empty description"

    def test_autocomplete_starts_with_slash(self):
        for cmd, _, autocomplete in SLASH_COMMANDS:
            assert autocomplete.startswith("/"), \
                f"Autocomplete for '{cmd}' does not start with '/'"

    def test_no_duplicate_command_names(self):
        names = [cmd for cmd, _, _ in SLASH_COMMANDS]
        assert len(names) == len(set(names)), "Duplicate command names in registry"

    def test_core_modes_present(self):
        names = {cmd for cmd, _, _ in SLASH_COMMANDS}
        for required in ("/research", "/diagnose", "/browse", "/desktop",
                         "/shell", "/auto", "/screen"):
            assert required in names, f"Core command '{required}' missing"

    def test_new_unique_commands_present(self):
        """Jarvis-specific commands not in vanilla Gemini CLI.

        Phase 45 removed the unimplemented /memory, /recall, /batch, /pipeline commands (they were
        advertised in help/autocomplete but had no handler in either the REPL or the TUI)."""
        names = {cmd for cmd, _, _ in SLASH_COMMANDS}
        for unique in ("/vocab", "/model", "/models",
                       "/tools", "/export", "/theme", "/help"):
            assert unique in names, f"Unique command '{unique}' missing"


class TestInlineCommands:
    def test_inline_commands_subset_of_registry(self):
        registry_names = {cmd for cmd, _, _ in SLASH_COMMANDS}
        for cmd in _INLINE_COMMANDS:
            assert cmd in registry_names, \
                f"Inline command '{cmd}' not in SLASH_COMMANDS registry"

    def test_key_inline_handlers_registered(self):
        for cmd in ("/clear", "/help", "/theme", "/model", "/models", "/tools"):
            assert cmd in _INLINE_COMMANDS, f"'{cmd}' should be an inline command"

    def test_jarvis_modes_not_inline(self):
        """Automation modes must NOT be handled inline — they need the Jarvis worker."""
        for mode in ("/research", "/diagnose", "/browse", "/desktop", "/auto"):
            assert mode not in _INLINE_COMMANDS, \
                f"Mode '{mode}' should not be inline (needs background worker)"


class TestThemes:
    def test_four_themes_defined(self):
        assert len(_THEMES) >= 4

    def test_required_theme_names(self):
        for name in ("dark", "matrix", "light", "ocean"):
            assert name in _THEMES, f"Theme '{name}' missing"

    def test_each_theme_has_required_keys(self):
        required_keys = {"bg", "header_bg", "border", "accent", "text", "dropdown_bg"}
        for name, theme in _THEMES.items():
            missing = required_keys - set(theme.keys())
            assert not missing, f"Theme '{name}' missing keys: {missing}"

    def test_build_css_returns_string(self):
        css = _build_css("dark")
        assert isinstance(css, str)
        assert len(css) > 100

    def test_build_css_injects_accent_colour(self):
        for name, theme in _THEMES.items():
            css = _build_css(name)
            # Accent colour appears in the CSS output
            assert theme["accent"] in css, \
                f"Accent colour for '{name}' not found in generated CSS"

    def test_build_css_unknown_theme_falls_back_to_dark(self):
        css = _build_css("nonexistent_theme")
        dark_accent = _THEMES["dark"]["accent"]
        assert dark_accent in css, "Unknown theme should fall back to dark"


class TestCommandParsing:
    """Simulate the input-submitted parsing logic from JarvisTuiApp."""

    def _parse(self, text: str) -> tuple[str, str]:
        """Mirrors on_input_submitted logic."""
        mode = "auto"
        task = text
        for cmd, _, _ in SLASH_COMMANDS:
            if text.startswith(cmd):
                mode = cmd[1:]
                task = text[len(cmd):].strip()
                break
        return mode, task

    def test_bare_text_is_auto_mode(self):
        mode, task = self._parse("open Chrome and search for jobs")
        assert mode == "auto"
        assert task == "open Chrome and search for jobs"

    def test_research_command(self):
        mode, task = self._parse("/research Find AI startups in NYC")
        assert mode == "research"
        assert task == "Find AI startups in NYC"

    def test_desktop_command(self):
        mode, task = self._parse("/desktop click the search bar in Figma")
        assert mode == "desktop"
        assert task == "click the search bar in Figma"

    def test_model_command_with_arg(self):
        mode, task = self._parse("/model gpt-oss:120b")
        assert mode == "model"
        assert task == "gpt-oss:120b"

    def test_clear_command_no_arg(self):
        mode, task = self._parse("/clear")
        assert mode == "clear"
        assert task == ""

    def test_theme_with_name(self):
        mode, task = self._parse("/theme matrix")
        assert mode == "theme"
        assert task == "matrix"

    def test_command_without_trailing_space(self):
        mode, task = self._parse("/research")
        assert mode == "research"

    def test_help_command(self):
        mode, task = self._parse("/help")
        assert mode == "help"
