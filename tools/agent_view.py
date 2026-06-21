# tools/agent_view.py
"""
Agent View — annotated screenshots of what the agent "sees" (Phase 24)

Every locate/click operation can record its perception into an AgentViewSession:
  - window-graph rectangles (title + z-depth labels, occlusions in red)
  - mouse-braille probe points (miss = small gray dot, hit = green ring)
  - matched element bounding boxes
  - OCR word boxes colored by confidence
  - the crop region sent to a vision model + the coordinate it returned

Sessions save annotated PNGs to scratch/agent_view/ and are a complete no-op
unless JARVIS_AGENT_VIEW=1 — call sites never need to gate on the env var.
"""

import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENT_VIEW_DIR = os.path.join(_PROJECT_ROOT, "scratch", "agent_view")
LATEST_FILE = os.path.join(AGENT_VIEW_DIR, "latest.txt")
MAX_FILES = 30

# Annotation colors (module constants so tests can assert pixels)
COLOR_WINDOW = (94, 234, 212)      # teal — window rectangles
COLOR_OCCLUSION = (239, 68, 68)    # red — occluded intersections
COLOR_PROBE_MISS = (148, 163, 184) # gray — braille probe that found nothing
COLOR_PROBE_HIT = (34, 197, 94)    # green — braille probe that matched
COLOR_MATCH = (34, 197, 94)        # green — matched element box
COLOR_OCR_LOW = (239, 68, 68)      # red — OCR conf < 50
COLOR_OCR_MID = (234, 179, 8)      # yellow — OCR conf 50-70
COLOR_OCR_HIGH = (34, 197, 94)     # green — OCR conf >= 70
COLOR_VISION_CROP = (59, 130, 246) # blue — region sent to the vision model
COLOR_VISION_HIT = (217, 70, 239)  # magenta — coordinate the model returned
COLOR_FOOTER_BG = (10, 12, 15)
COLOR_FOOTER_FG = (230, 233, 239)


def view_enabled() -> bool:
    """Whether agent-view recording is on (defaults to ON, disabled with JARVIS_AGENT_VIEW=0)."""
    return os.environ.get("JARVIS_AGENT_VIEW", "1") != "0"


def _capture_screen():
    """Full-screen PIL image, with the agent cursor overlay hidden."""
    import mss
    from PIL import Image
    from tools.agent_cursor import cursor_hidden

    with cursor_hidden():
        with mss.mss() as sct:
            raw = sct.grab(sct.monitors[1])
            return Image.frombytes("RGB", (raw.width, raw.height), raw.bgra, "raw", "BGRX")


