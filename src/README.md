# Docs

## Configuration
 
```python
from relay.config import RelayConfig, WatchdogMode
 
config = RelayConfig(
    plc_config={
        "type": "s7",
        "ip": "192.168.0.1",
        "rack": 0,
        "slot": 2,
    },
    confidence_threshold=0.75,
    consecutive_frames=5,
    output_tag="Q0.0",
    safe_state=False,           # value written on watchdog trip or shutdown
    watchdog_mode="halt",       # "halt" exits on trip; "recover" resumes on next heartbeat
)
```

## Usage
 
```python
from relay.config import RelayConfig
from relay.core import RelayPipeline
from relay.vision import VisionModel
from relay.plc.s7 import s7Driver
import cv2
 
config = RelayConfig(...)
driver = s7Driver(ip=config.plc_config.ip, rack=config.plc_config.rack, slot=config.plc_config.slot)
model  = VisionModel(model_path="best.pt", confidence_min=config.confidence_threshold)
 
pipeline = RelayPipeline(config, driver, model)
 
def frames():
    cap = cv2.VideoCapture(0)
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        yield frame
 
pipeline.run(frames())
```

