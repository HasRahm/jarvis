"""Phase 46 cluster 1 — generated files land in the user's output dir, not the install dir. CI-safe."""
import os
import sys
import tempfile
import importlib

os.environ.setdefault("JARVIS_CI", "true")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _reload_auth():
    import core.auth as auth
    importlib.reload(auth)
    return auth


def test_unset_defaults_to_install_dir(monkeypatch):
    # Backward compatible: with JARVIS_OUTPUT_ROOT unset, rooting is the install dir as before.
    monkeypatch.delenv("JARVIS_OUTPUT_ROOT", raising=False)
    auth = _reload_auth()
    amp = auth.get_agents_md_path(None)
    assert amp.replace("\\", "/").endswith("jarvis/AGENTS.md")


def test_output_root_roots_workspace_and_agents_md(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_OUTPUT_ROOT", str(tmp_path))
    auth = _reload_auth()
    assert os.path.dirname(auth.get_agents_md_path(None)) == str(tmp_path)
    assert auth.get_workspace_path("backend", None).startswith(str(tmp_path))


def test_saas_user_scoped_under_output_root(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_OUTPUT_ROOT", str(tmp_path))
    auth = _reload_auth()
    a = auth.get_workspace_path("backend", "alice")
    b = auth.get_workspace_path("backend", "bob")
    assert a != b
    assert os.path.join("workspaces", "alice", "backend").replace("\\", "/") in a.replace("\\", "/")


def test_build_prompt_injects_output_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_OUTPUT_ROOT", str(tmp_path))
    spec = importlib.util.spec_from_file_location(
        "jcli_test", os.path.join(os.path.dirname(__file__), "..", "jarvis-cli.py"))
    jcli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(jcli)
    p = jcli.build_prompt("excel", "make a tracker")
    assert str(tmp_path) in p
    assert "{{OUTPUT_DIR}}" not in p          # placeholder substituted
    assert "YOUR_USERNAME" not in p           # no leftover template path
    assert "OUTPUT LOCATION" in p


def teardown_module(_module):
    # Restore default rooting for other test modules.
    os.environ.pop("JARVIS_OUTPUT_ROOT", None)
    import core.auth as auth
    importlib.reload(auth)
