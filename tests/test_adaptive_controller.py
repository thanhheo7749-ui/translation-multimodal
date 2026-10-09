import unittest
import time
from backend.translation.contracts import ASRSegment, VisualEntity
from backend.controller.state import VisualMemoryCache, ContextWindowManager
from backend.controller.policy import AdaptiveController

class TestAdaptiveController(unittest.TestCase):
    def setUp(self):
        self.vcache = VisualMemoryCache()
        self.vcache.update_slide(
            slide_id=1,
            title="NVIDIA and Microsoft Reinvent PC",
            entities=[
                VisualEntity(text="OPENSHELL", score=0.98),
                VisualEntity(text="DeepSeek", score=0.99),
                VisualEntity(text="Qwen", score=0.99)
            ]
        )
        self.controller = AdaptiveController(visual_cache=self.vcache)

    def test_disfluency_deduplication(self):
        raw = "many of you many of you many of my friends here"
        cleaned = self.controller.clean_disfluencies(raw)
        self.assertEqual(cleaned, "many of you many of my friends here")

    def test_entity_matching_from_cache(self):
        seg = ASRSegment(
            segment_id=6,
            text="that compute pattern called the agent is going to connect with OpenShell",
            start_time=120.0,
            end_time=125.0
        )
        t0 = time.perf_counter()
        req, meta = self.controller.process_segment(seg)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        self.assertIn("OPENSHELL", req.relevant_entities)
        self.assertEqual(req.action, "TRANSLATE_NOW")
        self.assertTrue(meta["visual_grounded"])
        self.assertLess(elapsed_ms, 5.0, "Controller decision must take < 5ms")

    def test_connector_and_pronoun_revision(self):
        # First feed Sentence 3
        seg3 = ASRSegment(
            segment_id=3,
            text="This is in a lot of ways the beginning of the modern computer industry 40 years now",
            start_time=17.48,
            end_time=23.68
        )
        req3, meta3 = self.controller.process_segment(seg3)
        self.controller.record_completed_translation(
            segment_id=3,
            original_text=seg3.text,
            translated_text="Về nhiều mặt, đây là sự khởi đầu của ngành công nghiệp máy tính hiện đại cách đây 40 năm."
        )

        # Now feed Sentence 4 starting with 'And it is'
        seg4 = ASRSegment(
            segment_id=4,
            text="And it is 33 years old",
            start_time=24.60,
            end_time=26.60
        )
        req4, meta4 = self.controller.process_segment(seg4)

        self.assertEqual(req4.action, "REVISE_PREVIOUS")
        self.assertTrue(meta4["is_revision"])
        self.assertEqual(meta4["revised_segment_id"], 3)
        self.assertIn("beginning of the modern computer industry", req4.previous_context)

if __name__ == "__main__":
    unittest.main()
