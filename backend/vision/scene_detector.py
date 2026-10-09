import time
import cv2
import numpy as np
from typing import Tuple, Dict, Any, Optional

class SlideTransitionDetector:
    """
    Lightweight, CPU-efficient slide transition detector (< 2ms per frame).
    Combines low-resolution grayscale histogram correlation with pixel-level mean absolute difference
    to reliably distinguish between slide changes and minor webcam/speaker motion.
    """
    def __init__(
        self,
        correlation_threshold: float = 0.88,
        mean_diff_threshold: float = 28.0,
        downsample_size: Tuple[int, int] = (320, 180),
        min_interval_sec: float = 0.8
    ):
        self.correlation_threshold = correlation_threshold
        self.mean_diff_threshold = mean_diff_threshold
        self.downsample_size = downsample_size
        self.min_interval_sec = min_interval_sec

        self.prev_gray: Optional[np.ndarray] = None
        self.prev_hist: Optional[np.ndarray] = None
        self.last_transition_time: float = -1.0
        self.transition_count: int = 0

    def _preprocess(self, frame: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Downsamples frame and computes normalized 64-bin grayscale histogram."""
        resized = cv2.resize(frame, self.downsample_size, interpolation=cv2.INTER_AREA)
        if len(resized.shape) == 3:
            gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
        else:
            gray = resized

        hist = cv2.calcHist([gray], [0], None, [64], [0, 256])
        cv2.normalize(hist, hist, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)
        return gray, hist

    def check_frame(self, frame: np.ndarray, timestamp_sec: float = 0.0) -> Tuple[bool, Dict[str, Any]]:
        """
        Evaluates an incoming video frame to detect if a slide transition occurred.
        Returns:
            (is_changed, metadata_dict)
        """
        t0 = time.perf_counter()

        gray, hist = self._preprocess(frame)

        if self.prev_hist is None or self.prev_gray is None:
            # First frame initializes the reference keyframe
            self.prev_gray = gray
            self.prev_hist = hist
            self.last_transition_time = timestamp_sec
            self.transition_count += 1
            elapsed_ms = (time.perf_counter() - t0) * 1000
            return True, {
                "correlation": 0.0,
                "mean_diff": 255.0,
                "latency_ms": round(elapsed_ms, 3),
                "transition_count": self.transition_count,
                "reason": "initial_reference"
            }

        # Temporal cooldown check to prevent stutter triggers
        if timestamp_sec > 0 and (timestamp_sec - self.last_transition_time) < self.min_interval_sec:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            return False, {
                "correlation": 1.0,
                "mean_diff": 0.0,
                "latency_ms": round(elapsed_ms, 3),
                "reason": "cooldown_suppressed"
            }

        # Metric 1: Histogram Correlation (1.0 = identical, < 0.85 = significant color/layout shift)
        correlation = float(cv2.compareHist(self.prev_hist, hist, cv2.HISTCMP_CORREL))

        # Metric 2: Mean Absolute Pixel Difference
        mean_diff = float(np.mean(cv2.absdiff(self.prev_gray, gray)))

        is_changed = (correlation < self.correlation_threshold) or (mean_diff > self.mean_diff_threshold)

        if is_changed:
            self.prev_gray = gray
            self.prev_hist = hist
            self.last_transition_time = timestamp_sec
            self.transition_count += 1

        elapsed_ms = (time.perf_counter() - t0) * 1000

        metadata = {
            "correlation": round(correlation, 4),
            "mean_diff": round(mean_diff, 2),
            "latency_ms": round(elapsed_ms, 3),
            "transition_count": self.transition_count,
            "reason": "threshold_exceeded" if is_changed else "no_change"
        }

        return is_changed, metadata

    def reset(self):
        """Resets detector state."""
        self.prev_gray = None
        self.prev_hist = None
        self.last_transition_time = -1.0
        self.transition_count = 0
