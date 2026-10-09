import unittest
import asyncio
from backend.translation.contracts import ASRSegment, VisualEntity
from backend.translation.factory import get_translator
from backend.controller.state import VisualMemoryCache
from backend.controller.policy import AdaptiveController

class TestE2EPipeline(unittest.IsolatedAsyncioTestCase):
    async def test_keynote_stream_simulation(self):
        # 1. Setup Visual Memory Cache with Slide 120s data from EXP-004
        vcache = VisualMemoryCache()
        vcache.update_slide(
            slide_id=1,
            title="NVIDIA and Microsoft Reinvent PC",
            entities=[
                VisualEntity(text="OPENSHELL", score=0.985),
                VisualEntity(text="DeepSeek", score=0.992),
                VisualEntity(text="Qwen", score=0.994),
                VisualEntity(text="WINDOWS", score=0.985)
            ]
        )

        controller = AdaptiveController(visual_cache=vcache)
        translator = get_translator("mock")

        segments = [
            ASRSegment(
                segment_id=1,
                start_time=3.98,
                end_time=13.26,
                text="My relationship with you started here and many of you many of you many of my friends and partners here in Taiwan"
            ),
            ASRSegment(
                segment_id=2,
                start_time=13.72,
                end_time=15.72,
                text="Your companies started here"
            ),
            ASRSegment(
                segment_id=3,
                start_time=17.48,
                end_time=23.68,
                text="This is in a lot of ways the beginning of the modern computer industry 40 years now"
            ),
            ASRSegment(
                segment_id=4,
                start_time=24.60,
                end_time=26.60,
                text="And it is 33 years old"
            ),
            ASRSegment(
                segment_id=6,
                start_time=120.0,
                end_time=132.0,
                text="Microsoft NVIDIA over the last three years, it took this long to completely reinvent how the PC is going to work and connect with OpenShell"
            )
        ]

        responses = []
        revised_records = []

        for seg in segments:
            # Controller step
            req, meta = controller.process_segment(seg)
            self.assertLess(meta["controller_latency_ms"], 10.0)

            # Translation step
            resp = await translator.translate(req)
            responses.append((resp, meta))

            # Record in controller
            controller.record_completed_translation(
                segment_id=seg.segment_id,
                original_text=req.speech_text,
                translated_text=resp.translated_text
            )

            if meta["is_revision"]:
                revised_records.append((seg.segment_id, meta["revised_segment_id"]))

        # Verify assertions
        # 1. Sentence 1 disfluency cleaned
        self.assertEqual(responses[0][0].original_text, "My relationship with you started here and many of you many of my friends and partners here in Taiwan")

        # 2. Sentence 4 triggered revision of Sentence 3
        self.assertEqual(len(revised_records), 1)
        self.assertEqual(revised_records[0], (4, 3))

        # 3. Sentence 6 correctly ground with OPENSHELL
        resp6, meta6 = responses[4]
        self.assertTrue(meta6["visual_grounded"])
        self.assertIn("OPENSHELL", meta6["matched_entities"])
        self.assertIn("OPENSHELL", resp6.translated_text)

if __name__ == "__main__":
    unittest.main()
