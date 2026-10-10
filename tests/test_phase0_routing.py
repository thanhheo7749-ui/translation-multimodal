"""Unit tests for Phase 0: Backend Routing & Contract (SPEC_LIVE_SUBTITLES_LOCAL_FIRST.md)."""
import io
import json
import os
import tempfile
import threading
import urllib.error
import urllib.request
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import Mock, patch

from backend.translation.contracts import TranslationRequest
from backend.translation.live_service import LiveTranslationService, TranslationOutcome
from backend.translation.nllb_engine import MODEL as LOCAL_MODEL
from backend.server import StudioHandler, save_distillation_sample


class QuietHandler(StudioHandler):
    def log_message(self, *args):
        pass


def mock_response(data):
    val = Mock()
    val.__enter__ = Mock(return_value=io.BytesIO(json.dumps(data).encode()))
    val.__exit__ = Mock(return_value=False)
    return val


class TestPhase0ContractsAndRouting(unittest.TestCase):
    def test_translation_request_phase0_fields(self):
        req = TranslationRequest(
            request_id="req-1",
            speech_text="Hello world",
            session_id="session-xyz",
            segment_id=42,
            initial_translation="Xin chào thế giới"
        )
        self.assertEqual(req.session_id, "session-xyz")
        self.assertEqual(req.segment_id, 42)
        self.assertEqual(req.initial_translation, "Xin chào thế giới")

        # Test defaults
        default_req = TranslationRequest(request_id="req-def", speech_text="Test")
        self.assertEqual(default_req.session_id, "")
        self.assertIsNone(default_req.segment_id)
        self.assertEqual(default_req.initial_translation, "")

    def test_info_separated_fields(self):
        with patch.dict(os.environ, {
            "TRANSLATION_PROVIDER": "local",
            "GEMINI_MODEL": "gemini-3.5-flash-lite",
            "GEMINI_API_KEY": ""
        }):
            info_local = LiveTranslationService().info()
            self.assertEqual(info_local["provider"], "local")
            self.assertEqual(info_local["local_model"], LOCAL_MODEL)
            self.assertEqual(info_local["gemini_model"], "gemini-3.5-flash-lite")
            self.assertFalse(info_local["gemini_configured"])
            self.assertFalse(info_local["context_supported"])
            self.assertEqual(info_local["generation_mode"], "stream")
            self.assertEqual(info_local["build"], "2026-10-08-stream-1")

        with patch.dict(os.environ, {
            "TRANSLATION_PROVIDER": "gemini",
            "GEMINI_MODEL": "gemini-3.8-flash",
            "GEMINI_API_KEY": "fixture-key"
        }):
            info_gemini = LiveTranslationService().info()
            self.assertEqual(info_gemini["provider"], "gemini")
            self.assertEqual(info_gemini["local_model"], LOCAL_MODEL)
            self.assertEqual(info_gemini["gemini_model"], "gemini-3.8-flash")
            self.assertTrue(info_gemini["gemini_configured"])
            self.assertTrue(info_gemini["context_supported"])

    def test_local_provider_uses_local_model_and_ignores_context(self):
        mock_engine = Mock()
        mock_engine.translate.return_value = {"translation": "Bản dịch local"}
        with patch.dict(os.environ, {"TRANSLATION_PROVIDER": "local"}), \
             patch("backend.translation.live_service.get_local_engine", return_value=mock_engine):
            service = LiveTranslationService()
            service.model = "gemini-ignored-model"
            req = TranslationRequest(
                request_id="s1:1:local",
                speech_text="We have built a strong platform.",
                previous_context="Our company started 10 years ago.",
                session_id="s1",
                segment_id=1
            )
            result = service.translate(req)
            self.assertEqual(result.status, "ok")
            self.assertEqual(result.model, LOCAL_MODEL)
            self.assertFalse(result.context_supported)
            self.assertEqual(result.translated_text, "Bản dịch local")
            # Local engine must be called with ONLY speech_text, not previous_context
            mock_engine.translate.assert_called_once_with("We have built a strong platform.")

    def test_gemini_rejects_nllb_model(self):
        with patch.dict(os.environ, {
            "TRANSLATION_PROVIDER": "gemini",
            "GEMINI_API_KEY": "fixture-key"
        }):
            service = LiveTranslationService()
            service.model = LOCAL_MODEL
            req = TranslationRequest(request_id="r", speech_text="Hello")
            result = service.translate(req)
            self.assertEqual(result.status, "error")
            self.assertEqual(result.error_code, "invalid_model")

    def test_gemini_missing_api_key_reports_clear_error(self):
        with patch.dict(os.environ, {
            "TRANSLATION_PROVIDER": "gemini",
            "GEMINI_API_KEY": ""
        }), patch("urllib.request.urlopen") as opener:
            service = LiveTranslationService()
            req = TranslationRequest(request_id="r", speech_text="Hello")
            result = service.translate(req)
            opener.assert_not_called()
            self.assertEqual(result.status, "error")
            self.assertEqual(result.error_code, "missing_api_key")
            self.assertIn("Chưa cấu hình GEMINI_API_KEY", result.message)

    def test_gemini_refinement_prompt_when_initial_translation_provided(self):
        data = {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "Bản dịch hiệu chỉnh"}]}}]}
        with patch.dict(os.environ, {
            "TRANSLATION_PROVIDER": "gemini",
            "GEMINI_API_KEY": "fixture-key",
            "GEMINI_MODEL": "gemini-3.5-flash-lite"
        }), patch("urllib.request.urlopen", return_value=mock_response(data)) as opener:
            service = LiveTranslationService()
            req = TranslationRequest(
                request_id="s1:5:refine",
                speech_text="The Blackwell GPU achieves 4x training speedup.",
                previous_context="Hopper was great.",
                session_id="s1",
                segment_id=5,
                initial_translation="GPU Blackwell đạt 4x tăng tốc huấn luyện."
            )
            result = service.translate(req)
            self.assertEqual(result.status, "ok")
            self.assertEqual(result.translated_text, "Bản dịch hiệu chỉnh")
            self.assertEqual(result.session_id, "s1")
            self.assertEqual(result.segment_id, 5)

            req_sent = opener.call_args.args[0]
            body = json.loads(req_sent.data.decode("utf-8"))
            prompt_text = body["contents"][0]["parts"][0]["text"]
            self.assertIn("hiệu chỉnh", prompt_text)
            self.assertIn("GPU Blackwell đạt 4x tăng tốc huấn luyện.", prompt_text)
            self.assertIn("Blackwell", prompt_text)
            self.assertIn("Hopper was great.", prompt_text)

    def test_save_distillation_sample_flag(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            distill_file = os.path.join(temp_dir, "distill.jsonl")
            with patch("backend.server.BASE_DIR", temp_dir):
                # When ENABLE_DISTILLATION_LOG is not "1" -> no file created
                with patch.dict(os.environ, {"ENABLE_DISTILLATION_LOG": "0"}):
                    save_distillation_sample("Source text", "Bản dịch")
                    self.assertFalse(os.path.exists(distill_file))

                # When ENABLE_DISTILLATION_LOG is "1" -> record saved
                with patch.dict(os.environ, {"ENABLE_DISTILLATION_LOG": "1"}):
                    target_file = os.path.join(temp_dir, "data", "distillation_dataset.jsonl")
                    save_distillation_sample("Source text", "Bản dịch", "Context text")
                    self.assertTrue(os.path.exists(target_file))
                    with open(target_file, "r", encoding="utf-8") as f:
                        saved = json.loads(f.read().strip())
                    self.assertEqual(saved["source"], "Source text")
                    self.assertEqual(saved["target"], "Bản dịch")
                    self.assertEqual(saved["context"], "Context text")


class TestPhase0ServerEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), QuietHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)

    def post(self, path, body=b"", headers=None):
        req = urllib.request.Request(self.base + path, data=body, headers=headers or {}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    def test_live_translate_operation_translate_local(self):
        mock_outcome = TranslationOutcome(
            status="ok",
            provider="local",
            translated_text="Bản dịch NLLB",
            latency_ms=25.0,
            context_supported=False,
            model=LOCAL_MODEL,
            request_id="sess-1:1:translate_local",
            session_id="sess-1",
            segment_id=1
        )
        with patch.object(LiveTranslationService, "translate", return_value=mock_outcome) as mock_tr, \
             patch("backend.server.save_attempt"):
            status, res = self.post("/api/live/translate", json.dumps({
                "operation": "translate_local",
                "session_id": "sess-1",
                "segment_id": 1,
                "text": "Hello world"
            }).encode(), {"Content-Type": "application/json"})
            self.assertEqual(status, 200)
            self.assertEqual(res["status"], "ok")
            self.assertEqual(res["provider"], "local")
            self.assertEqual(res["model"], LOCAL_MODEL)
            self.assertEqual(res["translated_text"], "Bản dịch NLLB")
            self.assertFalse(res["context_supported"])
            self.assertEqual(res["session_id"], "sess-1")
            self.assertEqual(res["segment_id"], 1)

            # Check that service.translate was called with provider="local" and previous_context=""
            req_arg = mock_tr.call_args[0][0]
            self.assertEqual(req_arg.speech_text, "Hello world")
            self.assertEqual(req_arg.previous_context, "")

    def test_live_translate_rejects_gemini_model_for_local(self):
        status, res = self.post("/api/live/translate", json.dumps({
            "operation": "translate_local",
            "session_id": "sess-1",
            "segment_id": 1,
            "text": "Hello world",
            "model": "gemini-3.5-flash-lite"
        }).encode(), {"Content-Type": "application/json"})
        self.assertEqual(status, 400)
        self.assertEqual(res["error_code"], "invalid_model")

    def test_live_translate_rejects_nllb_model_for_gemini(self):
        status, res = self.post("/api/live/translate", json.dumps({
            "operation": "translate_gemini",
            "session_id": "sess-1",
            "segment_id": 1,
            "text": "Hello world",
            "model": LOCAL_MODEL
        }).encode(), {"Content-Type": "application/json"})
        self.assertEqual(status, 400)
        self.assertEqual(res["error_code"], "invalid_model")

    def test_live_translate_operation_refine_gemini(self):
        mock_outcome = TranslationOutcome(
            status="ok",
            provider="gemini",
            translated_text="Bản dịch đã hiệu chỉnh",
            latency_ms=120.0,
            context_supported=True,
            model="gemini-3.5-flash-lite",
            request_id="sess-1:1:refine_gemini",
            session_id="sess-1",
            segment_id=1
        )
        with patch.object(LiveTranslationService, "translate", return_value=mock_outcome) as mock_tr, \
             patch("backend.server.save_attempt"):
            status, res = self.post("/api/live/translate", json.dumps({
                "operation": "refine_gemini",
                "session_id": "sess-1",
                "segment_id": 1,
                "text": "The quick brown fox",
                "previous_context": "Earlier speech",
                "initial_translation": "Con cáo nhanh nhẹn"
            }).encode(), {"Content-Type": "application/json"})
            self.assertEqual(status, 200)
            self.assertEqual(res["status"], "ok")
            self.assertEqual(res["provider"], "gemini")
            self.assertTrue(res["context_supported"])
            self.assertEqual(res["translated_text"], "Bản dịch đã hiệu chỉnh")

            req_arg = mock_tr.call_args[0][0]
            self.assertEqual(req_arg.speech_text, "The quick brown fox")
            self.assertEqual(req_arg.previous_context, "Earlier speech")
            self.assertEqual(req_arg.initial_translation, "Con cáo nhanh nhẹn")

    def test_live_translate_rejects_invalid_operation(self):
        status, res = self.post("/api/live/translate", json.dumps({
            "operation": "unsupported_op",
            "text": "Hello"
        }).encode(), {"Content-Type": "application/json"})
        self.assertEqual(status, 400)
        self.assertEqual(res["error_code"], "invalid_operation")


if __name__ == "__main__":
    unittest.main()
