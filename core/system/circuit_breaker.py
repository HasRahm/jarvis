import time
import logging

logger = logging.getLogger(__name__)

class CircuitBreaker:
    def __init__(self, tool_name: str, 
                 failure_threshold: int = 3,
                 recovery_timeout: int = 300):
        self.tool       = tool_name
        self.threshold  = failure_threshold
        self.recovery   = recovery_timeout
        self.failures   = 0
        self.last_fail  = None
        self.state      = "CLOSED"  # CLOSED=normal, OPEN=disabled, HALF_OPEN=testing
        
    def record_failure(self):
        self.failures  += 1
        self.last_fail  = time.time()
        if self.failures >= self.threshold:
            self.state = "OPEN"
            logger.warning(f"⚡ Circuit breaker OPEN: {self.tool} disabled for {self.recovery}s")
            
    def record_success(self):
        self.failures = 0
        self.state    = "CLOSED"
        
    def is_available(self) -> bool:
        if self.state == "CLOSED":
            return True
        # Auto-recover after timeout
        if self.state == "OPEN" and self.last_fail and (time.time() - self.last_fail > self.recovery):
            self.state    = "HALF_OPEN"
            self.failures = 0
            return True
        return False
