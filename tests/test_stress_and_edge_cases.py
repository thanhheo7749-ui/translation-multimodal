import unittest
import asyncio
import os
from backend.translation.contracts import ASRSegment, TranslationRequest, VisualEntity
from backend.translation.factory import get_translator
from backend.translation.mock_provider import MockTranslator
from backend.translation.gemini_provider import GeminiTranslator
from backend.translation.local_provider import LocalLLMTranslator
from backend.controller.state import VisualMemoryCache, ContextWindowManager
from backend.controller.policy import AdaptiveController

class TestStressAndEdgeCases(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.vcache = VisualMemoryCache()
        self.vcache.update_slide(
            slide_id=1,
            title="NVIDIA and Microsoft Reinvent PC",
            entities=[
                VisualEntity(text="OPENSHELL", score=0.985),
                VisualEntity(text="DeepSeek", score=0.992),
                VisualEntity(text="Qwen", score=0.994),
                VisualEntity(text="WINDOWS", score=0.985)
            ]
        )
        self.controller = AdaptiveController(visual_cache=self.vcache, max_history=3)
        self.translator = get_translator("mock")

    async def test_empty_and_whitespace_speech(self):
        """Edge Case 1: Empty or whitespace input should not crash."""
        for empty_text in ["", "   ", "\n\t", "...."]:
            seg = ASRSegment(segment_id=99, text=empty_text, start_time=0.0, end_time=1.0)
            req, meta = self.controller.process_segment(seg)
            resp = await self.translator.translate(req)
            self.assertIsNotNone(resp.translated_text)
            self.assertFalse(meta["visual_grounded"])

    def test_sliding_window_overflow_cap(self):
        """Edge Case 2: History buffer strictly bounded by max_history."""
        c_mgr = ContextWindowManager(max_history=3)
        for i in range(10):
            c_mgr.add_segment(i, f"English {i}", f"Vietnamese {i}")
        
        self.assertEqual(len(c_mgr.history), 3)
        # Should contain segments 7, 8, 9
        history_ids = [item["segment_id"] for item in c_mgr.history]
        self.assertEqual(history_ids, [7, 8, 9])
        self.assertEqual(c_mgr.get_last_segment()["segment_id"], 9)

    def test_punctuation_and_case_insensitive_entity_matching(self):
        """Edge Case 3: Entities with varying capitalization and surrounding punctuation."""
        variations = [
            "we are using openshell now",
            "check out (OpenShell)!",
            "connecting to 'OPENSHELL', as expected.",
            "deepseek-ai and qwen models are supported."
        ]
        for v in variations:
            seg = ASRSegment(segment_id=10, text=v, start_time=0.0, end_time=2.0)
            req, meta = self.controller.process_segment(seg)
            self.assertTrue(meta["visual_grounded"], f"Failed to match entity in: {v}")
            self.assertGreater(len(req.relevant_entities), 0)

    def test_stopword_immunity(self):
        """Edge Case 4: Sentences with common words must NOT trigger false entity matches."""
        safe_sentences = [
            "This is what we have for you today",
            "We will work with them from here",
            "Can you tell us more about our industry",
            "Into the future over time"
        ]
        for s in safe_sentences:
            seg = ASRSegment(segment_id=20, text=s, start_time=0.0, end_time=2.0)
            req, meta = self.controller.process_segment(seg)
            self.assertEqual(
                meta["matched_entities"], [],
                f"False positive matched entities in safe sentence: '{s}' -> {meta['matched_entities']}"
            )

    async def test_consecutive_chain_revisions(self):
        """Edge Case 5: Multiple dependent sentences in a row."""
        seg1 = ASRSegment(segment_id=1, text="The PC industry started 40 years ago", start_time=0.0, end_time=3.0)
        req1, meta1 = self.controller.process_segment(seg1)
        resp1 = await self.translator.translate(req1)
        self.controller.record_completed_translation(1, req1.speech_text, resp1.translated_text)
        self.assertFalse(meta1["is_revision"])

        # Second sentence starting with "And it is"
        seg2 = ASRSegment(segment_id=2, text="And it is evolving rapidly", start_time=3.5, end_time=5.0)
        req2, meta2 = self.controller.process_segment(seg2)
        resp2 = await self.translator.translate(req2)
        self.controller.record_completed_translation(2, req2.speech_text, resp2.translated_text)
        self.assertTrue(meta2["is_revision"])
        self.assertEqual(meta2["revised_segment_id"], 1)

        # Third sentence starting with "Because they are"
        seg3 = ASRSegment(segment_id=3, text="Because they are adopting AI chips", start_time=5.5, end_time=7.0)
        req3, meta3 = self.controller.process_segment(seg3)
        resp3 = await self.translator.translate(req3)
        self.controller.record_completed_translation(3, req3.speech_text, resp3.translated_text)
        self.assertTrue(meta3["is_revision"])
        self.assertEqual(meta2["revised_segment_id"], 1)
        self.assertEqual(meta3["revised_segment_id"], 2)

    async def test_factory_invalid_provider_fallback(self):
        """Edge Case 6: Invalid provider name gracefully defaults to MockTranslator."""
        t = get_translator("non_existent_engine_abc")
        self.assertIsInstance(t, MockTranslator)
        req = TranslationRequest(request_id="r1", speech_text="Hello world")
        resp = await t.translate(req)
        self.assertIn("Hello world", resp.translated_text)

    async def test_gemini_without_api_key_graceful_handling(self):
        """Edge Case 7: GeminiTranslator without API key returns structured fallback, does not crash."""
        gemini = GeminiTranslator(api_key="")
        req = TranslationRequest(request_id="g1", speech_text="Artificial Intelligence")
        resp = await gemini.translate(req)
        self.assertIn("GEMINI_API_KEY chưa cấu hình", resp.translated_text)
        self.assertEqual(resp.request_id, "g1")

    async def test_local_llm_skeleton_does_not_crash(self):
        """Edge Case 8: LocalLLMTranslator returns structured output without crashing."""
        local_llm = LocalLLMTranslator(model_path="Qwen/Qwen2.5-1.5B-Instruct")
        local_llm.load_model()
        req = TranslationRequest(request_id="loc1", speech_text="Deep learning computing")
        resp = await local_llm.translate(req)
        self.assertIn("Qwen2.5-1.5B-Instruct", resp.translated_text)

if __name__ == "__main__":
    unittest.main()