class AgentViewSession:
    """Records one locate/click operation onto an annotated screenshot.

    Construction captures the screen ONLY when JARVIS_AGENT_VIEW=1; otherwise
    self.img stays None and every method (including save) is a no-op, so call
    sites can record unconditionally with zero overhead when disabled.
    """

    def __init__(self, op_name: str, base_image=None):
        self.op_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in op_name)[:40]
        self.img = None
        self._draw = None
        self._probes = []     # (x, y, hit) — drawn lazily at save (can be hundreds)
        self._notes = []
        if not view_enabled():
            return
        try:
            from PIL import ImageDraw
            self.img = base_image if base_image is not None else _capture_screen()
            self._draw = ImageDraw.Draw(self.img)
        except Exception as exc:
            logger.warning("[AgentView] capture failed, session disabled: %s", exc)
            self.img = None

    # ── recorders ──────────────────────────────────────────────────────────

    def add_window_graph(self, graph: dict) -> None:
        """Draw window rectangles with title+depth labels and occluded regions."""
        if self.img is None:
            return
        try:
            for node in graph.get("nodes", []):
                x, y = node.get("x", 0), node.get("y", 0)
                w, h = node.get("w", 0), node.get("h", 0)
                if w <= 0 or h <= 0:
                    continue
                self._draw.rectangle([x, y, x + w, y + h], outline=COLOR_WINDOW, width=2)
                label = f"{node.get('title','')[:30]} d{node.get('depth','?')}"
                self._label(x + 4, y + 4, label, COLOR_WINDOW)
            for occ in graph.get("blocked_paths", []):
                inter = occ.get("intersection", {})
                ix, iy = inter.get("x", 0), inter.get("y", 0)
                iw, ih = inter.get("w", 0), inter.get("h", 0)
                if iw <= 0 or ih <= 0:
                    continue
                self._draw.rectangle([ix, iy, ix + iw, iy + ih],
                                     outline=COLOR_OCCLUSION, width=2)
                self._label(ix + 4, iy + 4,
                            f"occluded by {occ.get('blocking_window','')[:24]}",
                            COLOR_OCCLUSION)
        except Exception as exc:
            logger.warning("[AgentView] add_window_graph failed: %s", exc)

    def add_probe(self, x: int, y: int, hit: bool = False) -> None:
        """Record one mouse-braille ControlFromPoint probe (drawn at save)."""
        if self.img is None:
            return
        self._probes.append((x, y, hit))

    def add_match_box(self, x: int, y: int, w: int, h: int, label: str = "") -> None:
        """Highlight the element the agent matched and is about to act on."""
        if self.img is None:
            return
        try:
            self._draw.rectangle([x, y, x + w, y + h], outline=COLOR_MATCH, width=4)
            if label:
                self._label(x, max(0, y - 14), f"MATCH: {label[:40]}", COLOR_MATCH)
        except Exception as exc:
            logger.warning("[AgentView] add_match_box failed: %s", exc)

    def add_ocr_words(self, tess_data: dict, min_conf: int = 30) -> None:
        """Draw pytesseract word boxes colored by confidence."""
        if self.img is None:
            return
        try:
            for i, tok in enumerate(tess_data.get("text", [])):
                if not (tok or "").strip():
                    continue
                conf = int(tess_data["conf"][i])
                if conf < min_conf:
                    continue
                x, y = tess_data["left"][i], tess_data["top"][i]
                w, h = tess_data["width"][i], tess_data["height"][i]
                color = (COLOR_OCR_LOW if conf < 50
                         else COLOR_OCR_MID if conf < 70
                         else COLOR_OCR_HIGH)
                self._draw.rectangle([x, y, x + w, y + h], outline=color, width=1)
        except Exception as exc:
            logger.warning("[AgentView] add_ocr_words failed: %s", exc)

    def add_vision_crop(self, crop_box: tuple, result_xy: tuple = None, note: str = "") -> None:
        """Draw the region sent to the vision model and the coordinate it returned.

        crop_box:  (x, y, w, h) in screen coords.
        result_xy: (x, y) in screen coords, or None when the model found nothing.
        """
        if self.img is None:
            return
        try:
            x, y, w, h = crop_box
            self._draw.rectangle([x, y, x + w, y + h], outline=COLOR_VISION_CROP, width=3)
            self._label(x + 4, y + 4, f"vision crop {w}x{h}", COLOR_VISION_CROP)
            if result_xy is not None:
                rx, ry = result_xy
                # crosshair
                self._draw.line([rx - 14, ry, rx + 14, ry], fill=COLOR_VISION_HIT, width=3)
                self._draw.line([rx, ry - 14, rx, ry + 14], fill=COLOR_VISION_HIT, width=3)
                self._draw.ellipse([rx - 8, ry - 8, rx + 8, ry + 8],
                                   outline=COLOR_VISION_HIT, width=3)
            if note:
                self._notes.append(f"vision: {note}")
        except Exception as exc:
            logger.warning("[AgentView] add_vision_crop failed: %s", exc)

    def add_note(self, text: str) -> None:
        """Append a line to the footer text strip."""
        if self.img is None:
            return
        self._notes.append(text)

    # ── output ─────────────────────────────────────────────────────────────

    def save(self) -> str | None:
        """Render probes + footer, write the PNG, prune old files.

        Returns the saved path, or None when the session is disabled.
        """
        if self.img is None:
            return None
        try:
            # Lazily draw the probe layer (hundreds of points)
            for x, y, hit in self._probes:
                if hit:
                    self._draw.ellipse([x - 8, y - 8, x + 8, y + 8],
                                       outline=COLOR_PROBE_HIT, width=3)
                else:
                    self._draw.ellipse([x - 2, y - 2, x + 2, y + 2],
                                       fill=COLOR_PROBE_MISS)

            # Footer strip with notes
            if self._notes:
                from PIL import ImageDraw, ImageFont, Image as PILImage
                font = ImageFont.load_default()
                lines = []
                for n in self._notes[-6:]:
                    lines.extend(str(n).splitlines() or [""])
                lines = lines[-8:]
                strip_h = 14 * len(lines) + 8
                w, h = self.img.size
                expanded = PILImage.new("RGB", (w, h + strip_h), COLOR_FOOTER_BG)
                expanded.paste(self.img, (0, 0))
                d = ImageDraw.Draw(expanded)
                for i, line in enumerate(lines):
                    d.text((6, h + 4 + i * 14), line[:220], fill=COLOR_FOOTER_FG, font=font)
                self.img = expanded

            os.makedirs(AGENT_VIEW_DIR, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
            path = os.path.join(AGENT_VIEW_DIR, f"{ts}_{self.op_name}.png")
            self.img.save(path, format="PNG")
            
            # Save a copy to the main scratch directory for instant user viewing
            main_scratch_path = os.path.join(_PROJECT_ROOT, "scratch", "last_action_annotated.png")
            self.img.save(main_scratch_path, format="PNG")

            with open(LATEST_FILE, "w", encoding="utf-8") as f:
                f.write(path)
            _prune_old_files()
            logger.info("[AgentView] saved %s", path)
            return path
        except Exception as exc:
            logger.warning("[AgentView] save failed: %s", exc)
            return None

    def _label(self, x: int, y: int, text: str, color: tuple) -> None:
        from PIL import ImageFont
        font = ImageFont.load_default()
        self._draw.text((x, y), text, fill=color, font=font)


def _prune_old_files() -> None:
    """Keep only the newest MAX_FILES PNGs in the agent_view dir."""
    try:
        pngs = sorted(
            (f for f in os.listdir(AGENT_VIEW_DIR) if f.endswith(".png")),
            reverse=True,
        )
        for old in pngs[MAX_FILES:]:
            try:
                os.remove(os.path.join(AGENT_VIEW_DIR, old))
            except OSError:
                pass
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Agent-facing tool
# ---------------------------------------------------------------------------

def agent_view_tool(action: str = "latest", open_file: bool = False) -> str:
    """Manage the agent-view recorder. Actions: latest | on | off | status."""
    action = (action or "latest").lower()

    if action == "on":
        os.environ["JARVIS_AGENT_VIEW"] = "1"
        return "Agent view ON — every locate/click op now saves an annotated PNG to scratch/agent_view/"
    if action == "off":
        os.environ["JARVIS_AGENT_VIEW"] = "0"
        return "Agent view OFF"
    if action == "status":
        count = 0
        if os.path.isdir(AGENT_VIEW_DIR):
            count = len([f for f in os.listdir(AGENT_VIEW_DIR) if f.endswith(".png")])
        state = "ON" if view_enabled() else "OFF"
        return f"Agent view is {state}; {count} saved screenshot(s) in {AGENT_VIEW_DIR}"
    if action == "latest":
        if not os.path.exists(LATEST_FILE):
            return "No agent-view screenshots yet. Turn on with agent_view('on') and run a locate/click."
        with open(LATEST_FILE, "r", encoding="utf-8") as f:
            path = f.read().strip()
        if not os.path.exists(path):
            return f"Latest recorded file is missing: {path}"
        if open_file:
            try:
                os.startfile(path)  # noqa — Windows only, by design
            except Exception as exc:
                return f"Latest: {path} (could not open: {exc})"
        return f"Latest agent view: {path}"
    return f"ERROR: unknown agent_view action '{action}' (use latest|on|off|status)"
