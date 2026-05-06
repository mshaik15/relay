import socket
import struct
from .base import PLCDriver, PLCConnectionError, PLCReadError, PLCWriteError

# memory area codes
_AREA = {
    "I": 0x81,  # inputs
    "Q": 0x82,  # outputs
    "M": 0x83,  # merkers
    "DB": 0x84, # data blocks
    "C": 0x1C,  # counters
    "T": 0x1D,  # timers
}

# s7 variable type codes 
_VTYPE_BIT  = 0x01
_VTYPE_BYTE = 0x02

# port
_s7_PORT = 102

# tag parser
def _parse_tag(tag: str) -> tuple[int, int, int]:
    """ parse a tag string into area_code, byte_offset, bit_offset """
    tag = tag.strip().upper()
    for prefix in ("DB", "I", "Q", "M", "C", "T"):
        if tag.startswith(prefix):
            area_code = _AREA[prefix]
            rest = tag[len(prefix):]
            break
    else:
        raise ValueError(f"Unknown area in tag: {tag!r}")
    
    if "." in rest:
        byte_str, bit_str = rest.split(".", 1)
        byte_offset = int(byte_str)
        bit_offset  = int(bit_str)
    else:
        byte_offset = int(rest)
        bit_offset  = 0
 
    return area_code, byte_offset, bit_offset

# packet builders
def _tpkt(payload: bytes) -> bytes:
    """ wrap the payload in a 4-byte TPKT header """
    length = 4 + len(payload)
    return struct.pack("!BBH", 3, 0, length) + payload

def _cotp_cr(rack: int, slot: int) -> bytes:
    """ build a COTP connection request and encode the rack/slot into the destinations TSAP """
    src_tsap = bytes([0xC1, 0x02, 0x01, 0x00]) # param code, len, tsap bytes
    dst_tsap = bytes([0xC2, 0x02, 0x01, (rack * 0x20) + slot])
    tpdu_size = bytes([0xC0, 0x01, 0x0A]) # propose 1024-byte TPDU
 
    body = struct.pack(
        "!BHHB",
        0xE0, # PDU type: connection request
        0x0000, # dst ref
        0x0001, # src ref
        0x00, # class/option
    ) + src_tsap + dst_tsap + tpdu_size
 
    # COTP length byte = len(body) - 1 (excludes the length byte itself)
    return bytes([len(body)]) + body

def _cotp_dt(payload: bytes) -> bytes:
    """ wrap payload into a COTP DF """
    return bytes([0x02, 0xF0, 0x80]) + payload


def _s7_header(msg_type: int, param_len: int, data_len: int, pdu_ref: int = 1) -> bytes:
    """ Build a s7 communication parameter block """
    return struct.pack(
        "!BBHHHH", # but PDU ref is little-endian, pack separately
        0x32, # protocol ID
        msg_type,
        0x0000,
        pdu_ref, # PDU reference (copied back in replies) , actually big-endian per spec
        param_len,
        data_len,
    )


def _s7_negotiate_params() -> bytes:
    """ s7 Setup Communication parameter block, function 0xF0 """
    return struct.pack(
        "!BBHHH",
        0xF0, # function: Setup Communication
        0x00, # reserved
        0x0001, # max AMQ caller (parallel jobs we can send)
        0x0001, # max AMQ callee
        0x01E0, # max PDU size = 480
    )

def _s7_write_bit_params(area: int, byte_offset: int, bit_offset: int) -> bytes:
    """s7 Write Variable parameter block for a single bit."""
    bit_address = (byte_offset * 8 + bit_offset).to_bytes(3, "big")
    request_item = bytes([
        0x12, # spec type: Variable Specification
        0x0A, # length of remaining item = 10
        0x10, # syntax ID: any-type addressing
        _VTYPE_BIT, # variable type: BIT
        0x00, 0x01, # count = 1
        0x00, 0x00, # DB number = 0 (not a DB)
        area, # memory area
    ]) + bit_address
    return bytes([0x05, 0x01]) + request_item  # func=Write, item_count=1
 
 
def _s7_write_bit_data(value: bool) -> bytes:
    """ s7 write variable data block for a bit """
    return bytes([
        0x00, # error code (0 in requests)
        0x03, # transport size: BIT
        0x00, 0x01, # length = 1
        0x01 if value else 0x00,
        0x00, # padding to even boundary
    ])
 
 
def _s7_read_bit_params(area: int, byte_offset: int, bit_offset: int) -> bytes:
    """ s7 read variable parameter block for a bit """
    bit_address = (byte_offset * 8 + bit_offset).to_bytes(3, "big")
    request_item = bytes([
        0x12,
        0x0A,
        0x10,
        _VTYPE_BIT,
        0x00, 0x01,
        0x00, 0x00,
        area,
    ]) + bit_address
    return bytes([0x04, 0x01]) + request_item # func=Read, item_count=1
 
 
# driver
 
