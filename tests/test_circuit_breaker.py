import pytest
import time
from unittest.mock import patch, MagicMock
from core.system.circuit_breaker import CircuitBreaker
from tools.dispatcher import dispatch, _breakers

def test_circuit_breaker_state_transitions():
    cb = CircuitBreaker("test_tool", failure_threshold=2, recovery_timeout=1)
    assert cb.is_available() is True
    assert cb.state == "CLOSED"
    
    cb.record_failure()
    assert cb.is_available() is True
    assert cb.state == "CLOSED"
    
    cb.record_failure()
    assert cb.is_available() is False
    assert cb.state == "OPEN"
    
    # Check that it is still open before timeout
    assert cb.is_available() is False
    
    # Sleep to exceed recovery timeout
    time.sleep(1.1)
    assert cb.is_available() is True
    assert cb.state == "HALF_OPEN"
    
    # Success resets state to CLOSED
    cb.record_success()
    assert cb.is_available() is True
    assert cb.state == "CLOSED"

@patch("tools.dispatcher._dispatch_raw")
def test_dispatch_circuit_breaker_integration(mock_dispatch):
    # Reset breakers cache
    _breakers.clear()
    
    mock_dispatch.return_value = "[SUCCESS] Tool executed"
    
    # First dispatch succeeds
    res = dispatch("test_breaker_tool", {})
    assert res == "[SUCCESS] Tool executed"
    
    # Simulate tool failures
    mock_dispatch.return_value = "[ERROR] Bad execution"
    
    # 1st failure
    res = dispatch("test_breaker_tool", {})
    assert res == "[ERROR] Bad execution"
    
    # 2nd failure
    res = dispatch("test_breaker_tool", {})
    assert res == "[ERROR] Bad execution"
    
    # 3rd failure (trips breaker)
    res = dispatch("test_breaker_tool", {})
    assert res == "[ERROR] Bad execution"
    
    # 4th call should be blocked by open circuit breaker
    res = dispatch("test_breaker_tool", {})
    assert "[ERROR] Circuit breaker is OPEN" in res
