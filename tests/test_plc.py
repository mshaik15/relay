import struct
import pytest
from unittest.mock import MagicMock, patch

from relay.plc.base import PLCConnectionError, PLCReadError, PLCWriteError
from relay.plc.s7 import s7Driver, _parse_tag, _AREA


# helpers
def make_s7(ip="192.168.0.1", rack=0, slot=2):
    return s7Driver(ip=ip, rack=rack, slot=slot)

def cotp_cc_response() -> bytes:
    cotp_cc = bytes([0x06, 0xD0, 0x00, 0x00, 0x00, 0x01, 0x00])
    length = 4 + len(cotp_cc)
    return struct.pack("!BBH", 3, 0, length) + cotp_cc

def s7_ack_response() -> bytes:
    cotp_dt = bytes([0x02, 0xF0, 0x80])
    s7_ack = bytes([
        0x32, 0x03,
        0x00, 0x00,
        0x00, 0x01,
        0x00, 0x08,
        0x00, 0x00,
        0x00, 0x00,
        0xF0, 0x00,
        0x00, 0x01, 0x00, 0x01,
        0x01, 0xE0,
    ])
    body = cotp_dt + s7_ack
    return struct.pack("!BBH", 3, 0, 4 + len(body)) + body

def write_ok_response() -> bytes:
    cotp_dt = bytes([0x02, 0xF0, 0x80])
    s7_ack = bytes([
        0x32, 0x03,
        0x00, 0x00,
        0x00, 0x01,
        0x00, 0x02,
        0x00, 0x00,
        0x00, 0x00,
        0x05, 0x00,
    ])
    result = bytes([0xFF])
    body = cotp_dt + s7_ack + result
    return struct.pack("!BBH", 3, 0, 4 + len(body)) + body

def write_err_response() -> bytes:
    cotp_dt = bytes([0x02, 0xF0, 0x80])
    s7_ack = bytes([
        0x32, 0x03,
        0x00, 0x00,
        0x00, 0x01,
        0x00, 0x02,
        0x00, 0x00,
        0x00, 0x00,
        0x05, 0x00,
    ])
    result = bytes([0x0A]) # non-0xFF → error
    body = cotp_dt + s7_ack + result
    return struct.pack("!BBH", 3, 0, 4 + len(body)) + body

def read_ok_response(value: bool) -> bytes:
    cotp_dt = bytes([0x02, 0xF0, 0x80])
    s7_ack = bytes([
        0x32, 0x03, # protocol, Ack-Data
        0x00, 0x00, # reserved
        0x00, 0x01, # PDU ref
        0x00, 0x02, # param len
        0x00, 0x05, # data len
        0x00, 0x00, # error class/code
    ])                                                     
    data = bytes([0xFF, 0x03, 0x00, 0x01, 0x01 if value else 0x00])
    body = cotp_dt + s7_ack + data
    return struct.pack("!BBH", 3, 0, 4 + len(body)) + body

def make_mock_socket(responses: list[bytes]):
    sock = MagicMock()
    buffers = []
    for pkt in responses:
        buffers.append(pkt[:4])
        buffers.append(pkt[4:])
    buf_iter = iter(buffers)

    def recv_side_effect(n):
        try:
            return next(buf_iter)
        except StopIteration:
            return b""

    sock.recv.side_effect = recv_side_effect
    return sock

def connected_driver(extra_responses=None):
    responses = [cotp_cc_response(), s7_ack_response()] + (extra_responses or [])
    with patch("relay.plc.s7.socket.socket") as mock_cls:
        mock_cls.return_value = make_mock_socket(responses)
        driver = make_s7()
        driver.connect()
    return driver


# parse_tag
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

def test_parse_tag_lowercase_normalised():
    area, byte_off, bit_off = _parse_tag("q0.0")
    assert area == _AREA["Q"]

def test_parse_tag_timer():
    area, byte_off, bit_off = _parse_tag("T5.0")
    assert area == _AREA["T"]

def test_parse_tag_counter():
    area, byte_off, bit_off = _parse_tag("C3.0")
    assert area == _AREA["C"]

def test_parse_tag_no_dot_defaults_bit_zero():
    area, byte_off, bit_off = _parse_tag("M4")
    assert byte_off == 4
    assert bit_off == 0

def test_parse_tag_invalid_prefix_raises():
    with pytest.raises(ValueError):
        _parse_tag("X5.0")

def test_parse_tag_empty_raises():
    with pytest.raises((ValueError, IndexError)):
        _parse_tag("")


# s7Driver — connection
@patch("relay.plc.s7.socket.socket")
def test_connect_success(mock_cls):
    mock_cls.return_value = make_mock_socket([cotp_cc_response(), s7_ack_response()])
    driver = make_s7()
    driver.connect()
    assert driver.is_connected()

@patch("relay.plc.s7.socket.socket")
def test_connect_cotp_bad_response_raises(mock_cls):
    bad = struct.pack("!BBH", 3, 0, 5) + bytes([0x00])
    mock_cls.return_value = make_mock_socket([bad])
    driver = make_s7()
    with pytest.raises(PLCConnectionError):
        driver.connect()
    assert not driver.is_connected()

@patch("relay.plc.s7.socket.socket")
def test_connect_tcp_failure_raises(mock_cls):
    sock = MagicMock()
    sock.connect.side_effect = OSError("refused")
    mock_cls.return_value = sock
    driver = make_s7()
    with pytest.raises(PLCConnectionError):
        driver.connect()
    assert not driver.is_connected()

