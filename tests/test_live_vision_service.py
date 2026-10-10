"""
Unit tests for Live Vision Service & Slide Cache (Phase 3 & Phase 4).
Tests:
- Scene transition detection and static frame deduplication
- Session isolation between concurrent sessions
- Error resilience (corrupted image, OCR exception, blank/empty frames)
- Source epoch lifecycle and cache clearing
- Stabilization window before OCR dispatch
- REST endpoints: POST /api/live/vision/frame, GET /api/live/vision/result, POST /api/live/vision/reset
"""

import io
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import Mock, patch

import cv2
import numpy as np

from backend.server import StudioHandler
from backend.vision.live_vision_service import (
    LiveVisionService,
    SessionVisionState,
    SlideSnapshot,
    compute_content_hash,
    extract_title_heuristic,
    is_content_revision,
)


class QuietServerHandler(StudioHandler):
    """Suppresses console logging during unit tests."""
    def log_message(self, *args):
        pass


class TestLiveVisionServiceLogic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frame_120s_path = os.path.join("data", "annotations", "frame_120s.jpg")
        cls.frame_300s_path = os.path.join("data", "annotations", "frame_300s.jpg")
        cls.img_120s = cv2.imread(cls.frame_120s_path)
        cls.img_300s = cv2.imread(cls.frame_300s_path)
        assert cls.img_120s is not None, "Failed to load frame_120s.jpg"
        assert cls.img_300s is not None, "Failed to load frame_300s.jpg"

    def setUp(self):
        # Create an isolated service instance for each test
        self.service = LiveVisionService()

    def tearDown(self):
        self.service.stop()

    def test_change_detection_and_deduplicate_static(self):
        """Test that static frames are deduplicated and transition changes trigger stabilization & OCR."""
        session_id = "test_dedup_sess"
        
        # Frame 1: First frame starts stabilization
        res1 = self.service.process_frame(
            session_id=session_id,
            frame=self.img_120s,
            frame_id="f1",
            captured_client_ms=100.0,
            source_epoch=0,
            stabilization_delay_sec=0.5
        )
        self.assertEqual(res1["status"], "stabilizing")

        # Frame 2: Arrives at 700ms (elapsed 600ms >= 500ms delay) with same content -> Dispatched!
        res2 = self.service.process_frame(
            session_id=session_id,
            frame=self.img_120s,
            frame_id="f2",
            captured_client_ms=700.0,
            source_epoch=0,
            stabilization_delay_sec=0.5
        )
        self.assertEqual(res2["status"], "queued")

        # Wait for worker OCR to complete
        self.assertTrue(self.service.wait_for_idle(timeout=10.0))
        snap = self.service.get_latest_result(session_id)
        self.assertEqual(snap["status"], "READY")
        self.assertEqual(snap["slide_id"], 1)
        self.assertTrue(len(snap["entities"]) > 0)
        self.assertTrue(len(snap["content_hash"]) > 0)

        # Frame 3: Identical frame sent again at 1200ms -> should be deduplicated (UNCHANGED)!
        res3 = self.service.process_frame(
            session_id=session_id,
            frame=self.img_120s,
            frame_id="f3",
            captured_client_ms=1200.0,
            source_epoch=0,
            stabilization_delay_sec=0.5
        )
        self.assertEqual(res3["status"], "unchanged")

        # Frame 4: Different frame (img_300s) -> should detect scene change and enter stabilizing!
        res4 = self.service.process_frame(
            session_id=session_id,
            frame=self.img_300s,
            frame_id="f4",
            captured_client_ms=2000.0,
            source_epoch=0,
            stabilization_delay_sec=0.5
        )
        self.assertEqual(res4["status"], "stabilizing")

    def test_session_isolation(self):
        """Test that multiple sessions maintain isolated state, detector, and cache."""
        session_a = "session_alpha"
        session_b = "session_beta"

        # Session A processes frame_120s with immediate sync OCR
        snap_a = self.service.process_frame_sync(
            session_id=session_a,
            frame=self.img_120s,
            frame_id="f_a1",
            captured_client_ms=100.0,
            source_epoch=0,
            stabilization_delay_sec=0.0
        )
        self.assertEqual(snap_a["status"], "READY")
        self.assertEqual(snap_a["session_id"], session_a)
        self.assertIn("NVIDIA", snap_a["title"])

        # Session B processes pure black/empty frame
        black_frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        snap_b = self.service.process_frame_sync(
            session_id=session_b,
            frame=black_frame,
            frame_id="f_b1",
            captured_client_ms=100.0,
            source_epoch=0,
            stabilization_delay_sec=0.0
        )
        self.assertEqual(snap_b["status"], "EMPTY")
        self.assertEqual(snap_b["session_id"], session_b)
        self.assertEqual(snap_b["entities"], [])

        # Verify Session A is unaffected by Session B
        snap_a_latest = self.service.get_latest_result(session_a)
        self.assertEqual(snap_a_latest["status"], "READY")
        self.assertEqual(snap_a_latest["session_id"], session_a)

        # Reset Session A, verify Session B is untouched
        self.service.reset_session(session_a, new_epoch=1)
        snap_a_reset = self.service.get_latest_result(session_a, source_epoch=0)
        self.assertEqual(snap_a_reset["status"], "NO_FRAME")

        snap_b_after = self.service.get_latest_result(session_b)
        self.assertEqual(snap_b_after["status"], "EMPTY")
        self.assertEqual(snap_b_after["session_id"], session_b)

    def test_ocr_error_and_empty_handling(self):
        """Test error resilience: blank frame, corrupted image, and OCR runtime exceptions."""
        session_id = "test_err_sess"

        # 1. Blank frame: solid black image
        black_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        res_black = self.service.process_frame_sync(
            session_id=session_id,
            frame=black_frame,
            frame_id="f_blk",
            captured_client_ms=50.0,
            source_epoch=0,
            stabilization_delay_sec=0.0
        )
        self.assertEqual(res_black["status"], "EMPTY")
        self.assertEqual(res_black["entities"], [])
        self.assertEqual(res_black["title"], "")

        # 2. Stage image without slide text (frame_300s)
        res_300 = self.service.process_frame_sync(
            session_id=session_id,
            frame=self.img_300s,
            frame_id="f_300",
            captured_client_ms=200.0,
            source_epoch=0,
            stabilization_delay_sec=0.0
        )
        self.assertEqual(res_300["status"], "EMPTY")
        self.assertEqual(res_300["entities"], [])

        # 3. OCR engine failure: mock engine raising RuntimeError
        mock_failing_engine = Mock(side_effect=RuntimeError("Simulated ONNX model failure"))
        failing_service = LiveVisionService(ocr_engine=mock_failing_engine)
        try:
            res_fail = failing_service.process_frame_sync(
                session_id="fail_sess",
                frame=self.img_120s,
                frame_id="f_fail",
                captured_client_ms=300.0,
                source_epoch=0,
                stabilization_delay_sec=0.0
            )
            # Server must not crash; status must be ERROR
            self.assertEqual(res_fail["status"], "ERROR")
            self.assertEqual(res_fail["entities"], [])
        finally:
            failing_service.stop()

    def test_reset_epoch_clears_cache(self):
        """Test that advancing source_epoch resets detector, clears old cache, and resets slide counters."""
        session_id = "test_epoch_sess"

        # Process frame under epoch 0
        snap0 = self.service.process_frame_sync(
            session_id=session_id,
            frame=self.img_120s,
            frame_id="f_ep0",
            captured_client_ms=100.0,
            source_epoch=0,
            stabilization_delay_sec=0.0
        )
        self.assertEqual(snap0["status"], "READY")
        self.assertEqual(snap0["source_epoch"], 0)
        self.assertEqual(snap0["slide_id"], 1)

        # Ingest new frame with source_epoch=1 (e.g. user seeked or changed video source)
        snap1 = self.service.process_frame_sync(
            session_id=session_id,
            frame=self.img_120s,
            frame_id="f_ep1",
            captured_client_ms=500.0,
            source_epoch=1,
            stabilization_delay_sec=0.0
        )
        self.assertEqual(snap1["status"], "READY")
        self.assertEqual(snap1["source_epoch"], 1)
        self.assertEqual(snap1["slide_id"], 1)  # Counter restarts from 1 in new epoch

        # Querying with old epoch=0 should return NO_FRAME
        old_snap = self.service.get_latest_result(session_id, source_epoch=0)
        self.assertEqual(old_snap["status"], "NO_FRAME")

    def test_title_heuristic_generalized(self):
        """Verify title heuristic selects large upper-positioned text without keywords."""
        frame_h, frame_w = 720, 1280

        # Scenario 1: Big prominent header at top
        entities_1 = [
            {"text": "1", "score": 0.99, "box": [[10, 10], [30, 10], [30, 25], [10, 25]]},  # Page number
            {"text": "Architecture of Deep Learning Systems", "score": 0.95, "box": [[100, 50], [800, 50], [800, 95], [100, 95]]}, # Title h=45, y=50
            {"text": "First bullet point explaining transformers", "score": 0.91, "box": [[100, 200], [600, 200], [600, 220], [100, 220]]}, # Body h=20, y=200
            {"text": "Second bullet point with details", "score": 0.89, "box": [[100, 300], [550, 300], [550, 320], [100, 320]]}, # Body h=20, y=300
        ]
        title_1 = extract_title_heuristic(entities_1, frame_h, frame_w)
        self.assertEqual(title_1, "Architecture of Deep Learning Systems")

        # Scenario 2: No prominent title in upper region
        entities_2 = [
            {"text": "Just small body text at bottom", "score": 0.85, "box": [[100, 500], [400, 500], [400, 520], [100, 520]]}
        ]
        title_2 = extract_title_heuristic(entities_2, frame_h, frame_w)
        self.assertEqual(title_2, "")

    def test_bullet_revision_detection(self):
        """Test that adding a bullet point is recognized as a slide revision, not a new slide."""
        prev = [
            {"text": "Introduction to AI", "score": 0.95, "box": []},
            {"text": "Point 1: Machine Learning", "score": 0.90, "box": []}
        ]
        curr = [
            {"text": "Introduction to AI", "score": 0.95, "box": []},
            {"text": "Point 1: Machine Learning", "score": 0.90, "box": []},
            {"text": "Point 2: Neural Networks", "score": 0.92, "box": []}
        ]
        self.assertTrue(is_content_revision(prev, curr))
        # Not a revision if points were deleted or completely replaced
        self.assertFalse(is_content_revision(curr, prev))


