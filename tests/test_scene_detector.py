import unittest
import os
import cv2
import numpy as np
import time
from backend.controller.state import VisualMemoryCache
from backend.vision.scene_detector import SlideTransitionDetector
from backend.vision.slide_pipeline import SlideVisionPipeline

class TestSceneDetector(unittest.TestCase):
    def setUp(self):
        self.frame_20s_path = os.path.join("data", "annotations", "frame_20s.jpg")
        self.frame_120s_path = os.path.join("data", "annotations", "frame_120s.jpg")
        self.frame_300s_path = os.path.join("data", "annotations", "frame_300s.jpg")
        
        self.img_20s = cv2.imread(self.frame_20s_path)
        self.img_120s = cv2.imread(self.frame_120s_path)
        self.img_300s = cv2.imread(self.frame_300s_path)

        self.assertIsNotNone(self.img_20s, "Failed to load frame_20s.jpg")
        self.assertIsNotNone(self.img_120s, "Failed to load frame_120s.jpg")
        self.assertIsNotNone(self.img_300s, "Failed to load frame_300s.jpg")

    def test_identical_frame_not_changed(self):
        detector = SlideTransitionDetector()
        # First frame initializes reference
        changed_1, meta_1 = detector.check_frame(self.img_20s, timestamp_sec=20.0)
        self.assertTrue(changed_1, "First frame should initialize reference as new slide")

        # Second identical frame
        changed_2, meta_2 = detector.check_frame(self.img_20s, timestamp_sec=21.0)
        self.assertFalse(changed_2, "Identical frame should NOT trigger slide change")
        self.assertGreater(meta_2["correlation"], 0.98)

    def test_minor_noise_not_changed(self):
        detector = SlideTransitionDetector()
        detector.check_frame(self.img_20s, timestamp_sec=20.0)

        # Add slight gaussian noise or minor brightness offset (simulating webcam head/light jitter)
        noisy_frame = np.clip(self.img_20s.astype(np.int16) + np.random.randint(-5, 5, size=self.img_20s.shape), 0, 255).astype(np.uint8)
        changed, meta = detector.check_frame(noisy_frame, timestamp_sec=20.5)
        self.assertFalse(changed, "Minor noise should NOT trigger slide change")

    def test_distinct_slides_trigger_transition(self):
        detector = SlideTransitionDetector()
        detector.check_frame(self.img_20s, timestamp_sec=20.0)

        # Transition to frame_120s
        changed, meta = detector.check_frame(self.img_120s, timestamp_sec=120.0)
        self.assertTrue(changed, "Transition to frame_120s should trigger slide change")
        self.assertLess(meta["correlation"], 0.85)

        # Transition to frame_300s
        changed_300, meta_300 = detector.check_frame(self.img_300s, timestamp_sec=300.0)
        self.assertTrue(changed_300, "Transition to frame_300s should trigger slide change")

    def test_detector_latency_under_5ms(self):
        detector = SlideTransitionDetector()
        detector.check_frame(self.img_20s)

        t0 = time.perf_counter()
        changed, meta = detector.check_frame(self.img_120s)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        self.assertLess(elapsed_ms, 5.0, f"Detector must run in < 5ms, took {elapsed_ms:.2f}ms")
        self.assertLess(meta["latency_ms"], 5.0)

    def test_slide_vision_pipeline_integration(self):
        vcache = VisualMemoryCache()
        pipeline = SlideVisionPipeline(visual_cache=vcache)

        # Frame 20s
        res_20s = pipeline.process_frame(self.img_20s, timestamp_sec=20.0)
        self.assertIsNotNone(res_20s, "Pipeline should process new slide for frame_20s")
        self.assertEqual(vcache.slide_id, 1)

        # Frame 20s again (no slide change)
        res_repeat = pipeline.process_frame(self.img_20s, timestamp_sec=21.0)
        self.assertIsNone(res_repeat, "Pipeline should SKIP OCR on repeated frame")

        # Frame 120s (slide changed!)
        res_120s = pipeline.process_frame(self.img_120s, timestamp_sec=120.0)
        self.assertIsNotNone(res_120s, "Pipeline should process new slide for frame_120s")
        self.assertEqual(vcache.slide_id, 2)
        self.assertGreater(len(vcache.entities), 5)
        # Check that OPENSHELL is now in cache
        matched = vcache.match_entities_in_text("we are connecting to OpenShell")
        self.assertIn("OPENSHELL", matched)

if __name__ == "__main__":
    unittest.main()
