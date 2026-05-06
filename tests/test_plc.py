import struct
import pytest
from unittest.mock import MagicMock, patch

from relay.plc.base import PLCConnectionError, PLCReadError, PLCWriteError
from relay.plc.s7 import s7Driver, _parse_tag, _AREA


# parse tag unit tests

def test_parse_tag_output_bit():
    area, byte_off, bit_off = _parse_tag("Q0.1")
    assert area == _AREA["Q"]
    assert byte_off == 0
    assert bit_off == 1

def test_parse_tag_merker():
    area, byte_off, bit_off = _parse_tag("M10.3")
    assert area == _AREA["M"]
    assert byte_off == 10
    assert bit_off == 3

def test_parse_tag_input():
    area, byte_off, bit_off = _parse_tag("I2.0")
    assert area == _AREA["I"]
    assert byte_off == 2
    assert bit_off == 0

def test_parse_tag_lowercase():
    area, byte_off, bit_off = _parse_tag("q0.0")
    assert area == _AREA["Q"]

def test_parse_tag_invalid_raises():
    with pytest.raises(ValueError):
        _parse_tag("X5.0")



# s7Driver connection tests

def _make_s7(ip="192.168.0.1", rack=0, slot=2):
    return s7Driver(ip=ip, rack=rack, slot=slot)


def _cotp_cc_response() -> bytes:
    """Minimal COTP Connection Confirm response (TPKT-wrapped)."""
    cotp_cc = bytes([0x06, 0xD0, 0x00, 0x00, 0x00, 0x01, 0x00])
    length = 4 + len(cotp_cc)
    tpkt = struct.pack("!BBH", 3, 0, length) + cotp_cc
    return tpkt


def _s7_ack_response() -> bytes:
    """Minimal S7 Setup-Communication Ack-Data response."""
    cotp_dt = bytes([0x02, 0xF0, 0x80])
    s7_ack = bytes([
        0x32, 0x03, # protocol, Ack-Data
        0x00, 0x00, # reserved
        0x00, 0x01, # PDU ref
        0x00, 0x08, # param len
        0x00, 0x00, # data len
        0x00, 0x00, # error class/code
        0xF0, 0x00, # function, reserved
        0x00, 0x01, 0x00, 0x01, # AMQ caller/callee
        0x01, 0xE0, # max PDU
    ])
    body = cotp_dt + s7_ack
    length = 4 + len(body)
    tpkt = struct.pack("!BBH", 3, 0, length) + body
    return tpkt


def _make_mock_socket(responses: list[bytes]):
    """Return a mock socket whose recv() streams through the given TPKT responses."""
    sock = MagicMock()
    buffers = []
    for pkt in responses:
        buffers.append(pkt[:4])   # TPKT header
        buffers.append(pkt[4:])   # body
    buf_iter = iter(buffers)

    def recv_side_effect(n):
        try:
            return next(buf_iter)
        except StopIteration:
            return b""

    sock.recv.side_effect = recv_side_effect
    return sock


@patch("relay.plc.s7.socket.socket")
def test_s7_connect_success(mock_socket_cls):
    sock = _make_mock_socket([_cotp_cc_response(), _s7_ack_response()])
    mock_socket_cls.return_value = sock

    driver = _make_s7()
    driver.connect()
    assert driver.is_connected()


@patch("relay.plc.s7.socket.socket")
def test_s7_connect_cotp_failure(mock_socket_cls):
    # Return garbage instead of a CC packet
    bad = struct.pack("!BBH", 3, 0, 5) + bytes([0x00])
    sock = _make_mock_socket([bad])
    mock_socket_cls.return_value = sock

    driver = _make_s7()
    with pytest.raises(PLCConnectionError):
        driver.connect()
    assert not driver.is_connected()


@patch("relay.plc.s7.socket.socket")
def test_s7_disconnect(mock_socket_cls):
    sock = _make_mock_socket([_cotp_cc_response(), _s7_ack_response()])
    mock_socket_cls.return_value = sock

    driver = _make_s7()
    driver.connect()
    driver.disconnect()
    assert not driver.is_connected()


def test_s7_write_not_connected_raises():
    driver = _make_s7()
    with pytest.raises(PLCWriteError, match="Not connected"):
        driver.write_output("Q0.0", True)


def test_s7_read_not_connected_raises():
    driver = _make_s7()
    with pytest.raises(PLCReadError, match="Not connected"):
        driver.read_output("Q0.0")


def test_s7_write_invalid_tag_raises():
    driver = _make_s7()
    driver._sock = MagicMock()  # fake connected state
    with pytest.raises(PLCWriteError, match="Invalid tag"):
        driver.write_output("BADTAG", True)


# ──────────────────────────────────────────────
# ABDriver tests
# ──────────────────────────────────────────────

def _make_ab_driver():
    # Delay import so missing pylogix doesn't break the whole module at collection time
    from relay.plc.ab import ABDriver
    return ABDriver(ip="192.168.0.2", slot=0)


def _mock_pylogix_plc(status="Success", time_status="Success", read_value=True):
    plc = MagicMock()
    plc.GetPLCTime.return_value = MagicMock(Status=time_status)
    plc.Write.return_value      = MagicMock(Status=status)
    plc.Read.return_value       = MagicMock(Status=status, Value=read_value)
    return plc


@patch("relay.plc.ab._PylogixPLC")
def test_ab_connect_success(mock_cls):
    mock_cls.return_value = _mock_pylogix_plc()
    driver = _make_ab_driver()
    driver.connect()
    assert driver.is_connected()


@patch("relay.plc.ab._PylogixPLC")
def test_ab_connect_probe_failure(mock_cls):
    mock_cls.return_value = _mock_pylogix_plc(time_status="Timeout")
    driver = _make_ab_driver()
    with pytest.raises(PLCConnectionError):
        driver.connect()


@patch("relay.plc.ab._PylogixPLC")
def test_ab_write_success(mock_cls):
    plc = _mock_pylogix_plc()
    mock_cls.return_value = plc
    driver = _make_ab_driver()
    driver.connect()
    driver.write_output("MyTag", True)
    plc.Write.assert_called_once_with("MyTag", True)


@patch("relay.plc.ab._PylogixPLC")
def test_ab_write_plc_error(mock_cls):
    mock_cls.return_value = _mock_pylogix_plc(status="Timeout")
    driver = _make_ab_driver()
    driver.connect()
    with pytest.raises(PLCWriteError):
        driver.write_output("MyTag", True)


@patch("relay.plc.ab._PylogixPLC")
def test_ab_read_success(mock_cls):
    mock_cls.return_value = _mock_pylogix_plc(read_value=True)
    driver = _make_ab_driver()
    driver.connect()
    assert driver.read_output("MyTag") is True


@patch("relay.plc.ab._PylogixPLC")
def test_ab_read_false_value(mock_cls):
    mock_cls.return_value = _mock_pylogix_plc(read_value=False)
    driver = _make_ab_driver()
    driver.connect()
    assert driver.read_output("MyTag") is False


def test_ab_write_not_connected_raises():
    driver = _make_ab_driver()
    with pytest.raises(PLCWriteError, match="Not connected"):
        driver.write_output("MyTag", True)


"""
    To run use
    uv run pytest tests/test_plc.py -v
"""