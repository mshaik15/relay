import time
import pytest
from unittest.mock import MagicMock
from relay.safety import Watchdog


def make_watchdog(interval_ms=50, safe_state=False, recover=False):
    driver = MagicMock()
    w = Watchdog(driver, tag="Q0.0", interval_ms=interval_ms, safe_state=safe_state, recover=recover)
    return w, driver


def test_healthy_with_regular_heartbeats():
    w, driver = make_watchdog(interval_ms=50)
    w.start()
    try:
        for _ in range(5):
            time.sleep(0.03)
            w.heartbeat()
        assert w.is_healthy()
        driver.write_output.assert_not_called()
    finally:
        w.stop()


def test_fires_after_missed_heartbeat():
    w, driver = make_watchdog(interval_ms=50)
    w.start()
    time.sleep(0.2)  # no heartbeat — watchdog should trip
    assert not w.is_healthy()
    driver.write_output.assert_called_with("Q0.0", False)


def test_safe_state_true_is_written_on_trip():
    w, driver = make_watchdog(interval_ms=50, safe_state=True)
    w.start()
    time.sleep(0.2)
    driver.write_output.assert_called_with("Q0.0", True)


def test_halt_mode_stops_thread():
    w, driver = make_watchdog(interval_ms=50, recover=False)
    w.start()
    time.sleep(0.2)
    assert not w.is_healthy()
    # In halt mode the internal thread exits — stop() should return quickly
    start = time.time()
    w.stop()
    assert time.time() - start < 0.5


def test_recover_mode_resumes_after_heartbeat():
    w, driver = make_watchdog(interval_ms=50, recover=True)
    w.start()
    time.sleep(0.2)           # let it trip
    assert not w.is_healthy()

    w.heartbeat()             # heartbeat resets health in recover mode
    assert w.is_healthy()
    w.stop()


def test_write_error_does_not_crash_watchdog():
    driver = MagicMock()
    driver.write_output.side_effect = Exception("PLC unreachable")
    w = Watchdog(driver, tag="Q0.0", interval_ms=50)
    w.start()
    time.sleep(0.2)
    # watchdog should still be running (not crashed), just unhealthy
    assert not w.is_healthy()
    w.stop()


"""
    To run use
    uv run pytest tests/test_safety.py -v
"""