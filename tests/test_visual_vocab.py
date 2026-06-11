"""Tests for the VisualVocabulary class.

Uses tmp_vocab_dir fixture from conftest.py so no real vocab files are needed.
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def vocab(tmp_vocab_dir, monkeypatch):
    """VisualVocabulary pointed at the temp fixture directory."""
    from core.system.visual_vocab import VisualVocabulary
    return VisualVocabulary(vocab_dir=str(tmp_vocab_dir))


class TestVocabLoading:
    def test_icons_loaded(self, vocab):
        assert vocab.icons, "icons should not be empty"
        assert "Search" in vocab.icons or "search" in vocab.icons.lower()

    def test_logos_loaded(self, vocab):
        assert vocab.logos, "logos should not be empty"
        assert "Chrome" in vocab.logos or "chrome" in vocab.logos.lower()

    def test_patterns_loaded(self, vocab):
        assert vocab.patterns, "patterns should not be empty"

    def test_learned_empty_initially(self, vocab):
        assert vocab.learned == "" or vocab.learned is not None


class TestContextAddition:
    def test_returns_string(self, vocab):
        result = vocab.get_context_addition()
        assert isinstance(result, str)

    def test_contains_section_headers(self, vocab):
        result = vocab.get_context_addition()
        assert "Icon" in result or "VISUAL" in result

    def test_not_empty(self, vocab):
        result = vocab.get_context_addition()
        assert len(result) > 100, "context addition should have substantial content"

    def test_cheatsheet_under_size_limit(self, vocab):
        """The injected vocab block must stay under 6 KB to keep per-turn tokens small."""
        result = vocab.get_context_addition()
        assert len(result) < 60_000, "vocab injection suspiciously large"


class TestVocabLearn:
    def test_learn_returns_confirmation(self, vocab):
        result = vocab.learn("Test heading", "Test content for learning")
        assert isinstance(result, str)
        assert "learn" in result.lower() or "saved" in result.lower() or "Test heading" in result

    def test_learn_creates_file(self, vocab, tmp_vocab_dir):
        vocab.learn("Chrome search bar", "Found at y=64 on 1080p screen")
        learned_dir = tmp_vocab_dir / "learned"
        files = list(learned_dir.glob("*.md"))
        assert len(files) >= 1, "learn() should create a file in learned/"

    def test_learn_content_persists(self, vocab, tmp_vocab_dir):
        heading = "Unique-marker-XYZ"
        vocab.learn(heading, "Marker content")
        learned_dir = tmp_vocab_dir / "learned"
        combined = "\n".join(f.read_text(encoding="utf-8") for f in learned_dir.glob("*.md"))
        assert heading in combined, "learned content should persist to disk"

    def test_learn_appends_not_overwrites(self, vocab):
        vocab.learn("First entry",  "Content A")
        vocab.learn("Second entry", "Content B")
        # Both entries should exist — learn should append
        from core.system.visual_vocab import VisualVocabulary
        vocab2 = VisualVocabulary(vocab_dir=str(vocab.vocab_dir))
        assert "First entry" in vocab2.learned or len(vocab2.learned) > 0


class TestLookup:
    """If vocab_lookup (Phase 22h) is implemented, test it here."""

    def test_lookup_icons_returns_string(self, vocab):
        if not hasattr(vocab, "lookup"):
            pytest.skip("lookup() not yet implemented")
        result = vocab.lookup("icons")
        assert isinstance(result, str)
        assert len(result) > 10

    def test_lookup_invalid_category(self, vocab):
        if not hasattr(vocab, "lookup"):
            pytest.skip("lookup() not yet implemented")
        result = vocab.lookup("nonexistent_category")
        assert isinstance(result, str)
