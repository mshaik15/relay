# Relay
A Python package for bridging YOLO-based machine vision to industrial PLCs (Allen-Bradley and Siemens) without relying on Cognex or Keyence, and it is written in pure python. Wraps detection, temporal filtering, and PLC I/O into a pipeline deployable in ~15 lines. Installable via pip or uv when deployed (**not deployed yet**)

# How it works
![Relay Diagram](Relay_Diagram.svg)

### Main Thread
`RelayConfig` sits on top, feeding thresholds, tag names, and modes into the pipeline. `RelayPipeline` drives everything — on each `step()` call it pushes the frame into `VisionModel`, takes the top detection, and runs it through a `TemporalFilter`
 
The filter only triggers when the same label clears `confidence_threshold` for `consecutive_frames` in a row. If confidence drops or the label changes, the streak resets. Once triggered, `write_output` sends the result to the selected `PLCDriver` — either `s7Driver` or `ABDriver` — and writes to the PLC

A background watchdog monitors pipeline health via heartbeats. If the pipeline stalls:
 
- **`stop` mode** — writes `safe_state`, marks the pipeline permanently unhealthy, and exits. `step()` will raise a `RuntimeError` until the pipeline is restarted
- **`recover` mode** — writes `safe_state`, marks unhealthy, but rearms itself on the next heartbeat
---

## Installation
 
> Not deployed to PyPI. To use it, clone the repo and install locally:
 
```bash
git clone https://github.com/mshaik15/relay
cd relay
 
# Siemens S7 only
uv add .
 
# With Allen-Bradley support
uv add '.[ab]'
```
 
---
 
## Quick Start
visit [docs](https://github.com/mshaik15/relay/blob/main/src/README.md) for more info on how to use Relay
 
```python
import cv2
from relay.config import RelayConfig
from relay.core import RelayPipeline
from relay.vision import VisionModel
from relay.plc.s7 import s7Driver
 
config = RelayConfig(
    plc_config={"type": "s7", "ip": "192.168.0.1", "rack": 0, "slot": 2},
    confidence_threshold=0.75,
    consecutive_frames=5,
    output_tag="Q0.0",
    safe_state=False,
    watchdog_mode="stop",
)
 
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
 
`pipeline.run()` runs until a `KeyboardInterrupt`, the frame source is exhausted, or the watchdog halts the pipeline. On any exit path it writes `safe_state` and disconnects from the PLC cleanly
 
---

This starteed as a collection of scripts i wrote during my last work term, making it easier to connect YOLO to a PLC without needing Cognex and Keyence. I finally cleaned it up into a proper package for practice and configured for my own work, not a published library. Probably wont work out the box for most people either, **again this was mainly a learning experaince for packaging CV applications and writing test code using tools like pytest**
