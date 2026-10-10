import time
import unittest
import numpy as np
from unittest.mock import MagicMock

from backend.translation.contracts import TranslationRequest, TranslationOutcome
from backend.vision.live_vision_service import (
    LiveVisionService,
    SessionVisionState,
    SlideSnapshot,
    OCRJob
)


class TestReviewPlanIntegratedGreen(unittest.TestCase):
    """
    Comprehensive verification for fixes F1 through F7 from:
    docs/REVIEW_UPGRADE_AND_FIX_PLAN_2026-10-10.md
    """

    def setUp(self):
        LiveVisionService._instance = None
        self.service = LiveVisionService(ocr_engine=MagicMock())

    def tearDown(self):
        self.service.stop()

    # --------------------------------------------------------------------------
    # F1 & F2: Envelope with UUID session_id and aligned clock selects context
    # --------------------------------------------------------------------------
    def test_f1_and_f2_session_envelope_and_aligned_clock(self):
        """
        Envelope transmits session_id UUID and aligned capture clock (ms since capture start).
        select_visual_context successfully matches the slide without future_frame_rejected.
        """
        session_id = "sess_user_uuid_9999"
        session = self.service.get_session(session_id, source_epoch=1)

        # Simulate frame captured at 2500ms into audio capture
        frame_dummy = np.ones((100, 100, 3), dtype=np.uint8) * 128
        snap = SlideSnapshot(
            session_id=session_id,
            source_epoch=1,
            frame_id="f_aligned_1",
            slide_id=1,
            slide_revision=1,
            status="READY",
            title="Blackwell AI Superchip",
            entities=[{"text": "Blackwell", "score": 0.95}],
            content_hash="h_blackwell",
            captured_client_ms=2500.0,  # 2.5s into capture
            available_server_ms=time.time() * 1000,
            scene_generation=1
        )
        with session.lock:
            session.current_snapshot = snap
            session.history.append(snap)
            session.slides_registry[(1, 1)] = snap.to_dict()
            session.slides_registry[1] = snap.to_dict()
            session.last_frame_received_time = time.time()

        # Audio segment from 2.0s to 3.0s (end_ms = 3000)
        # Because 2500 <= 3000, frame is valid and not rejected as future
        ctx = self.service.select_visual_context(
            session_id=session_id,
            source_epoch=1,
            segment_end_ms=3000.0,
            speech_text="Here is the Blackwell chip."
        )
        self.assertTrue(ctx["used"], "Context must be used when clocks align and session_id is provided")
        self.assertEqual(ctx["slide_title"], "Blackwell AI Superchip")
        self.assertIn("Blackwell", ctx["relevant_entities"])

    # --------------------------------------------------------------------------
    # F3: Strict monotonic epoch (discard older epoch packet)
    # --------------------------------------------------------------------------
    def test_f3_monotonic_epoch_and_heartbeat_protection(self):
        """Outdated epoch packets cannot downgrade epoch or update heartbeat timestamp."""
        session_id = "sess_f3_test"
        session = self.service.get_session(session_id, source_epoch=5)
        self.assertEqual(session.source_epoch, 5)

        old_heartbeat = session.last_frame_received_time - 10.0
        session.last_frame_received_time = old_heartbeat

        # Ingest packet with older epoch 4
        frame_dummy = np.ones((100, 100, 3), dtype=np.uint8) * 128
        action, payload = session.ingest_frame(
            frame=frame_dummy,
            frame_id="f_late",
            captured_client_ms=500.0,
            source_epoch=4
        )
        self.assertEqual(action, "UNCHANGED")
        self.assertIsNone(payload)
        self.assertEqual(session.source_epoch, 5, "Epoch must remain at 5")
        self.assertEqual(session.last_frame_received_time, old_heartbeat, "Heartbeat must not be refreshed by outdated packet")

        # Ingest packet with newer epoch 6
        action, payload = session.ingest_frame(
            frame=frame_dummy,
            frame_id="f_new_epoch",
            captured_client_ms=600.0,
            source_epoch=6
        )
        self.assertEqual(session.source_epoch, 6, "Newer epoch must advance session epoch")
        self.assertGreater(session.last_frame_received_time, old_heartbeat, "Newer epoch refreshes heartbeat")

    # --------------------------------------------------------------------------
    # F4: Scene generation token invalidates stale OCR over EMPTY scene
    # --------------------------------------------------------------------------
    def test_f4_scene_generation_drops_stale_ocr_and_respects_empty_boundary(self):
        """Worker drops OCR jobs whose scene_generation doesn't match session current scene."""
        session_id = "sess_f4_test"
        session = self.service.get_session(session_id, source_epoch=1)
        initial_gen = session.scene_generation

        # Job created under initial generation
        frame_dummy = np.ones((100, 100, 3), dtype=np.uint8) * 128
        job = OCRJob(
            session_id=session_id,
            source_epoch=1,
            frame_id="f_scene1",
            frame=frame_dummy,
            captured_client_ms=1000.0,
            scene_generation=initial_gen
        )

        # Screen transitions to EMPTY (blank frame)
        blank_frame = np.zeros((100, 100, 3), dtype=np.uint8)
        action, payload = session.ingest_frame(
            frame=blank_frame,
            frame_id="f_blank",
            captured_client_ms=2000.0,
            source_epoch=1
        )
        self.assertEqual(action, "EMPTY")
        self.assertEqual(session.state, "EMPTY")
        self.assertGreater(session.scene_generation, initial_gen, "Scene generation must increase on EMPTY")

        # Now worker finishes job
        self.service._execute_ocr_job(job)
        self.assertEqual(session.state, "EMPTY", "Session state must remain EMPTY, stale OCR must be dropped")

        # And select_visual_context at 2500ms must not resurrect scene 1 from before the EMPTY boundary
        ctx = self.service.select_visual_context(
            session_id=session_id,
            source_epoch=1,
            segment_end_ms=2500.0,
            speech_text="We speak during empty screen."
        )
        self.assertFalse(ctx["used"], "Context must not be used during empty screen")
        self.assertEqual(ctx["reason"], "snapshot_empty")

    # --------------------------------------------------------------------------
    # F5: Recovery from OCR execution error
    # --------------------------------------------------------------------------
    def test_f5_ocr_error_recovery_resets_last_stable_frame(self):
        """When an OCR error occurs, last_stable_frame is cleared so subsequent frames can re-stabilize."""
        session_id = "sess_f5_test"
        session = self.service.get_session(session_id, source_epoch=1)

        # Mock OCR engine to raise exception
        self.service._ocr_engine = MagicMock(side_effect=RuntimeError("Simulated OCR failure"))

        # Frame with texture/variance
        rng = np.random.RandomState(42)
        frame_dummy = rng.randint(50, 200, (100, 100, 3), dtype=np.uint8)
        job = OCRJob(
            session_id=session_id,
            source_epoch=1,
            frame_id="f_err",
            frame=frame_dummy,
            captured_client_ms=1000.0,
            scene_generation=session.scene_generation
        )
        session.last_stable_frame = frame_dummy
        session.state = "OCR_PENDING"

        # Execute failing job
        self.service._execute_ocr_job(job)
        self.assertEqual(session.state, "ERROR")
        self.assertIsNone(session.last_stable_frame, "last_stable_frame must be None after error to allow recovery")

        # Subsequent stabilized frame can now trigger a new OCR attempt instead of being ignored as UNCHANGED
        action, _ = session.ingest_frame(
            frame=frame_dummy,
            frame_id="f_recovery",
            captured_client_ms=2000.0,
            source_epoch=1,
            stabilization_delay_sec=0.0
        )
        self.assertEqual(action, "DISPATCH_OCR", "Frame after error can dispatch OCR for recovery")

    # --------------------------------------------------------------------------
    # F6: Per-epoch registry isolation and immutable override snapshot
    # --------------------------------------------------------------------------
    def test_f6_registry_epoch_isolation_and_immutable_override(self):
        """User override creates a new revision without mutating previous history snapshots."""
        session_id = "sess_f6_test"
        session = self.service.get_session(session_id, source_epoch=1)

        # Add initial slide in epoch 1
        snap1 = SlideSnapshot(
            session_id=session_id,
            source_epoch=1,
            frame_id="f_snap1",
            slide_id=1,
            slide_revision=1,
            status="READY",
            title="Original Title",
            entities=[{"text": "EntityA", "score": 0.9}],
            content_hash="h1",
            captured_client_ms=1000.0,
            available_server_ms=time.time() * 1000,
            scene_generation=1
        )
        session.current_snapshot = snap1
        session.history.append(snap1)
        session.slides_registry[(1, 1)] = snap1.to_dict()

        # User overrides slide 1
        session.override_context(title="Edited Title", entities=["EntityA", "EntityB"], slide_id=1)

        # Snapshot in history at index 0 must NOT have been mutated in-place
        self.assertEqual(session.history[0].title, "Original Title", "History snapshot 0 must be immutable")
        # Current snapshot must have incremented revision and the new title
        self.assertEqual(session.current_snapshot.title, "Edited Title")
        self.assertEqual(session.current_snapshot.slide_revision, 2)
        self.assertEqual(session.current_snapshot.captured_client_ms, 1000.0, "Original capture timestamp preserved")

        # When epoch advances to 2, reset_session clears active working registry
        next_epoch = self.service.reset_session(session_id, new_epoch=2)
        self.assertEqual(next_epoch, 2)
        self.assertEqual(len(session.slides_registry), 0, "Working registry cleared on session reset")

    # --------------------------------------------------------------------------
    # F7: Translation Request & Outcome Envelope Contracts
    # --------------------------------------------------------------------------
    def test_f7_translation_contract_envelope_roundtrip(self):
        """TranslationRequest and TranslationOutcome support source_revision and operation metadata."""
        req = TranslationRequest(
            request_id="sess_1:1:1:translate_local",
            speech_text="Testing envelope.",
            session_id="sess_1",
            segment_id=1,
            source_epoch=2,
            source_revision=1,
            segment_audio_start_ms=100.0,
            segment_audio_end_ms=500.0
        )
        self.assertEqual(req.source_revision, 1)
        self.assertEqual(req.source_epoch, 2)

        outcome = TranslationOutcome(
            status="ok",
            provider="local",
            translated_text="Kiểm tra phong bì.",
            request_id=req.request_id,
            session_id=req.session_id,
            segment_id=req.segment_id,
            source_epoch=req.source_epoch,
            source_revision=req.source_revision,
            operation="translate_local"
        )
        d = outcome.to_dict()
        self.assertEqual(d["source_epoch"], 2)
        self.assertEqual(d["source_revision"], 1)
        self.assertEqual(d["operation"], "translate_local")


if __name__ == "__main__":
    unittest.main()