class s7Driver(PLCDriver):
    """ simulated s7 TCP driver, connects to a Siemens s7-300/400 PLC over port 102 in python """
 
    def __init__(self, ip: str, rack: int = 0, slot: int = 2):
        self._ip   = ip
        self._rack = rack
        self._slot = slot
        self._sock: socket.socket | None = None
        self._pdu_ref = 1
 
    # internal input output
 
    def _send_recv(self, data: bytes) -> bytes:
        """ Send a raw packet and return the full response payload (minus TPKT header) """
        assert self._sock is not None
        try:
            self._sock.sendall(data)
            # read the 4-byte TPKT header first to learn total length
            header = self._recv_exact(4)
            _ver, _res, length = struct.unpack("!BBH", header)
            body = self._recv_exact(length - 4)
            return body
        except OSError as e:
            raise PLCConnectionError(f"Socket error during send/recv: {e}") from e
 
    def _recv_exact(self, n: int) -> bytes:
        """ read n bytes from the socket """
        buf = bytearray()
        while len(buf) < n:
            chunk = self._sock.recv(n - len(buf))  # type: ignore[union-attr]
            if not chunk:
                raise PLCConnectionError("Connection closed by PLC during read")
            buf.extend(chunk)
        return bytes(buf)
 
    def _next_pdu_ref(self) -> int:
        """ Return the next PDU reference counter, wrapping at 0xFFFF """
        ref = self._pdu_ref
        self._pdu_ref = (self._pdu_ref % 0xFFFF) + 1
        return ref
 
    # handshake connection
 
    def _cotp_connect(self) -> None:
        """ send COTP CR, expect COTP CC """
        cr_packet = _tpkt(_cotp_cr(self._rack, self._slot))
        response = self._send_recv(cr_packet)
        # response[1] is the COTP PDU type; 0xD0 = Connection Confirm
        if len(response) < 2 or response[1] != 0xD0:
            raise PLCConnectionError(
                f"COTP handshake failed , expected CC (0xD0), got: {response.hex()}"
            )
 
    def _s7_negotiate(self) -> None:
        """ send s7 Setup Communication, expect Ack-Data """
        params = _s7_negotiate_params()
        header = _s7_header(0x01, len(params), 0, self._next_pdu_ref())
        s7_pdu = header + params
        packet = _tpkt(_cotp_dt(s7_pdu))
        response = self._send_recv(packet)
        # Skip COTP DT header (3 bytes), then check s7 message type
        s7 = response[3:]
        if len(s7) < 2 or s7[1] != 0x03:
            raise PLCConnectionError(
                f"s7 negotiate failed , expected Ack-Data (0x03), got: {response.hex()}"
            )
 
    # PLCDriver interface
 
    def connect(self) -> None:
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._sock.settimeout(5.0)
            self._sock.connect((self._ip, _s7_PORT))
        except OSError as e:
            self._sock = None
            raise PLCConnectionError(f"TCP connect to {self._ip}:{_s7_PORT} failed: {e}") from e
 
        try:
            self._cotp_connect()
            self._s7_negotiate()
        except PLCConnectionError:
            self._sock.close()
            self._sock = None
            raise
 
    def disconnect(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError as e:
                raise PLCConnectionError(f"Error closing socket: {e}") from e
            finally:
                self._sock = None
 
    def is_connected(self) -> bool:
        return self._sock is not None
 
    def write_output(self, tag: str, value: bool) -> None:
        if not self.is_connected():
            raise PLCWriteError("Not connected")
        try:
            area, byte_off, bit_off = _parse_tag(tag)
        except ValueError as e:
            raise PLCWriteError(f"Invalid tag {tag!r}: {e}") from e
 
        params = _s7_write_bit_params(area, byte_off, bit_off)
        data   = _s7_write_bit_data(value)
        header = _s7_header(0x01, len(params), len(data), self._next_pdu_ref())
        packet = _tpkt(_cotp_dt(header + params + data))
 
        try:
            response = self._send_recv(packet)
        except PLCConnectionError as e:
            raise PLCWriteError(str(e)) from e
 
        # response structure: 3 COTP bytes + 12 s7 Ack-Data header + 1 result byte
        if len(response) < 4:
            raise PLCWriteError(f"Write response too short: {response.hex()}")
        result_byte = response[-1]
        if result_byte != 0xFF:
            raise PLCWriteError(
                f"PLC returned write error for tag {tag!r}: 0x{result_byte:02X}"
            )
 
    def read_output(self, tag: str) -> bool:
        if not self.is_connected():
            raise PLCReadError("Not connected")
        try:
            area, byte_off, bit_off = _parse_tag(tag)
        except ValueError as e:
            raise PLCReadError(f"Invalid tag {tag!r}: {e}") from e
 
        params = _s7_read_bit_params(area, byte_off, bit_off)
        header = _s7_header(0x01, len(params), 0, self._next_pdu_ref())
        packet = _tpkt(_cotp_dt(header + params))
 
        try:
            response = self._send_recv(packet)
        except PLCConnectionError as e:
            raise PLCReadError(str(e)) from e
 
        # response: 3 COTP + 12 s7 header + data
        # data layout: error_code(1), transport_size(1), length(2), data(n)
        data_section = response[3 + 12:]  # skip COTP DT + s7 header
        if len(data_section) < 5:
            raise PLCReadError(f"Read response too short: {response.hex()}")
 
        error_code = data_section[0]
        if error_code != 0xFF:
            raise PLCReadError(
                f"PLC returned read error for tag {tag!r}: 0x{error_code:02X}"
            )
 
        value_byte = data_section[4]
        return bool(value_byte & 0x01)



