from .base import PLCDriver, PLCConnectionError, PLCReadError, PLCWriteError

try:
    from pylogix import PLC as _PylogixPLC
except ImportError as _e:
    raise ImportError(
        "pylogix is required for Allen-Bradley support. "
        "Install it with: uv add 'relay[ab]'"
    ) from _e


class ABDriver(PLCDriver):
    """ Allen-Bradley EtherNet/IP driver that connects to ControlLogix and CompactLogix PLCs over TCP/44818 """
    def __init__(self, ip: str, slot: int = 0):
        self._ip   = ip
        self._slot = slot
        self._plc: _PylogixPLC | None = None

    # PLCDriver interface 
    def connect(self) -> None:
        try:
            plc = _PylogixPLC()
            plc.IPAddress   = self._ip
            plc.ProcessorSlot = self._slot
            result = plc.GetPLCTime()
            if result.Status != "Success":
                raise PLCConnectionError(
                    f"AB connect probe failed for {self._ip} slot {self._slot}: "
                    f"{result.Status}"
                )
            
            self._plc = plc
        except PLCConnectionError:
            raise
        except Exception as e:
            raise PLCConnectionError(
                f"AB connect to {self._ip} failed: {e}"
            ) from e

    def disconnect(self) -> None:
        if self._plc is not None:
            try:
                self._plc.Close()
            except Exception as e:
                raise PLCConnectionError(f"AB disconnect error: {e}") from e
            finally:
                self._plc = None

    def is_connected(self) -> bool:
        return self._plc is not None

    def write_output(self, tag: str, value: bool) -> None:
        if not self.is_connected():
            raise PLCWriteError("Not connected")
        try:
            result = self._plc.Write(tag, value) # type: ignore[union-attr]
        except Exception as e:
            raise PLCWriteError(f"AB write error on tag {tag!r}: {e}") from e

        if result.Status != "Success":
            raise PLCWriteError(
                f"AB write failed for tag {tag!r}: {result.Status}"
            )

    def read_output(self, tag: str) -> bool:
        if not self.is_connected():
            raise PLCReadError("Not connected")
        try:
            result = self._plc.Read(tag) # type: ignore[union-attr]
        except Exception as e:
            raise PLCReadError(f"AB read error on tag {tag!r}: {e}") from e

        if result.Status != "Success":
            raise PLCReadError(
                f"AB read failed for tag {tag!r}: {result.Status}"
            )
        return bool(result.Value)