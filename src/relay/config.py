from typing import Union, Annotated, Literal
from enum import Enum
from pydantic import BaseModel, Field, field_validator

class PLCType(str, Enum):
    s7 = 's7'
    ab = 'ab'

class S7Config(BaseModel):
    type: Literal[PLCType.s7] = PLCType.s7
    ip: str
    rack: int = 0
    slot: int = 2

class ABConfig(BaseModel):
    type: Literal[PLCType.ab] = PLCType.ab
    ip: str
    slot: int = 0

PLCConfig = Annotated[Union[S7Config, ABConfig], Field(discriminator='type')]

class RelayConfig(BaseModel):
    plc_config: PLCConfig
    confidence_threshold: float
    consecutive_frames: int
    output_tag: str

    @field_validator("confidence_threshold")
    @classmethod
    def validate_confidence(cls, x:float) -> float:
        if not 0.0 < x < 1.0:
            raise ValueError("confidence_threshold must be between 0 and 1, exclusive")
        return x
    
    @field_validator("consecutive_frames")
    @classmethod
    def validate_frames(cls, y:int) -> int:
        if not 0 < y:
            raise ValueError("consecutive_frames must be greater than 0")
        return y