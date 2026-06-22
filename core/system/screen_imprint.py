import sys
from core.trace import trace as _jtrace
# core/system/screen_imprint.py
import mss
import cv2
import numpy as np
import asyncio
from typing import Dict, List, Any, Callable, Awaitable

class ScreenImprintGraph:
    """
    Constructs a visual density map of the screen using grid halftone intensity analysis.
    Enables low-cost screen delta checks and physical-attention mapping.
    """
    
    def __init__(self, grid_size: int = 32):
        self.grid_size = grid_size
        self.last_imprint = None

    def imprint(self) -> Dict[str, Any]:
        """Captures the screen and builds the halftone density matrix utilizing high-speed NumPy vectorization."""
        with mss.mss() as sct:
            monitor = sct.monitors[1]  # Primary monitor
            screenshot = sct.grab(monitor)
            
            # Convert raw BGRA screenshot to numpy array and grayscale
            img = np.array(screenshot)
            gray = cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)
            h, w = gray.shape

            # Calculate cells dimensions
            cell_h = h // self.grid_size
            cell_w = w // self.grid_size

            # Compute Sobel edges for visual details/boundaries
            edges = cv2.Sobel(gray, cv2.CV_64F, 1, 1, ksize=3)
            edges_abs = np.absolute(edges)
            edges_max = np.max(edges_abs)
            edges_normalized = np.uint8(255 * edges_abs / edges_max if edges_max > 0 else edges_abs)

            # --- Correction 2: Vectorized NumPy block operations instead of nested loops ---
            # Trim to exact multiples
            trimmed_gray = gray[:self.grid_size * cell_h, :self.grid_size * cell_w]
            # Reshape into grid blocks in one operation
            blocks = trimmed_gray.reshape(self.grid_size, cell_h, self.grid_size, cell_w)
            # Mean of each block = density
            density_matrix = blocks.mean(axis=(1, 3))

            # Trim edges and reshape
            trimmed_edges = edges_normalized[:self.grid_size * cell_h, :self.grid_size * cell_w]
            edge_blocks = trimmed_edges.reshape(self.grid_size, cell_h, self.grid_size, cell_w)
            # Mean of edges
            edge_matrix = edge_blocks.mean(axis=(1, 3))

            # --- Correction 3: Vectorized ASCII index clipping to prevent out-of-bounds ---
            ascii_chars = " .:-=+*#%@"
            normalized = np.clip((density_matrix / 255.0 * 9).astype(int), 0, 9)
            ascii_map = [
                "".join(ascii_chars[normalized[i, j]] for j in range(self.grid_size))
                for i in range(self.grid_size)
            ]

            current_imprint = {
                "density": density_matrix.tolist(),
                "edges": edge_matrix.tolist(),
                "ascii_map": "\n".join(ascii_map),
                "resolution": {"w": w, "h": h},
                "grid_dims": {"rows": self.grid_size, "cols": self.grid_size, "cell_w": cell_w, "cell_h": cell_h}
            }

            changes = {"changed": False, "regions": []}
            if self.last_imprint is not None:
                changes = self._compute_deltas(self.last_imprint, current_imprint)

            self.last_imprint = current_imprint
            return {
                "imprint": current_imprint,
                "changes": changes
            }

    def _compute_deltas(self, prev: Dict[str, Any], curr: Dict[str, Any]) -> Dict[str, Any]:
        _jtrace(f"[TRACE] core.system.screen_imprint.ScreenImprintGraph._compute_deltas: enter")
        p_dens = np.array(prev["density"])
        c_dens = np.array(curr["density"])
        
        diff = np.abs(c_dens - p_dens)
        threshold = 15.0  # Visual density variance threshold
        changed_cells = np.argwhere(diff > threshold)

        regions = []
        cell_w = curr["grid_dims"]["cell_w"]
        cell_h = curr["grid_dims"]["cell_h"]

        for row, col in changed_cells:
            regions.append({
                "cell": (int(row), int(col)),
                "x": int(col * cell_w),
                "y": int(row * cell_h),
                "w": int(cell_w),
                "h": int(cell_h),
                "delta": float(diff[row, col])
            })

        # Sort changes by visual impact (largest delta first)
        regions.sort(key=lambda r: r["delta"], reverse=True)

        return {
            "changed": len(regions) > 0,
            "regions": regions
        }

    # --- Open Question 2: Async background watcher ---
    async def watch_screen(self, callback: Callable[[Dict[str, Any]], Awaitable[None]], poll_interval: float = 0.25):
        """Monitors the screen for changes and fires callback automatically on visual changes."""
        _jtrace(f"[TRACE] core.system.screen_imprint.ScreenImprintGraph.watch_screen: enter")
        self.last_imprint = None
        while True:
            try:
                res = self.imprint()
                if res["changes"]["changed"]:
                    await callback(res)  # Await the async callback
            except Exception as e:
                _jtrace(f"[TRACE] core.system.screen_imprint.ScreenImprintGraph.watch_screen: except {str(e)[:80]}")
                print(f"[ScreenImprintGraph Watcher Error]: {e}")
            await asyncio.sleep(poll_interval)
