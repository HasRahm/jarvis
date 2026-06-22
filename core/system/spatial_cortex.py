import sys
import time
import hashlib
import asyncio
import logging
import threading
from core.system.sensory.braille import BrailleLayer
from core.system.sensory.sound import SoundLayer
from core.system.sensory.vibration import VibrationLayer
from core.system.sensory.air import AirMovementLayer

logger = logging.getLogger(__name__)

class SpatialContextCortex:
    """
    Fuses all four sensory streams into a continuous
    spatial context model. Fires interrupts on context change.
    The blind person's integrated spatial awareness.
    """
    
    def __init__(self, check_interval_sec: float = 0.5):
        self.check_interval = check_interval_sec
        self.braille = BrailleLayer()
        self.sound = SoundLayer()
        self.vibration = VibrationLayer()
        self.air = AirMovementLayer()
        
        self.current_fingerprint = None
        self.task_registry = {}  # task_id -> home fingerprint
        self.callbacks = []      # registered interrupt handlers
        self.running = False
        self.thread = None
        self.loop = None
        
    def start(self):
        print(f"[TRACE] core.system.spatial_cortex.SpatialContextCortex.start: enter", file=sys.stderr, flush=True)
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True, name="jarvis-spatial-cortex")
        self.thread.start()
        logger.info("[Cortex] Started background spatial context cortex daemon.")
        
    def stop(self):
        print(f"[TRACE] core.system.spatial_cortex.SpatialContextCortex.stop: enter", file=sys.stderr, flush=True)
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)
        logger.info("[Cortex] Stopped background spatial context cortex daemon.")
        
    def register_callback(self, cb):
        self.callbacks.append(cb)
        
    def _run_loop(self):
        print(f"[TRACE] core.system.spatial_cortex.SpatialContextCortex._run_loop: enter", file=sys.stderr, flush=True)
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._main_loop())
        self.loop.close()
        self.loop = None
        
    async def _main_loop(self):
        while self.running:
            try:
                fingerprint = self._fuse_streams()
                
                if self.current_fingerprint:
                    delta = self._fingerprint_delta(
                        self.current_fingerprint,
                        fingerprint
                    )
                    
                    # Soft warning — drift detected
                    if fingerprint["air"]["drift_warning"]:
                        await self._fire("DRIFT_WARNING", fingerprint)
                    
                    # Hard interrupt — context changed
                    elif delta > 0.3:  # 30% change threshold
                        await self._fire("CONTEXT_SWITCH", fingerprint)
                        
                self.current_fingerprint = fingerprint
            except Exception as e:
                print(f"[TRACE] core.system.spatial_cortex.SpatialContextCortex._main_loop: except {str(e)[:80]}", file=sys.stderr, flush=True)
                logger.error(f"[Cortex] Error in sensory loop: {e}")
                
            await asyncio.sleep(self.check_interval)
            
    def _fuse_streams(self) -> dict:
        """Read all four streams and build fingerprint."""
        print(f"[TRACE] core.system.spatial_cortex.SpatialContextCortex._fuse_streams: enter", file=sys.stderr, flush=True)
        b = self.braille.read()
        s = self.sound.read()
        v = self.vibration.read()
        a = self.air.read()
        
        # Build composite identity hash
        identity = hashlib.md5(
            f"{b['hwnd']}{b['tree_hash']}"
            f"{b['page_url']}{a['focus_process']}"
            .encode()
        ).hexdigest()[:12]
        
        return {
            "identity": identity,
            "braille": b,
            "sound": s,
            "vibration": v,
            "air": a,
            "timestamp": time.time()
        }
        
    def _fingerprint_delta(self, old: dict, new: dict) -> float:
        """
        How different are two fingerprints?
        Returns 0.0 (identical) to 1.0 (completely different).
        """
        print(f"[TRACE] core.system.spatial_cortex.SpatialContextCortex._fingerprint_delta: enter", file=sys.stderr, flush=True)
        score = 0.0
        weight = 0.0
        
        # hwnd changed = definitely different (heavy weight)
        if old["braille"]["hwnd"] != new["braille"]["hwnd"]:
            score += 0.5
        weight += 0.5
        
        # tree structure changed (medium weight)
        if old["braille"]["tree_hash"] != new["braille"]["tree_hash"]:
            score += 0.2
        weight += 0.2
        
        # page URL changed (medium weight)
        if old["braille"]["page_url"] != new["braille"]["page_url"]:
            score += 0.2
        weight += 0.2
        
        # keyboard routing changed (light weight)
        if old["air"]["focus_process"] != new["air"]["focus_process"]:
            score += 0.1
        weight += 0.1
        
        return score / weight if weight > 0 else 0.0
        
    async def _fire(self, event_type: str, fingerprint: dict):
        for callback in self.callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(event_type, fingerprint)
                else:
                    callback(event_type, fingerprint)
            except Exception as e:
                print(f"[TRACE] core.system.spatial_cortex.SpatialContextCortex._fire: except {str(e)[:80]}", file=sys.stderr, flush=True)
                logger.error(f"[Cortex] Error in event callback: {e}")
                
    def register_task(self, task_id: str):
        """Register current context as home for this task."""
        print(f"[TRACE] core.system.spatial_cortex.SpatialContextCortex.register_task: enter", file=sys.stderr, flush=True)
        if not self.current_fingerprint:
            self.current_fingerprint = self._fuse_streams()
        self.task_registry[task_id] = {
            "home": self.current_fingerprint,
            "registered_at": time.time()
        }
        logger.info(f"[Cortex] Registered task '{task_id}' home context: {self.current_fingerprint['identity']}")
        
    def is_home_context(self, task_id: str) -> bool:
        """Is the current context the home for this task?"""
        print(f"[TRACE] core.system.spatial_cortex.SpatialContextCortex.is_home_context: enter", file=sys.stderr, flush=True)
        if task_id not in self.task_registry:
            return True
            
        home = self.task_registry[task_id]["home"]
        current = self._fuse_streams()
        delta = self._fingerprint_delta(home, current)
        logger.debug(f"[Cortex] Checking context for '{task_id}': Delta={delta:.2f} (threshold: 0.3)")
        return delta < 0.3
