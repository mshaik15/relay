import pytest
from pydantic import ValidationError
from relay.config import RelayConfig, WatchdogMode, S7Config, ABConfig

# helpers
S7_BASE = {
    "type": "s7",
    "ip": "192.168.0.1",
    "rack": 0,
    "slot": 2,
}

AB_BASE = {
    "type": "ab",
    "ip": "192.168.0.2",
    "slot": 0,
}

def make_config(plc=None, **overrides):
    defaults = dict(
        plc_config=plc or S7_BASE,
        confidence_threshold=0.75,
        consecutive_frames=5,
        output_tag="Q0.0",
    )
    defaults.update(overrides)
    return RelayConfig(**defaults)


# S7Config
def test_s7_config_defaults():
    cfg = S7Config(ip="10.0.0.1")
    assert cfg.rack == 0
    assert cfg.slot == 2
    assert cfg.type == "s7"

def test_s7_config_explicit_rack_slot():
    cfg = S7Config(ip="10.0.0.1", rack=1, slot=3)
    assert cfg.rack == 1
    assert cfg.slot == 3


# ABConfig
def test_ab_config_defaults():
    cfg = ABConfig(ip="10.0.0.2")
    assert cfg.slot == 0
    assert cfg.type == "ab"

def test_ab_config_explicit_slot():
    cfg = ABConfig(ip="10.0.0.2", slot=4)
    assert cfg.slot == 4


# RelayConfig construction
def test_valid_s7_config():
    cfg = make_config()
    assert cfg.confidence_threshold == 0.75
    assert cfg.consecutive_frames == 5
    assert cfg.output_tag == "Q0.0"

def test_valid_ab_config():
    cfg = make_config(plc=AB_BASE)
    assert cfg.plc_config.type == "ab"

def test_default_safe_state_is_false():
    cfg = make_config()
    assert cfg.safe_state is False

def test_safe_state_true():
    cfg = make_config(safe_state=True)
    assert cfg.safe_state is True

def test_default_watchdog_mode_is_stop():
    cfg = make_config()
    assert cfg.watchdog_mode == WatchdogMode.stop

def test_watchdog_mode_recover():
    cfg = make_config(watchdog_mode="recover")
    assert cfg.watchdog_mode == WatchdogMode.recover


# confidence_threshold validation
def test_confidence_boundary_low():
    with pytest.raises(ValidationError):
        make_config(confidence_threshold=0.0)

def test_confidence_boundary_high():
    with pytest.raises(ValidationError):
        make_config(confidence_threshold=1.0)

def test_confidence_below_zero():
    with pytest.raises(ValidationError):
        make_config(confidence_threshold=-0.1)

def test_confidence_above_one():
    with pytest.raises(ValidationError):
        make_config(confidence_threshold=1.5)

def test_confidence_valid_low_edge():
    cfg = make_config(confidence_threshold=0.01)
    assert cfg.confidence_threshold == 0.01

def test_confidence_valid_high_edge():
    cfg = make_config(confidence_threshold=0.99)
    assert cfg.confidence_threshold == 0.99


# consecutive_frames validation
def test_consecutive_frames_zero_raises():
    with pytest.raises(ValidationError):
        make_config(consecutive_frames=0)

def test_consecutive_frames_negative_raises():
    with pytest.raises(ValidationError):
        make_config(consecutive_frames=-1)

def test_consecutive_frames_one_is_valid():
    cfg = make_config(consecutive_frames=1)
    assert cfg.consecutive_frames == 1

def test_consecutive_frames_large_is_valid():
    cfg = make_config(consecutive_frames=1000)
    assert cfg.consecutive_frames == 1000


# other tests
def test_unknown_plc_type_raises():
    with pytest.raises(ValidationError):
        make_config(plc={"type": "travis_scott", "ip": "10.0.0.3"})

def test_missing_plc_ip_raises():
    with pytest.raises(ValidationError):
        make_config(plc={"type": "s7"})


"""
    To run use
    uv run pytest tests/test_config.py -v
"""