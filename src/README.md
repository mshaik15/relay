## Installation -- **ITS NOT DEPLOYED - so it isnt on pip or anything**

```bash
# Siemens S7 only (no extra dependencies)
uv add relay

# Allen-Bradley support
uv add 'relay[ab]'
```

---

## Configuration

All pipeline behaviour is controlled through a `RelayConfig` object.

```python
from relay.config import RelayConfig

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
    safe_state=False,
    watchdog_mode="stop",
)
```

### `plc_config`

Selects and configures the PLC driver. The `type` field acts as a discriminator

**Siemens S7** (`type: "s7"`) — connects over ISO-on-TCP (port 102):

| Field  | Type | Default | Description                        |
|--------|------|---------|------------------------------------|
| `ip`   | str  | —       | PLC IP address                     |
| `rack` | int  | `0`     | PLC rack number                    |
| `slot` | int  | `2`     | CPU slot number                    |

**Allen-Bradley** (`type: "ab"`) — connects over EtherNet/IP (port 44818):

| Field  | Type | Default | Description            |
|--------|------|---------|------------------------|
| `ip`   | str  | —       | PLC IP address         |
| `slot` | int  | `0`     | Processor slot number  |

### `confidence_threshold`

A float in the range `0.0 - 1.0` (exclusive). Detections below this score are ignored. Values at exactly `0.0` or `1.0` are rejected at construction time

### `consecutive_frames`

The number of consecutive frames a detection must exceed `confidence_threshold` before the output tag is written. Must be greater than `0`. Higher values reduce false positives at the cost of response latency

### `output_tag`

The PLC tag or memory address to write when a detection is confirmed

- S7 format: `Q0.0`, `M10.3`, `I2.1`
- Allen-Bradley format: a named tag string, e.g. `"ConveyorRun"`

### `safe_state`

The boolean value written to `output_tag` when the watchdog trips or the pipeline shuts down. Defaults to `False`

### `watchdog_mode`

Controls what happens when the watchdog detects a stalled pipeline

| Value       | Behaviour                                                                   |
|-------------|-----------------------------------------------------------------------------|
| `"stop"`    | Writes `safe_state`, marks pipeline unhealthy, exits the watchdog thread.   |
| `"recover"` | Writes `safe_state`, marks unhealthy, but resumes as soon as a heartbeat arrives. |

---

## Usage

### Minimal example

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

`pipeline.run()` blocks until a `KeyboardInterrupt`, the frame source is exhausted, or the watchdog halts the pipeline. On exit it always writes `safe_state` and disconnects from the PLC

### Allen-Bradley example

```python
from relay.plc.ab import ABDriver

driver = ABDriver(ip="192.168.0.2", slot=0)
config = RelayConfig(
    plc_config={"type": "ab", "ip": "192.168.0.2", "slot": 0},
    confidence_threshold=0.80,
    consecutive_frames=3,
    output_tag="ConveyorRun",
    safe_state=False,
    watchdog_mode="recover",
)
```

### Manual frame stepping

If you need finer control, call `start()` / `step()` / `stop()` directly instead of `run()`

```python
pipeline.start()
try:
    for frame in my_source():
        triggered = pipeline.step(frame)
        if triggered:
            print("Detection confirmed — PLC output written")
finally:
    pipeline.stop()
```

`step()` returns `True` when the detection passed the temporal filter and the PLC write succeeded, and `False` otherwise. It raises `RuntimeError` if the watchdog has tripped

---

## How it works

Each frame passes through three stages before anything is written to the PLC

**1. Detection** — `VisionModel.predict()` runs the YOLO model and returns a list of `Detection(label, confidence)` objects sorted by confidence descending. Only the top detection is considered

**2. Temporal filtering** — `TemporalFilter` counts how many consecutive frames the same label clears `confidence_threshold`. The count resets whenever the label changes, confidence drops below the threshold, or no object is detected. The filter returns `True` only once the streak reaches `consecutive_frames`

**3. PLC write + watchdog heartbeat** — when the filter triggers, `True` is written to `output_tag` and a watchdog heartbeat is recorded. If the pipeline stalls (no heartbeat within the watchdog interval), the watchdog writes `safe_state` to the tag independently from the main thread

---

## Output

`RelayPipeline.step()` returns a single `bool`:

| Return value | Meaning |
|---|---|
| `True` | Detection confirmed for `consecutive_frames` frames; `True` written to `output_tag` |
| `False` | No detection, confidence too low, or streak not yet reached. PLC not written |

On watchdog trip, `safe_state` is written to `output_tag` from the watchdog thread regardless of what `step()` is doing. In `"stop"` mode the pipeline then becomes permanently unhealthy until restarted. In `"recover"` mode it becomes healthy again on the next successful `step()`

On any exit path (interrupt, exhausted source, watchdog halt), `stop()` writes `safe_state` to `output_tag` and disconnects cleanly from the PLC

---

## Logging

Relay uses Python's standard `logging` module under the `relay` logger hierarchy. To see pipeline events:

```python
import logging
logging.basicConfig(level=logging.INFO)
```

Key log events: PLC connect/disconnect, model load, watchdog trips, PLC write failures, pipeline start/stop

---

## Errors

| Exception          | Raised when |
|--------------------|-------------|
| `PLCConnectionError` | TCP connect, COTP handshake, or S7 negotiation fails |
| `PLCWriteError`    | A tag write is rejected by the PLC or the socket is closed |
| `PLCReadError`     | A tag read is rejected by the PLC or the socket is closed |
| `RuntimeError`     | `step()` is called after the watchdog has tripped in `"stop"` mode |