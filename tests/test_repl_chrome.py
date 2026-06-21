"""Phase 40 — REPL chrome (warm-elegant banner + helpers). CI-safe, no TTY."""
import os
import io
import sys

os.environ.setdefault("JARVIS_CI", "true")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from rich.console import Console
from rich.text import Text

from core.cli.repl import JarvisRepl, _gradient_text, _warm, _hex_to_rgb


class TestHelpers:
    def test_hex_to_rgb(self):
        assert _hex_to_rgb("#E08A5F") == (224, 138, 95)
        assert _hex_to_rgb("F0C27B") == (240, 194, 123)

    def test_gradient_preserves_text(self):
        t = _gradient_text("J A R V I S", "#E08A5F", "#F0C27B", bold=True)
        assert isinstance(t, Text)
        assert t.plain == "J A R V I S"

    def test_gradient_bad_hex_falls_back(self):
        # Must not raise on malformed input.
        t = _gradient_text("HI", "nothex", "#F0C27B")
        assert t.plain == "HI"

    def test_warm_palette_has_keys(self):
        w = _warm()
        for k in ("accent", "grad_a", "grad_b", "muted", "rule"):
            assert k in w


def _repl_with_capture():
    r = JarvisRepl()
    buf = io.StringIO()
    r.console = Console(file=buf, width=100)  # not a terminal → animation auto-skips
    return r, buf


class TestBanner:
    def test_banner_renders_without_error(self):
        r, buf = _repl_with_capture()
        r._banner()
        out = buf.getvalue()
        assert "console" in out          # tagline "inline console"
        assert out.strip()               # produced visible output

    def test_banner_no_anim_env(self, monkeypatch):
        monkeypatch.setenv("JARVIS_NO_ANIM", "1")
        # Reload module flag is read at call time via getattr/console.is_terminal; banner must
        # still render the static fallback cleanly.
        r, buf = _repl_with_capture()
        r._banner()
        assert buf.getvalue().strip()

    def test_banner_never_raises_on_broken_console(self):
        r, _ = _repl_with_capture()

        class _BoomConsole:
            is_terminal = False
            def print(self, *a, **k):
                raise RuntimeError("boom")
        r.console = _BoomConsole()
        # _banner swallows chrome errors — must not propagate.
        r._banner()
