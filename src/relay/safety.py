from threading import Thread, Event
import time

class Watchdog:
    def __init__(self, driver, tag: str, interval_ms: int = 50, safe_state: bool = False, recover: bool = False):
        self.driver = driver
        self.tag = tag
        self.interval = interval_ms / 1000
        self.safe_state = safe_state
        self.recover = recover

        self._last_heartbeat = time.time()
        self._healthy = True
        self._stop_event = Event()
        self._thread: Thread | None = None

    def start(self) -> None:
        self._thread = Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join()

    def heartbeat(self) -> None:
        self._last_heartbeat = time.time()
        if self.recover:
            self._healthy = True

    def is_healthy(self) -> bool:
        return self._healthy

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self._stop_event.wait(self.interval)

            elapsed = time.time() - self._last_heartbeat
            if elapsed > self.interval:
                self._healthy = False
                try:
                    self.driver.write_output(self.tag, self.safe_state)
                except Exception as e:
                    print(f"Watchdog write failed: {e}")

                if not self.recover:
                    self._stop_event.set()
                    return