"""Phase 24 — agent view: annotated screenshot recorder.

Display-free: when enabled, a synthetic PIL image is injected via base_image
so mss is never touched.
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from PIL import Image
import tools.agent_view as av
from tools.agent_view import (
    AgentViewSession, view_enabled, agent_view_tool,
    COLOR_MATCH, COLOR_VISION_CROP, COLOR_PROBE_HIT,
)


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setenv("JARVIS_AGENT_VIEW", "1")


@pytest.fixture
def disabled(monkeypatch):
    monkeypatch.setenv("JARVIS_AGENT_VIEW", "0")


@pytest.fixture
def tmp_view_dir(tmp_path, monkeypatch):
    d = str(tmp_path / "agent_view")
    monkeypatch.setattr(av, "AGENT_VIEW_DIR", d)
    monkeypatch.setattr(av, "LATEST_FILE", os.path.join(d, "latest.txt"))
    return d


def synth_img():
    return Image.new("RGB", (800, 600), (20, 20, 20))


class TestDisabled:
    def test_session_is_full_noop(self, disabled, monkeypatch):
        # prove no screen capture happens: make _capture_screen explode
        monkeypatch.setattr(av, "_capture_screen", lambda: (_ for _ in ()).throw(RuntimeError("captured!")))
        s = AgentViewSession("test_op")
        assert s.img is None
        # all recorders are safe no-ops
        s.add_window_graph({"nodes": [{"x": 0, "y": 0, "w": 10, "h": 10}]})
        s.add_probe(5, 5, hit=True)
        s.add_match_box(1, 1, 5, 5, "x")
        s.add_ocr_words({"text": ["a"], "conf": [90], "left": [0], "top": [0], "width": [5], "height": [5]})
        s.add_vision_crop((0, 0, 10, 10), (5, 5))
        s.add_note("note")
        assert s.save() is None

    def test_view_enabled_false(self, disabled):
        assert not view_enabled()


class TestEnabled:
    def test_save_writes_png_and_latest(self, enabled, tmp_view_dir):
        s = AgentViewSession("hybrid_Search", base_image=synth_img())
        assert s.img is not None
        s.add_window_graph({
            "nodes": [{"title": "Notepad", "x": 50, "y": 50, "w": 400, "h": 300, "depth": 0}],
            "blocked_paths": [{"blocking_window": "Other",
                               "intersection": {"x": 60, "y": 60, "w": 40, "h": 40}}],
        })
        s.add_probe(100, 100, hit=False)
        s.add_probe(200, 120, hit=True)
        s.add_match_box(180, 100, 80, 40, "Search")
        s.add_vision_crop((300, 200, 200, 150), (380, 260), note="FOUND 80 60")
        s.add_note("layer trace here")
        path = s.save()
        assert path and os.path.exists(path)
        assert path.endswith(".png")
        with open(os.path.join(tmp_view_dir, "latest.txt")) as f:
            assert f.read().strip() == path

    def test_match_box_pixels_drawn(self, enabled, tmp_view_dir):
        s = AgentViewSession("px", base_image=synth_img())
        s.add_match_box(100, 100, 60, 30, "btn")
        path = s.save()
        img = Image.open(path)
        # the 4px-wide box outline passes through (100, 115) on its left edge
        assert img.getpixel((100, 115)) == COLOR_MATCH

    def test_vision_crop_pixels_drawn(self, enabled, tmp_view_dir):
        s = AgentViewSession("px2", base_image=synth_img())
        s.add_vision_crop((200, 200, 100, 80), None)
        path = s.save()
        img = Image.open(path)
        assert img.getpixel((200, 240)) == COLOR_VISION_CROP

    def test_probe_hit_ring_drawn(self, enabled, tmp_view_dir):
        s = AgentViewSession("px3", base_image=synth_img())
        s.add_probe(400, 300, hit=True)
        path = s.save()
        img = Image.open(path)
        # ring outline at radius 8 — sample the leftmost point
        assert img.getpixel((392, 300)) == COLOR_PROBE_HIT

    def test_prune_keeps_newest_30(self, enabled, tmp_view_dir):
        os.makedirs(tmp_view_dir, exist_ok=True)
        for i in range(35):
            Image.new("RGB", (4, 4)).save(os.path.join(tmp_view_dir, f"202601{i:02d}_old.png"))
        s = AgentViewSession("rotor", base_image=synth_img())
        s.save()
        pngs = [f for f in os.listdir(tmp_view_dir) if f.endswith(".png")]
        assert len(pngs) <= av.MAX_FILES

    def test_op_name_sanitized(self, enabled, tmp_view_dir):
        s = AgentViewSession('weird/op:name "with" spaces', base_image=synth_img())
        path = s.save()
        base = os.path.basename(path)
        assert "/" not in base.replace("\\", "") and ":" not in base.split("_", 1)[1]


class TestTool:
    def test_on_off_status(self, tmp_view_dir, monkeypatch):
        monkeypatch.setenv("JARVIS_AGENT_VIEW", "0")
        assert "ON" in agent_view_tool("on")
        assert view_enabled()
        assert "OFF" in agent_view_tool("off")
        assert not view_enabled()
        assert "OFF" in agent_view_tool("status")

    def test_latest_without_files(self, tmp_view_dir):
        assert "No agent-view screenshots yet" in agent_view_tool("latest")

    def test_unknown_action(self):
        assert agent_view_tool("explode").startswith("ERROR")
