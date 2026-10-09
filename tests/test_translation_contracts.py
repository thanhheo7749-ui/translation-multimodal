import unittest
from backend.translation.contracts import ASRSegment, TranslationRequest, TranslationResponse, VisualEntity
from backend.translation.prompt_builder import build_fusion_prompt

class TestTranslationContracts(unittest.TestCase):
    def test_asr_segment_dataclass(self):
        seg = ASRSegment(
            segment_id=1,
            text="Hello world",
            start_time=0.0,
            end_time=1.5,
            confidence=0.98,
            is_final=True
        )
        self.assertEqual(seg.segment_id, 1)
        self.assertEqual(seg.text, "Hello world")
        self.assertTrue(seg.is_final)

    def test_prompt_builder_audio_only(self):
        req = TranslationRequest(
            request_id="req_001",
            speech_text="Today we discuss artificial intelligence",
            action="TRANSLATE_NOW",
            slide_title="",
            relevant_entities=[]
        )
        prompt = build_fusion_prompt(req)
        self.assertIn("Today we discuss artificial intelligence", prompt)
        self.assertNotIn("Ngữ cảnh trên màn hình", prompt)

    def test_prompt_builder_with_visual_entities(self):
        req = TranslationRequest(
            request_id="req_002",
            speech_text="The agent connects with OpenShell",
            action="TRANSLATE_NOW",
            slide_title="NVIDIA and Microsoft Reinvent PC",
            relevant_entities=["OPENSHELL", "DeepSeek"]
        )
        prompt = build_fusion_prompt(req)
        self.assertIn("The agent connects with OpenShell", prompt)
        self.assertIn("NVIDIA and Microsoft Reinvent PC", prompt)
        self.assertIn("OPENSHELL, DeepSeek", prompt)

    def test_prompt_builder_with_previous_revision_context(self):
        req = TranslationRequest(
            request_id="req_003",
            speech_text="And it is 33 years old",
            action="REVISE_PREVIOUS",
            previous_context="This is in a lot of ways the beginning of the modern computer industry"
        )
        prompt = build_fusion_prompt(req)
        self.assertIn("And it is 33 years old", prompt)
        self.assertIn("Câu trước liền kề", prompt)

if __name__ == "__main__":
    unittest.main()
