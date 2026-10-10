import unittest
import time
import numpy as np
from backend.vision.live_vision_service import (
    LiveVisionService,
    SessionVisionState,
    SlideSnapshot,
    OCRJob
)


class TestReviewPlanPhase0Red(unittest.TestCase):
    """
    Tái hiện chính xác các lỗi ưu tiên cao F1, F2, F3, F4 được nêu trong:
    docs/REVIEW_UPGRADE_AND_FIX_PLAN_2026-10-10.md
    """

    def setUp(self):
        LiveVisionService._instance = None
        self.service = LiveVisionService.get_instance()

    # --------------------------------------------------------------------------
    # F1 — Yêu cầu dịch thiếu định danh phiên OCR (session_id missing / empty)
    # --------------------------------------------------------------------------
    def test_f1_translation_missing_session_id_fails_to_find_context(self):
        """Khi request dịch gửi session_id rỗng ("") thì không tìm thấy context của phiên thực."""
        real_session_id = "sess_user_uuid_12345"
        session = self.service.get_session(real_session_id, source_epoch=0)
        
        # Tạo snapshot hợp lệ cho phiên thực
        snap = SlideSnapshot(
            session_id=real_session_id,
            source_epoch=0,
            frame_id="f_1",
            slide_id=1,
            slide_revision=1,
            status="READY",
            title="Blackwell AI Architecture",
            entities=[{"text": "Blackwell", "score": 0.95}],
            content_hash="hash1",
            captured_client_ms=1000.0,
            available_server_ms=time.time() * 1000
        )
        with session.lock:
            session.current_snapshot = snap
            session.history.append(snap)
            session.last_frame_received_time = time.time()

        # Giả lập payload frontend gửi thiếu session_id (mặc định server là "")
        missing_session_id = ""
        ctx_missing = self.service.select_visual_context(
            session_id=missing_session_id,
            source_epoch=0,
            speech_text="We introduce Blackwell."
        )
        self.assertFalse(ctx_missing["used"], "Thiếu session_id thì không được phép tìm thấy context")
        self.assertEqual(ctx_missing["reason"], "session_not_found")

        # Khi frontend gửi đúng session_id UUID của phiên
        ctx_correct = self.service.select_visual_context(
            session_id=real_session_id,
            source_epoch=0,
            speech_text="We introduce Blackwell."
        )
        self.assertTrue(ctx_correct["used"], "Khi có đúng session_id thì phải tìm thấy context")
        self.assertEqual(ctx_correct["slide_title"], "Blackwell AI Architecture")

    # --------------------------------------------------------------------------
    # F2 — So sánh timestamp khác gốc (Clock Mismatch: performance.now vs audio startSec)
    # --------------------------------------------------------------------------
    def test_f2_clock_mismatch_future_frame_rejection(self):
        """
        Nếu frame dùng performance.now() tính từ khi mở tab (ví dụ 65,000ms)
        nhưng audio segment tính từ lúc bắt đầu capture (ví dụ 5,000ms),
        selector so sánh trực tiếp và coi frame là từ tương lai (future_frame_rejected).
        """
        session_id = "sess_f2_clock"
        session = self.service.get_session(session_id, source_epoch=0)
        
        # Giả lập người dùng mở trang 60s trước (60000ms), frame thu tại giây thứ 5 của capture (65000ms)
        page_load_clock_ms = 65000.0
        audio_segment_end_ms = 5000.0  # Giây thứ 5 của audio

        # Trường hợp 1 (Lỗi hiện tại): Snapshot dùng thẳng performance.now() không trừ gốc
        snap_mismatched = SlideSnapshot(
            session_id=session_id,
            source_epoch=0,
            frame_id="f_raw_clock",
            slide_id=1,
            slide_revision=1,
            status="READY",
            title="Slide Clock Test",
            entities=[{"text": "ClockEntity", "score": 0.95}],
            content_hash="hclock",
            captured_client_ms=page_load_clock_ms, # 65000ms
            available_server_ms=time.time() * 1000
        )
        with session.lock:
            session.current_snapshot = snap_mismatched
            session.last_frame_received_time = time.time()

        ctx_mismatched = self.service.select_visual_context(
            session_id=session_id,
            source_epoch=0,
            segment_end_ms=audio_segment_end_ms, # 5000ms
            speech_text="Testing clock."
        )
        self.assertFalse(ctx_mismatched["used"])
        self.assertEqual(ctx_mismatched["reason"], "future_frame_rejected", "65000 > 5000 bị coi là tương lai")

        # Trường hợp 2 (Đã sửa): Timestamp frame được đồng bộ cùng trục capture audio (5000ms)
        snap_aligned = SlideSnapshot(
            session_id=session_id,
            source_epoch=0,
            frame_id="f_aligned_clock",
            slide_id=1,
            slide_revision=1,
            status="READY",
            title="Slide Clock Test",
            entities=[{"text": "ClockEntity", "score": 0.95}],
            content_hash="hclock",
            captured_client_ms=5000.0, # Đã chuẩn hóa theo audio capture start
            available_server_ms=time.time() * 1000
        )
        with session.lock:
            session.current_snapshot = snap_aligned
            session.last_frame_received_time = time.time()

        ctx_aligned = self.service.select_visual_context(
            session_id=session_id,
            source_epoch=0,
            segment_end_ms=audio_segment_end_ms, # 5000ms
            speech_text="Testing clock."
        )
        self.assertTrue(ctx_aligned["used"], "Khi cùng hệ quy chiếu audio ms thì frame được chấp nhận")

    # --------------------------------------------------------------------------
    # F3 — Phiên và epoch chưa cách ly đầy đủ (Epoch Rewind)
    # --------------------------------------------------------------------------
    def test_f3_outdated_epoch_packet_must_not_rewind_session_epoch(self):
        """Packet frame đến trễ với epoch cũ (ví dụ 2) không được phép làm lùi epoch hiện tại (ví dụ 3)."""
        session_id = "sess_f3_epoch"
        session = self.service.get_session(session_id, source_epoch=3)
        self.assertEqual(session.source_epoch, 3)

        # Gửi frame có source_epoch=2 (gói tin trễ từ epoch cũ)
        frame_dummy = np.ones((100, 100, 3), dtype=np.uint8) * 128
        action, payload = session.ingest_frame(
            frame=frame_dummy,
            frame_id="f_old_epoch",
            captured_client_ms=100.0,
            source_epoch=2
        )

        # Trạng thái session phải được bảo vệ, source_epoch không được tụt về 2
        self.assertGreaterEqual(
            session.source_epoch, 3,
            f"Epoch bị lùi từ 3 xuống {session.source_epoch}!"
        )

    # --------------------------------------------------------------------------
    # F4 — OCR về muộn khôi phục slide đã hết hiệu lực (Outdated OCR over EMPTY)
    # --------------------------------------------------------------------------
    def test_f4_outdated_ocr_must_not_overwrite_empty_scene(self):
        """
        Khi OCR job của Slide A đang chạy, nếu màn hình trở thành EMPTY (chuyển cảnh),
        khi OCR job của Slide A hoàn tất, nó KHÔNG ĐƯỢC phép đè lên trạng thái EMPTY!
        """
        session_id = "sess_f4_generation"
        session = self.service.get_session(session_id, source_epoch=1)
        
        # Giả lập cảnh 1: Slide A được dispatch OCR
        frame_slide_a = np.ones((100, 100, 3), dtype=np.uint8) * 100
        job_slide_a = OCRJob(
            session_id=session_id,
            source_epoch=1,
            frame_id="f_slide_a",
            frame=frame_slide_a,
            captured_client_ms=1000.0,
            scene_generation=getattr(session, "scene_generation", 1)
        )

        # Trong lúc OCR đang chạy, màn hình chuyển sang cảnh rỗng (EMPTY)
        # Giả lập phát hiện khung hình rỗng làm tăng generation
        with session.lock:
            session.state = "EMPTY"
            if hasattr(session, "scene_generation"):
                session.scene_generation += 1

        # Bây giờ giả lập worker hoàn thành job_slide_a
        self.service._execute_ocr_job(job_slide_a)
        # Kiểm tra xem _execute_ocr_job có bảo vệ không ghi đè trạng thái EMPTY không
        self.assertEqual(session.state, "EMPTY", "Job OCR cũ không được đè lên trạng thái EMPTY mới hơn!")


if __name__ == "__main__":
    unittest.main()
