import sys
from core.trace import trace as _jtrace
import logging

logger = logging.getLogger(__name__)

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    _jtrace(f"[TRACE] core.system.sensory.vibration.<module>: except ImportError")
    HAS_PSUTIL = False

class VibrationLayer:
    """System state vibrations — underlying environmental state."""
    
    def __init__(self):
        self.last = None
        
    def read(self) -> dict:
        _jtrace(f"[TRACE] core.system.sensory.vibration.VibrationLayer.read: enter")
        if not HAS_PSUTIL:
            return {
                "cpu": 0.0,
                "memory": 0.0,
                "disk_io": 0,
                "net_io": 0,
                "deltas": {}
            }
            
        try:
            # interval=None is non-blocking and calculates percent since last call/import
            cpu = psutil.cpu_percent(interval=None)
            mem = psutil.virtual_memory().percent
            
            disk = psutil.disk_io_counters()
            disk_val = (disk.read_bytes + disk.write_bytes) if disk else 0
            
            net = psutil.net_io_counters()
            net_val = (net.bytes_sent + net.bytes_recv) if net else 0
            
            current = {
                "cpu": cpu,
                "memory": mem,
                "disk_io": disk_val,
                "net_io": net_val,
            }
            
            deltas = {}
            if self.last:
                deltas = {
                    "cpu_spike": cpu > 40 and cpu - self.last["cpu"] > 15,
                    "memory_jump": mem - self.last["memory"] > 5,
                    "disk_burst": current["disk_io"] - self.last["disk_io"] > 1e7,
                    "net_burst": current["net_io"] - self.last["net_io"] > 5e6,
                }
                
            self.last = current
            return {**current, "deltas": deltas}
        except Exception as e:
            _jtrace(f"[TRACE] core.system.sensory.vibration.VibrationLayer.read: except {str(e)[:80]}")
            logger.debug(f"[Vibration] Error reading system metrics: {e}")
            return {
                "cpu": 0.0,
                "memory": 0.0,
                "disk_io": 0,
                "net_io": 0,
                "deltas": {}
            }
