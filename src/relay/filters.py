class TemporalFilter:
    def __init__(self, threshold: float, consecutive_frames: int):
        self.threshold = threshold
        self.consecutive_frames = consecutive_frames
        self.count: int = 0
        self.current_label: str | None = None


    def update(self, label: str, confidence: float) -> bool:
        if confidence < self.threshold:
            self.count = 0
            self.current_label = None
            return False
        if label != self.current_label:
            self.count = 1
            self.current_label = label
            return False
        
        self.count += 1
        if self.count >= self.consecutive_frames:
            return True
        
        return False
    
    def reset(self):
        self.count = 0
        self.current_label = None