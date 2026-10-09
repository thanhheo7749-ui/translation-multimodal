import time
import numpy as np
from typing import Optional, Dict, Any, List
from rapidocr_onnxruntime import RapidOCR

from backend.translation.contracts import VisualEntity
from backend.controller.state import VisualMemoryCache
from backend.vision.scene_detector import SlideTransitionDetector

class SlideVisionPipeline:
    """
    Automated Vision Pipeline that:
    1. Runs low-latency (<2ms) slide transition detection on incoming video frames.
    2. Selectively invokes RapidOCR only when a slide change is confirmed.
    3. Populates the VisualMemoryCache in RAM for instant 0ms retrieval by the Adaptive Controller.
    """
    def __init__(
        self,
        visual_cache: Optional[VisualMemoryCache] = None,
        ocr_engine: Optional[RapidOCR] = None,
        detector: Optional[SlideTransitionDetector] = None
    ):
        self.visual_cache = visual_cache or VisualMemoryCache()
        self.detector = detector or SlideTransitionDetector()
        self.ocr_engine = ocr_engine or RapidOCR()

    def process_frame(self, frame: np.ndarray, timestamp_sec: float = 0.0) -> Optional[Dict[str, Any]]:
        """
        Processes a video frame.
        Returns:
            Dict with new slide info if transition detected, or None if frame is skipped.
        """
        is_changed, det_meta = self.detector.check_frame(frame, timestamp_sec=timestamp_sec)

        if not is_changed:
            return None

        # Slide change confirmed: Run RapidOCR
        t_ocr_start = time.perf_counter()
        ocr_result, elapse = self.ocr_engine(frame)
        ocr_latency_ms = (time.perf_counter() - t_ocr_start) * 1000

        entities: List[VisualEntity] = []
        if ocr_result:
            for item in ocr_result:
                box, text, score = item[0], item[1].strip(), float(item[2])
                if score >= 0.6 and len(text) > 1:
                    entities.append(VisualEntity(text=text, score=round(score, 3), box=box))

        # Title heuristic: first item with prominent text or first item
        title = ""
        if entities:
            # Check for known title indicators or top-most entity
            title_candidates = [e.text for e in entities if any(k in e.text.lower() for k in ["reinvent", "nvidia", "overview", "agenda", "keynote"])]
            title = title_candidates[0] if title_candidates else entities[0].text

        slide_id = self.detector.transition_count

        # Update Visual Memory in RAM
        self.visual_cache.update_slide(
            slide_id=slide_id,
            title=title,
            entities=entities
        )

        return {
            "slide_id": slide_id,
            "timestamp_sec": timestamp_sec,
            "title": title,
            "entities_count": len(entities),
            "ocr_latency_ms": round(ocr_latency_ms, 2),
            "detector_meta": det_meta
        }
