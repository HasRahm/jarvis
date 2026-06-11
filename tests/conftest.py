"""Shared test fixtures and helpers."""
import os
import sys
import pytest

# Make project root importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Strip live API keys so tests never make real network calls."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-anthropic-fake")
    monkeypatch.setenv("NVIDIA_API_KEY",    "nvapi-test-fake")
    monkeypatch.setenv("GEMINI_API_KEY",    "gemini-test-fake")
    monkeypatch.setenv("OPENAI_API_KEY",    "sk-test-openai-fake")
    monkeypatch.setenv("HERMES_SECRET",     "test-secret-32-chars-padded-ok!")
    monkeypatch.setenv("OLLAMA_HOST",       "http://localhost:11434")


@pytest.fixture
def tmp_vocab_dir(tmp_path):
    """A temporary visual-vocab directory with minimal fixtures."""
    vocab = tmp_path / "visual-vocab"
    vocab.mkdir()
    (vocab / "icons.md").write_text(
        "| Icon | Shape | Meaning | Location | Action |\n"
        "|------|-------|---------|----------|--------|\n"
        "| Search | Magnifying glass | Open search | Top bar | Click |\n",
        encoding="utf-8",
    )
    (vocab / "app-logos.md").write_text(
        "| App | Logo | Process | UI Type | Notes |\n"
        "|-----|------|---------|---------|-------|\n"
        "| Chrome | Blue circle | chrome.exe | html | DOM accessible |\n",
        encoding="utf-8",
    )
    (vocab / "ui-patterns.md").write_text(
        "| Pattern | Visual | Meaning | Elements |\n"
        "|---------|--------|---------|----------|\n"
        "| Sidebar | Vertical panel left | Navigation | List items |\n",
        encoding="utf-8",
    )
    (vocab / "learned").mkdir()
    return vocab