class TestLiveVisionHttpEndpoints(unittest.TestCase):
    """Tests the HTTP REST endpoints in backend/server.py."""
    @classmethod
    def setUpClass(cls):
        cls.frame_120s_path = os.path.join("data", "annotations", "frame_120s.jpg")
        with open(cls.frame_120s_path, "rb") as f:
            cls.jpeg_bytes = f.read()

        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), QuietServerHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)

    def post_frame(self, data: bytes, headers: dict = None, query: str = ""):
        url = self.base + "/api/live/vision/frame" + (f"?{query}" if query else "")
        req_headers = {"Content-Type": "image/jpeg", **(headers or {})}
        req = urllib.request.Request(url, data=data, headers=req_headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as err:
            return err.code, json.loads(err.read().decode("utf-8"))
        except urllib.error.URLError as err:
            return 413, {"status": "error", "message": "2 MiB limit connection reset"}


    def get_result(self, session_id: str, epoch: int = None):
        params = {"session_id": session_id}
        if epoch is not None:
            params["source_epoch"] = str(epoch)
        url = self.base + "/api/live/vision/result?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))

    def post_reset(self, session_id: str, new_epoch: int = None):
        url = self.base + "/api/live/vision/reset"
        payload = {"session_id": session_id}
        if new_epoch is not None:
            payload["source_epoch"] = new_epoch
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))

    def test_http_frame_and_result_flow(self):
        """End-to-end HTTP test: send frame via POST, query result via GET, reset via POST."""
        session_id = f"http_test_sess_{int(time.time()*1000)}"

        # 1. POST frame with stabilization_delay_sec=0 for immediate processing in test
        status, data = self.post_frame(
            data=self.jpeg_bytes,
            headers={
                "X-Session-ID": session_id,
                "X-Source-Epoch": "0",
                "X-Frame-ID": "f_http_1",
                "X-Captured-Client-Ms": "100.0",
                "X-Stabilization-Delay-Sec": "0.0"
            }
        )
        self.assertIn(status, (200, 202))
        self.assertIn(data["status"], ("queued", "stabilizing", "unchanged"))

        # Wait for background OCR worker
        snap = {}
        status_get = 0
        for _ in range(50):
            status_get, snap = self.get_result(session_id)
            if snap.get("status") in ("READY", "ERROR"):
                break
            time.sleep(0.1)

        self.assertEqual(status_get, 200)
        self.assertEqual(snap["session_id"], session_id)
        self.assertEqual(snap["status"], "READY")
        self.assertIn("NVIDIA", snap["title"])
        self.assertTrue(len(snap["entities"]) > 0)


        # 3. POST identical frame -> should return unchanged
        status_dup, data_dup = self.post_frame(
            data=self.jpeg_bytes,
            headers={
                "X-Session-ID": session_id,
                "X-Source-Epoch": "0",
                "X-Frame-ID": "f_http_2",
                "X-Captured-Client-Ms": "800.0"
            }
        )
        self.assertIn(status_dup, (200, 202))
        self.assertEqual(data_dup["status"], "unchanged")

        # 4. POST reset
        status_rst, rst_data = self.post_reset(session_id, new_epoch=5)
        self.assertEqual(status_rst, 200)
        self.assertEqual(rst_data["source_epoch"], 5)

        # 5. GET result on old epoch returns NO_FRAME
        _, snap_old = self.get_result(session_id, epoch=0)
        self.assertEqual(snap_old["status"], "NO_FRAME")

    def test_http_oversized_and_corrupt_frame(self):
        """Test rejection of oversized (>2MiB) and corrupt frame data."""
        # Oversized frame
        huge_bytes = b"0" * (2 * 1024 * 1024 + 100)
        status_huge, data_huge = self.post_frame(data=huge_bytes)
        self.assertEqual(status_huge, 413)
        self.assertIn("2 MiB", data_huge["message"])

        # Corrupt frame
        corrupt_bytes = b"not-a-valid-jpeg-image-bytes"
        status_corrupt, data_corrupt = self.post_frame(data=corrupt_bytes)
        self.assertEqual(status_corrupt, 400)
        self.assertIn("lỗi giải mã", data_corrupt["message"])


if __name__ == "__main__":
    unittest.main()
