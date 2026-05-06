import logging
import time

from .config import RelayConfig, WatchdogMode
from .filters import TemporalFilter
from .vision import VisionModel
from .safety import Watchdog
from .plc.base import PLCDriver, PLCWriteError

logger = logging.getLogger(__name__)

class RelayPipeline:
    def __init__(self, config: RelayConfig, driver: PLCDriver, model: VisionModel):
        self.config = config
        self.driver = driver
        self.model = model
        
        self._filter = TemporalFilter(
            threshold = config.confidence_threshold,
            consecutive_frames = config.consecutive_frames
        )

        self._watchdog = Watchdog(
            driver = driver,
            tag = config.output_tag,
            safe_state = config.safe_state,
            recover = config.watchdog_mode == WatchdogMode.recover
        )

        self._running = False

    def start(self) -> None:
        """ Connect the PLC, load model and start the watchdog thread """
        logger.info("Connecting to PLC")
        self.driver.connect()

        logger.info("Loading vision model")
        self.model.load()

        self._watchdog.start()
        self._running = True
        logger.info("Pipeline started")

    def stop(self) -> None:
        """ Stop watchdog, write safe state and disconnect from the PLC """
        self._running = False
        self._watchdog.stop()
        try:
            self.driver.write_output(self.config.output_tag, self.config.safe_state)
        
        except PLCWriteError as e:
            logger.warning("Couldnt write safe state on shutdown: %s", e)
        
        self.driver.disconnect()
        logger.info("Pipeline Stopped")

    def step(self, frame) -> bool:
        """ Run one frame through the model and filter, write PLC output if triggered """
        if not self._watchdog.is_healthy():
            raise RuntimeError("Watchdog tripped, pipeline stopped, restart")
        
        detections = self.model.predict(frame)

        if not detections:
            self._filter.update("", 0.0)
            return False

        top = detections[0]
        triggered = self._filter.update(top.label, top.confidence)

        if triggered:
            try:
                self.driver.write_output(self.config.output_tag, True)
                self._watchdog.heartbeat()
                return True
            except PLCWriteError as e:
                logger.error("PLC write failed: %s", e)

        return False
    
    def run(self, frame_source) -> None:
        """
        Block and process frames from frame_source (any iterable yielding frames).
        Stops on KeyboardInterrupt, watchdog halt, or exhausted source.
        """
        self.start()
        try:
            for frame in frame_source:
                if not self._running:
                    break
                try:
                    self.step(frame)
                except RuntimeError as e:
                    logger.error(str(e))
                    break
        except KeyboardInterrupt:
            logger.info("Interrupted.")
        finally:
            self.stop()


