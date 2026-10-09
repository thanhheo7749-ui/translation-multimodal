import unittest
import asyncio
from backend.translation.contracts import TranslationRequest
from backend.translation.factory import get_translator
from backend.translation.mock_provider import MockTranslator

class TestTranslationProviders(unittest.IsolatedAsyncioTestCase):
    async def test_mock_translator_audio_only(self):
        translator = MockTranslator()
        req = TranslationRequest(
            request_id="req_01",
            speech_text="Your companies started here",
            action="TRANSLATE_NOW",
            relevant_entities=[]
        )
        res = await translator.translate(req)
        self.assertEqual(res.request_id, "req_01")
        self.assertFalse(res.visual_grounded)
        self.assertIn("công ty", res.translated_text.lower())
        self.assertGreater(res.latency_ms, 0)

    async def test_mock_translator_with_visual_entities(self):
        translator = MockTranslator()
        req = TranslationRequest(
            request_id="req_02",
            speech_text="The agent connects with OpenShell",
            action="TRANSLATE_NOW",
            slide_title="NVIDIA and Microsoft Reinvent PC",
            relevant_entities=["OPENSHELL", "DeepSeek"]
        )
        res = await translator.translate(req)
        self.assertTrue(res.visual_grounded)
        self.assertIn("OPENSHELL", res.translated_text)

    async def test_factory_creation(self):
        translator = get_translator("mock")
        self.assertIsInstance(translator, MockTranslator)

if __name__ == "__main__":
    unittest.main()
