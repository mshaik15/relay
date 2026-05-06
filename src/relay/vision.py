from dataclasses import dataclass
from ultralytics import YOLO

@dataclass
class Detection:
    label: str
    confidence: float

class VisionModel:
    def __init__(self, model_path: str, confidence_min: float = 0.0):
        self._model_path = model_path
        self.confidence_min = confidence_min
        self._model = None

    def load(self) -> None:
        self._model = YOLO(self._model_path)

    def predict(self, frame):
        if self._model is None:
            raise RuntimeError("YOLO model is not loaded, call loat() before predict()")
        
        detections = []
        results = self._model(frame)

        for result in results:
            for box in result.boxes:
                conf = float(box.conf)
                if conf >= self.confidence_min:
                    label = self._model.names[int(box.cls)]
                    detections.append(Detection(label=label, confidence=conf))
        
        return sorted(detections, key=lambda d: d.confidence, reverse=True)