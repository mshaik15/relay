from threading import Thread, Event
import time

class Watchdog:
    def __init__(self, driver, tag, interval_ms=50):
        self.driver = driver
        self.tag = tag
        self.interval = interval_ms / 1000
        self._last_heartbeat = time.time()
        self._healthy = True
        self._stop_event = Event()

    
    def start(self) -> None:
        self._thread = Thread(target=self._run)
        self._thread.daemon = True
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._thread.join()

    def heartbeat(self) -> None:
            self._last_heartbeat = time.time()
    
    def is_healthy(self) -> bool:
        return self._healthy
        
    
    def _run(self):
        while not self._stop_event.is_set():
             self._stop_event.wait(self.interval)

             elapsed = time.time() - self._last_heartbeat
             if elapsed > self.interval:
                    self._healthy = False
                    try:
                        self.driver.write_output(self.tag, False)
                    except Exception as e:
                         print(f"Watchdog failed {e}")