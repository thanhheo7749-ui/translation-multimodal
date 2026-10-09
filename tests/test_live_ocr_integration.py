import unittest
import os
from rapidocr_onnxruntime import RapidOCR
from backend.translation.contracts import ASRSegment, VisualEntity
from backend.translation.factory import get_translator
from backend.controller.state import VisualMemoryCache
from backend.controller.policy import AdaptiveController

class TestLiveOCRIntegration(unittest.IsolatedAsyncioTestCase):
    async def test_live_rapidocr_to_controller_pipeline(self):
        frame_path = os.path.join("data", "annotations", "frame_120s.jpg")
        self.assertTrue(os.path.exists(frame_path), f"Frame file not found at {frame_path}")

        # 1. Execute live RapidOCR
        engine = RapidOCR()
        ocr_result, elapse = engine(frame_path)
        self.assertIsNotNone(ocr_result)
        self.assertGreater(len(ocr_result), 5, "OCR should detect at least 5 text blocks")

        # 2. Extract entities into VisualEntity list
        entities = []
        for item in ocr_result:
            box, text, score = item[0], item[1].strip(), float(item[2])
            if score >= 0.6 and len(text) > 1:
                entities.append(VisualEntity(text=text, score=score, box=box))

        # 3. Populate VisualMemoryCache
        vcache = VisualMemoryCache()
        vcache.update_slide(
            slide_id=1,
            title="NVIDIA and Microsoft Reinvent PC",
            entities=entities
        )

        controller = AdaptiveController(visual_cache=vcache)
        translator = get_translator("mock")

        # 4. Test with keynote sentence mentioning OpenShell
        seg = ASRSegment(
            segment_id=6,
            text="Microsoft NVIDIA over the last three years, it took this long to completely reinvent how the PC is going to work and connect with OpenShell",
            start_time=120.0,
            end_time=132.0
        )
        req, meta = controller.process_segment(seg)
        resp = await translator.translate(req)

        # 5. Assertions
        self.assertTrue(meta["visual_grounded"])
        self.assertTrue(any("openshell" in e.lower() for e in meta["matched_entities"]))
        self.assertIn("OPENSHELL", resp.translated_text)
        self.assertLess(meta["controller_latency_ms"], 5.0)

if __name__ == "__main__":
    unittest.main()