@patch("relay.plc.s7.socket.socket")
def test_disconnect_clears_connection(mock_cls):
    mock_cls.return_value = make_mock_socket([cotp_cc_response(), s7_ack_response()])
    driver = make_s7()
    driver.connect()
    driver.disconnect()
    assert not driver.is_connected()

def test_not_connected_by_default():
    driver = make_s7()
    assert not driver.is_connected()


# s7Driver — write commands
def test_write_not_connected_raises():
    driver = make_s7()
    with pytest.raises(PLCWriteError, match="Not connected"):
        driver.write_output("Q0.0", True)

def test_write_invalid_tag_raises():
    driver = make_s7()
    driver._sock = MagicMock()
    with pytest.raises(PLCWriteError, match="Invalid tag"):
        driver.write_output("BADTAG", True)

@patch("relay.plc.s7.socket.socket")
def test_write_success(mock_cls):
    mock_cls.return_value = make_mock_socket([
        cotp_cc_response(), s7_ack_response(), write_ok_response()
    ])
    driver = make_s7()
    driver.connect()
    driver.write_output("Q0.0", True) # shouldnt raise

@patch("relay.plc.s7.socket.socket")
def test_write_plc_error_raises(mock_cls):
    mock_cls.return_value = make_mock_socket([
        cotp_cc_response(), s7_ack_response(), write_err_response()
    ])
    driver = make_s7()
    driver.connect()
    with pytest.raises(PLCWriteError):
        driver.write_output("Q0.0", True)


# s7Driver — read commands
def test_read_not_connected_raises():
    driver = make_s7()
    with pytest.raises(PLCReadError, match="Not connected"):
        driver.read_output("Q0.0")

@patch("relay.plc.s7.socket.socket")
def test_read_returns_true(mock_cls):
    mock_cls.return_value = make_mock_socket([
        cotp_cc_response(), s7_ack_response(), read_ok_response(True)
    ])
    driver = make_s7()
    driver.connect()
    assert driver.read_output("Q0.0") is True

@patch("relay.plc.s7.socket.socket")
def test_read_returns_false(mock_cls):
    mock_cls.return_value = make_mock_socket([
        cotp_cc_response(), s7_ack_response(), read_ok_response(False)
    ])
    driver = make_s7()
    driver.connect()
    assert driver.read_output("Q0.0") is False


# ABDriver
def make_ab():
    from relay.plc.ab import ABDriver
    return ABDriver(ip="192.168.0.2", slot=0)

def mock_pylogix(status="Success", time_status="Success", read_value=True):
    plc = MagicMock()
    plc.GetPLCTime.return_value = MagicMock(Status=time_status)
    plc.Write.return_value      = MagicMock(Status=status)
    plc.Read.return_value       = MagicMock(Status=status, Value=read_value)
    return plc


@patch("relay.plc.ab._PylogixPLC")
def test_ab_connect_success(mock_cls):
    mock_cls.return_value = mock_pylogix()
    driver = make_ab()
    driver.connect()
    assert driver.is_connected()

@patch("relay.plc.ab._PylogixPLC")
def test_ab_connect_probe_failure_raises(mock_cls):
    mock_cls.return_value = mock_pylogix(time_status="Timeout")
    driver = make_ab()
    with pytest.raises(PLCConnectionError):
        driver.connect()

@patch("relay.plc.ab._PylogixPLC")
def test_ab_disconnect_clears_connection(mock_cls):
    mock_cls.return_value = mock_pylogix()
    driver = make_ab()
    driver.connect()
    driver.disconnect()
    assert not driver.is_connected()

@patch("relay.plc.ab._PylogixPLC")
def test_ab_write_success(mock_cls):
    plc = mock_pylogix()
    mock_cls.return_value = plc
    driver = make_ab()
    driver.connect()
    driver.write_output("MyTag", True)
    plc.Write.assert_called_once_with("MyTag", True)

@patch("relay.plc.ab._PylogixPLC")
def test_ab_write_false_value(mock_cls):
    plc = mock_pylogix()
    mock_cls.return_value = plc
    driver = make_ab()
    driver.connect()
    driver.write_output("MyTag", False)
    plc.Write.assert_called_once_with("MyTag", False)

@patch("relay.plc.ab._PylogixPLC")
def test_ab_write_plc_error_raises(mock_cls):
    mock_cls.return_value = mock_pylogix(status="Timeout")
    driver = make_ab()
    driver.connect()
    with pytest.raises(PLCWriteError):
        driver.write_output("MyTag", True)

@patch("relay.plc.ab._PylogixPLC")
def test_ab_read_true(mock_cls):
    mock_cls.return_value = mock_pylogix(read_value=True)
    driver = make_ab()
    driver.connect()
    assert driver.read_output("MyTag") is True

@patch("relay.plc.ab._PylogixPLC")
def test_ab_read_false(mock_cls):
    mock_cls.return_value = mock_pylogix(read_value=False)
    driver = make_ab()
    driver.connect()
    assert driver.read_output("MyTag") is False

@patch("relay.plc.ab._PylogixPLC")
def test_ab_read_plc_error_raises(mock_cls):
    mock_cls.return_value = mock_pylogix(status="Timeout")
    driver = make_ab()
    driver.connect()
    with pytest.raises(PLCReadError):
        driver.read_output("MyTag")

def test_ab_write_not_connected_raises():
    driver = make_ab()
    with pytest.raises(PLCWriteError, match="Not connected"):
        driver.write_output("MyTag", True)

def test_ab_read_not_connected_raises():
    driver = make_ab()
    with pytest.raises(PLCReadError, match="Not connected"):
        driver.read_output("MyTag")


"""
    To run use
    uv run pytest tests/test_plc.py -v
"""