import time
import pytest
from unittest.mock import MagicMock
from relay.safety import Watchdog


# helpers

INTERVAL_MS = 50
TRIP_SLEEP  = 0.2 # long enough to guarantee a trip at 50 ms interval

def make_watchdog(interval_ms=INTERVAL_MS, safe_state=False, recover=False):
    driver = MagicMock()
    w = Watchdog(driver, tag="Q0.0", interval_ms=interval_ms, safe_state=safe_state, recover=recover)
    return w, driver


# healthy operation
def test_healthy_with_regular_heartbeats():
    w, driver = make_watchdog()
    w.start()
    try:
        for _ in range(5):
            time.sleep(0.03)
            w.heartbeat()
        assert w.is_healthy()
        driver.write_output.assert_not_called()
    finally:
        w.stop()

def test_is_healthy_before_start():
    w, _ = make_watchdog()
    assert w.is_healthy()


# tripping
def test_fires_after_missed_heartbeat():
    w, driver = make_watchdog()
    w.start()
    time.sleep(TRIP_SLEEP)
    assert not w.is_healthy()
    driver.write_output.assert_called_with("Q0.0", False)

def test_safe_state_false_written_on_trip():
    w, driver = make_watchdog(safe_state=False)
    w.start()
    time.sleep(TRIP_SLEEP)
    driver.write_output.assert_called_with("Q0.0", False)

def test_safe_state_true_written_on_trip():
    w, driver = make_watchdog(safe_state=True)
    w.start()
    time.sleep(TRIP_SLEEP)
    driver.write_output.assert_called_with("Q0.0", True)

def test_tag_name_passed_to_driver():
    driver = MagicMock()
    w = Watchdog(driver, tag="M5.3", interval_ms=INTERVAL_MS)
    w.start()
    time.sleep(TRIP_SLEEP)
    args, _ = driver.write_output.call_args
    assert args[0] == "M5.3"
    w.stop()


# halt mode
def test_halt_mode_thread_exits_after_trip():
    w, _ = make_watchdog(recover=False)
    w.start()
    time.sleep(TRIP_SLEEP)
    assert not w.is_healthy()
    start = time.time()
    w.stop()
    assert time.time() - start < 0.5

def test_halt_mode_stays_unhealthy_after_heartbeat():
    w, _ = make_watchdog(recover=False)
    w.start()
    time.sleep(TRIP_SLEEP)
    w.heartbeat() # heartbeat after trip should not restore health in halt mode
    assert not w.is_healthy()
    w.stop()


# recover mode
def test_recover_mode_resumes_after_heartbeat():
    w, _ = make_watchdog(recover=True)
    w.start()
    time.sleep(TRIP_SLEEP)
    assert not w.is_healthy()
    w.heartbeat()
    assert w.is_healthy()
    w.stop()

def test_recover_mode_can_trip_multiple_times():
    w, driver = make_watchdog(interval_ms=INTERVAL_MS, recover=True)
    w.start()
    time.sleep(TRIP_SLEEP)
    w.heartbeat()
    assert w.is_healthy()
    time.sleep(TRIP_SLEEP)
    assert not w.is_healthy()
    w.stop()


# fault tolerance
def test_write_error_does_not_crash_watchdog():
    driver = MagicMock()
    driver.write_output.side_effect = Exception("PLC unreachable")
    w = Watchdog(driver, tag="Q0.0", interval_ms=INTERVAL_MS)
    w.start()
    time.sleep(TRIP_SLEEP)
    assert not w.is_healthy()
    w.stop()

def test_stop_before_start_does_not_raise():
    w, _ = make_watchdog()
    w.stop() # should be a no-op


"""
    To run use
    uv run pytest tests/test_safety.py -v
"""