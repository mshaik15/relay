from abc import ABC, abstractmethod

class PLCDriver(ABC):
    @abstractmethod
    def connect(self) -> None:
        """ Establish connection to the PLC, PLCConnectionError on failure """
        ...
    
    @abstractmethod
    def disconnect(self) -> None:
        """ Closes connection to the PLC, PLCConnectionError on failure """
        ...
    
    @abstractmethod
    def write_output(self, tag: str, value: bool) -> None:
        """ Write boolean to tag, PLCWriteError on failure """
        ...
    
    @abstractmethod
    def read_output(self, tag: str) -> bool:
        """ Read boolean from tag, PLCReadError on failure """
        ...
    
    @abstractmethod
    def is_connected(self) -> bool:
        """ Returns True if connection is active, False if not connected """
        ...

class PLCConnectionError(Exception):
    """ connection/disconnect failed """
    pass

class PLCWriteError(Exception):
    """ write failed """
    pass

class PLCReadError(Exception):
    """ read failed """
    pass
