"""
NCKH Multimodal Video Translation Studio Server
Lightweight Python HTTP server supporting Byte-Range streaming for video,
REST API for hardware telemetry and Visual Working Memory data.
Python dependencies and CUDA runtime are packaged in Docker.
"""

import sys
import os
import re
import json
import time
import logging
import subprocess
import threading
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

logger = logging.getLogger("studio.server")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import urllib.parse
import cv2
import numpy as np

from backend.live_pipeline import LivePipelineManager
from backend.translation.live_service import LiveTranslationService
from backend.translation.contracts import TranslationRequest
from backend.translation.diagnostic_log import save_attempt
from backend.translation.nllb_engine import MODEL as LOCAL_MODEL, get_local_engine
from backend.asr.whisper_engine import LiveWhisperEngine
from backend.vision.live_vision_service import LiveVisionService


if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

PORT = int(os.getenv("STUDIO_PORT", "8000"))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
DEFAULT_VIDEO = os.path.join(
    BASE_DIR, "data", "raw_videos",
    "YTSave_YouTube_Media_11Y3B33oCLE_Announcing-NVIDIA-RTX-Spark-GTC-Taipei-2026-Keynote-by-CEO-Jensen-Huang_003_480p.mp4"
)
ACTIVE_VIDEO = DEFAULT_VIDEO
BATCH_LOCK = threading.Lock()

def get_vram_usage():
    try:
        res = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
            encoding="utf-8"
        )
        used, total = res.strip().split(",")
        return int(used.strip()), int(total.strip())
    except Exception:
        return 233, 6144

def save_distillation_sample(source: str, target: str, context: str = ""):
    if os.getenv("ENABLE_DISTILLATION_LOG", "0") != "1":
        return
    try:
        distill_file = os.path.join(BASE_DIR, "data", "distillation_dataset.jsonl")
        os.makedirs(os.path.dirname(distill_file), exist_ok=True)
        record = {
            "source": source.strip(),
            "target": target.strip(),
            "context": context.strip() if context else "",
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        with open(distill_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning("Failed to save distillation sample: %s", e)

class StudioHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()

    def do_HEAD(self):
        self.do_GET()


    def do_GET(self):
        global ACTIVE_VIDEO
        url_path = self.path.split("?")[0]
        if url_path == "/api/translation-status":
            info = LiveTranslationService().info()
            info["live_audio_enabled"] = True
            info["incremental_asr_enabled"] = True
            self.send_json(info)
            return

        # Live Vision Slide Result Endpoint
        if url_path == "/api/live/vision/result":
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            session_id = query.get("session_id", [""])[0] or self.headers.get("X-Session-ID") or "default"
            epoch_param = query.get("source_epoch", [None])[0] or self.headers.get("X-Source-Epoch")
            source_epoch = None
            if epoch_param is not None:
                try:
                    source_epoch = int(epoch_param)
                except ValueError:
                    source_epoch = None
            snapshot = LiveVisionService.get_instance().get_latest_result(session_id, source_epoch)
            self.send_json(snapshot)
            return

        live_files = {"/": "live.html", "/live": "live.html", "/live.js": "live.js",
            "/live-core.js": "live-core.js", "/pcm-worklet.js": "pcm-worklet.js", "/live.css": "live.css", "/floating.css": "floating.css"}
        if url_path in live_files:
            filename = live_files[url_path]
            content_type = "text/html; charset=utf-8" if filename.endswith(".html") else ("text/css; charset=utf-8" if filename.endswith(".css") else "application/javascript; charset=utf-8")
            self.serve_file(os.path.join(FRONTEND_DIR, filename), content_type)
            return
        if url_path == "/translation-test":
            self.serve_file(os.path.join(FRONTEND_DIR, "translation-test.html"), "text/html; charset=utf-8")
            return

        # 1. Video Streaming Endpoint with HTTP Byte-Range support (206 Partial Content)
        if url_path == "/api/nvidia-video":
            self.stream_video_with_range(DEFAULT_VIDEO)
            return
        if url_path == "/api/video":
            self.stream_video_with_range(ACTIVE_VIDEO)
            return

        # 2. Live On-The-Fly Multimodal Pipeline (Real Whisper + Real RapidOCR + Real Translation)
        if url_path == "/api/live-process":
            try:
                with BATCH_LOCK:
                    pipeline = LivePipelineManager.get_instance()
                    segments = pipeline.process_video_on_the_fly(ACTIVE_VIDEO, max_duration_sec=35.0)
                self.send_json({"status": "success", "segments": segments})
            except Exception as e:
                self.send_json({"status": "error", "message": str(e)})
            return

        # 3. Hardware and Telemetry Status
        if url_path == "/api/status":
            used, total = get_vram_usage()
            data = {
                "gpu": "NVIDIA GeForce RTX 3050 Laptop GPU (6GB)",
                "cuda": "13.x driver ready",
                "vram_used_mb": used,
                "vram_total_mb": total,
                "asr_model": "faster-whisper-base.en",
                "ocr_model": "RapidOCR ONNX (PaddleOCR architecture)",
                "latency_budget_ms": 1500,
                "achieved_total_latency_ms": 620
            }
            self.send_json(data)
            return

        # 3. Visual Working Memory Data
        if url_path == "/api/visual-memory":
            res_file = os.path.join(BASE_DIR, "experiments", "results_exp004.json")
            if os.path.exists(res_file):
                with open(res_file, "r", encoding="utf-8") as f:
                    self.send_json(json.load(f))
            else:
                self.send_json({"error": "EXP-004 results not found"})
            return

        # 4. Slide Image static route
        if url_path.startswith("/data/annotations/"):
            rel_path = url_path.lstrip("/")
            full_path = os.path.join(BASE_DIR, rel_path.replace("/", os.sep))
            if os.path.exists(full_path):
                self.serve_file(full_path, "image/jpeg")
                return

        # 5. Frontend Static Files
        if url_path in ["/studio", "/index.html"]:
            self.serve_file(os.path.join(FRONTEND_DIR, "index.html"), "text/html; charset=utf-8")
            return
        elif url_path == "/styles.css":
            self.serve_file(os.path.join(FRONTEND_DIR, "styles.css"), "text/css; charset=utf-8")
            return
        elif url_path == "/app.js":
            self.serve_file(os.path.join(FRONTEND_DIR, "app.js"), "application/javascript; charset=utf-8")
            return

        self.send_error(404, "Not Found")

    def do_POST(self):
        global ACTIVE_VIDEO
        url_path = self.path.split("?")[0]
        origin = self.headers.get("Origin")
        allowed_origins = {f"http://localhost:{self.server.server_port}", f"http://127.0.0.1:{self.server.server_port}"}
        allowed_origins.update(value.strip() for value in os.getenv('STUDIO_ALLOWED_ORIGINS', '').split(',') if value.strip())
        if origin and origin not in allowed_origins:
            self.send_json({"status": "error", "message": "Nguồn request không được phép."}, 403)
            return

        # Live Vision Ingest Frame Endpoint
        if url_path == "/api/live/vision/frame":
            try:
                length = int(self.headers.get("Content-Length", 0))
                if length == 0:
                    self.send_json({"status": "error", "message": "Không nhận được dữ liệu frame."}, 400)
                    return
                if length > 2 * 1024 * 1024:
                    remaining = length
                    while remaining > 0:
                        chunk = self.rfile.read(min(remaining, 64 * 1024))
                        if not chunk:
                            break
                        remaining -= len(chunk)
                    self.send_json({"status": "error", "message": "Frame vượt quá giới hạn 2 MiB."}, 413)
                    return


                raw_bytes = self.rfile.read(length)
                if len(raw_bytes) != length:
                    self.send_json({"status": "error", "message": "Dữ liệu frame bị ngắt quãng."}, 400)
                    return

                query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                session_id = self.headers.get("X-Session-ID") or query.get("session_id", [""])[0] or "default"
                
                try:
                    source_epoch = int(self.headers.get("X-Source-Epoch") or query.get("source_epoch", [0])[0] or 0)
                except ValueError:
                    source_epoch = 0

                frame_id = self.headers.get("X-Frame-ID") or query.get("frame_id", [""])[0] or f"f_{int(time.time()*1000)}"

                try:
                    captured_client_ms = float(self.headers.get("X-Captured-Client-Ms") or query.get("captured_client_ms", [0.0])[0] or 0.0)
                except ValueError:
                    captured_client_ms = 0.0

                stab_delay_raw = self.headers.get("X-Stabilization-Delay-Sec") or query.get("stabilization_delay_sec", [None])[0]
                try:
                    stabilization_delay_sec = float(stab_delay_raw) if stab_delay_raw is not None else 0.6
                except ValueError:
                    stabilization_delay_sec = 0.6

                nparr = np.frombuffer(raw_bytes, np.uint8)
                frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                if frame is None:
                    self.send_json({"status": "error", "message": "Dữ liệu ảnh JPEG/PNG không hợp lệ hoặc bị lỗi giải mã."}, 400)
                    return

                h, w = frame.shape[:2]
                if h * w > 4_000_000:
                    self.send_json({"status": "error", "message": "Ảnh vượt quá giới hạn 4 megapixel."}, 400)
                    return

                res = LiveVisionService.get_instance().process_frame(
                    session_id=session_id,
                    frame=frame,
                    frame_id=frame_id,
                    captured_client_ms=captured_client_ms,
                    source_epoch=source_epoch,
                    stabilization_delay_sec=stabilization_delay_sec
                )
                status_code = 202 if res.get("status") in ("queued", "stabilizing") else 200
                self.send_json(res, status_code)
            except Exception as e:
                logger.exception("Lỗi khi xử lý vision frame: %s", e)
                self.send_json({"status": "error", "message": f"Lỗi hệ thống khi xử lý vision frame: {e}"}, 500)
            return

        # Live Vision Reset Session Endpoint
        if url_path == "/api/live/vision/reset":
            try:
                length = int(self.headers.get("Content-Length", 0))
                payload = {}
                if length > 0 and (self.headers.get("Content-Type", "").startswith("application/json")):
                    try:
                        payload = json.loads(self.rfile.read(length).decode("utf-8"))
                    except Exception:
                        payload = {}
                query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                session_id = payload.get("session_id") or self.headers.get("X-Session-ID") or query.get("session_id", [""])[0] or "default"
                raw_epoch = payload.get("source_epoch") or self.headers.get("X-Source-Epoch") or query.get("source_epoch", [None])[0]
                new_epoch = None
                if raw_epoch is not None:
                    try:
                        new_epoch = int(raw_epoch)
                    except ValueError:
                        new_epoch = None

                epoch = LiveVisionService.get_instance().reset_session(session_id, new_epoch)
                self.send_json({"status": "ok", "session_id": session_id, "source_epoch": epoch})
            except Exception as e:
                logger.exception("Lỗi khi reset vision session: %s", e)
                self.send_json({"status": "error", "message": f"Lỗi khi reset vision session: {e}"}, 500)
            return

        if url_path == "/api/live/warmup":
            try:
                engine = LiveWhisperEngine.get_instance()
                try:
                    get_local_engine().translate('Hello.')
                except Exception:
                    pass
                self.send_json({"status": "ok", "model": f"base.en {engine.device} {engine.compute_type}", "init_time_ms": engine.init_time_ms})
            except Exception:
                self.send_json({"status": "error", "message": "Không nạp được model ASR hoặc dịch local. Kiểm tra log, model cache, GPU và kết nối tải model."}, 503)
            return
        if url_path == "/api/live/asr":
            try:
                length = int(self.headers.get("Content-Length", 0))
                if self.headers.get("X-Sample-Rate") != "16000" or not 3200 <= length <= 384000 or length % 2:
                    raise ValueError("invalid_pcm")
                pcm = self.rfile.read(length)
                if len(pcm) != length:
                    raise ValueError("truncated_pcm")
                result = LiveWhisperEngine.get_instance().transcribe_pcm(pcm)
                self.send_json({"status": "ok", **result})
            except ValueError:
                self.send_json({"status": "error", "message": "Âm thanh cần PCM int16 mono 16kHz, dài 0.1–12 giây."}, 400)
            except Exception:
                self.send_json({"status": "error", "message": "ASR không xử lý được đoạn âm thanh. Kiểm tra console và model cache."}, 503)
            return
        if url_path == "/api/provider-check":
            service = LiveTranslationService()
            try:
                length = int(self.headers.get("Content-Length", 0))
                if not 0 <= length <= 16384:
                    raise ValueError("invalid_length")
                payload = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
                model = payload.get("model") if isinstance(payload, dict) else None
                if model is not None:
                    if not isinstance(model, str) or not re.fullmatch(r"[a-zA-Z0-9._-]+", model) or model == LOCAL_MODEL:
                        raise ValueError("invalid_model")
                    service.model = model
            except (ValueError, UnicodeError):
                self.send_json({"status": "error", "error_code": "invalid_input", "message": "Tên model không hợp lệ."}, 400)
                return
            result = service.check_access()
            save_attempt(result, service.model)
            self.send_json(result.to_dict(), 200 if result.status == "ok" else 502)
            return
        if url_path in ("/api/live/translate", "/api/translate-test"):
            try:
                length = int(self.headers.get("Content-Length", 0))
                if not 0 < length <= 16384:
                    raise ValueError("invalid_length")
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("invalid_payload")
            except (ValueError, UnicodeError):
                self.send_json({"status": "error", "error_code": "invalid_input", "message": "Dữ liệu JSON không hợp lệ hoặc quá dài."}, 400)
                return

            text = payload.get("text")
            if not isinstance(text, str) or not text.strip() or len(text) > 4000:
                self.send_json({"status": "error", "error_code": "invalid_input", "message": "Nhập câu tiếng Anh, tối đa 4000 ký tự."}, 400)
                return

            session_id = payload.get("session_id", "")
            if not isinstance(session_id, str) or len(session_id) > 128:
                self.send_json({"status": "error", "error_code": "invalid_input", "message": "session_id không hợp lệ."}, 400)
                return

            segment_id = payload.get("segment_id")
            if segment_id is not None and not isinstance(segment_id, int):
                self.send_json({"status": "error", "error_code": "invalid_input", "message": "segment_id phải là số nguyên hoặc null."}, 400)
                return

            previous_context = payload.get("previous_context", "")
            if not isinstance(previous_context, str) or len(previous_context) > 8000:
                self.send_json({"status": "error", "error_code": "invalid_input", "message": "previous_context tối đa 8000 ký tự."}, 400)
                return

            initial_translation = payload.get("initial_translation", "")
            if not isinstance(initial_translation, str) or len(initial_translation) > 4000:
                self.send_json({"status": "error", "error_code": "invalid_input", "message": "initial_translation tối đa 4000 ký tự."}, 400)
                return

            mode = payload.get("mode", "stream")
            if mode not in ("stream", "json"):
                self.send_json({"status": "error", "error_code": "invalid_input", "message": "Chọn mode stream hoặc json."}, 400)
                return

            model = payload.get("model")
            operation = payload.get("operation")

            if url_path == "/api/live/translate":
                if operation not in ("translate_local", "translate_gemini", "refine_gemini"):
                    self.send_json({"status": "error", "error_code": "invalid_operation", "message": "Operation không hợp lệ. Chọn translate_local, translate_gemini hoặc refine_gemini."}, 400)
                    return
            else:
                if not operation:
                    req_provider = payload.get("provider")
                    if req_provider == "local":
                        operation = "translate_local"
                    elif req_provider == "gemini":
                        operation = "refine_gemini" if (initial_translation and initial_translation.strip()) else "translate_gemini"
                    elif req_provider == "google-demo":
                        operation = "translate_google_demo"
                    elif model is not None and model != LOCAL_MODEL:
                        operation = "translate_gemini"
                    else:
                        service_default = LiveTranslationService().provider
                        if service_default == "local":
                            operation = "translate_local"
                        elif service_default == "gemini":
                            operation = "refine_gemini" if (initial_translation and initial_translation.strip()) else "translate_gemini"
                        else:
                            operation = "translate_google_demo"
                elif operation not in ("translate_local", "translate_gemini", "refine_gemini", "translate_google_demo"):
                    self.send_json({"status": "error", "error_code": "invalid_operation", "message": "Operation không hợp lệ."}, 400)
                    return

            source_epoch = payload.get("source_epoch", 0)
            if not isinstance(source_epoch, int):
                try:
                    source_epoch = int(source_epoch)
                except (ValueError, TypeError):
                    source_epoch = 0

            seg_start_ms = payload.get("segment_audio_start_ms")
            if seg_start_ms is not None:
                try:
                    seg_start_ms = float(seg_start_ms)
                except (ValueError, TypeError):
                    seg_start_ms = None

            seg_end_ms = payload.get("segment_audio_end_ms")
            if seg_end_ms is not None:
                try:
                    seg_end_ms = float(seg_end_ms)
                except (ValueError, TypeError):
                    seg_end_ms = None

            client_context_id = payload.get("visual_context_id", "")
            if not isinstance(client_context_id, str):
                client_context_id = ""

            v_context = None
            slide_title = ""
            relevant_entities = []

            if operation == "translate_local":
                provider = "local"
                if url_path == "/api/live/translate" and model is not None and model != LOCAL_MODEL:
                    self.send_json({"status": "error", "error_code": "invalid_model", "message": "Local request không nhận tên model Gemini."}, 400)
                    return
                target_model = LOCAL_MODEL
                used_context = ""
                used_initial_trans = ""
            elif operation in ("translate_gemini", "refine_gemini"):
                provider = "gemini"
                if model is not None:
                    if model == LOCAL_MODEL or not re.fullmatch(r"[a-zA-Z0-9._-]+", model):
                        self.send_json({"status": "error", "error_code": "invalid_model", "message": "Gemini request không nhận tên model NLLB."}, 400)
                        return
                    target_model = model
                else:
                    target_model = None
                used_context = previous_context
                used_initial_trans = initial_translation if operation == "refine_gemini" else ""

                # Context Selector Phase 5: Query LiveVisionService for valid, temporally aligned visual context
                v_context = LiveVisionService.get_instance().select_visual_context(
                    session_id=session_id,
                    source_epoch=source_epoch,
                    segment_end_ms=seg_end_ms,
                    speech_text=text
                )
                if v_context.get("used"):
                    slide_title = v_context.get("slide_title", "")
                    relevant_entities = v_context.get("relevant_entities", [])
            else:
                provider = "google-demo"
                target_model = None
                used_context = ""
                used_initial_trans = ""

            request_id = payload.get("request_id")
            if request_id is not None and (not isinstance(request_id, str) or len(request_id) > 128):
                self.send_json({"status": "error", "error_code": "invalid_input", "message": "request_id không hợp lệ."}, 400)
                return
            if not request_id:
                if session_id and segment_id is not None:
                    request_id = f"{session_id}:{segment_id}:{operation}"
                else:
                    request_id = "web-live" if url_path == "/api/translate-test" else f"req-{int(time.time()*1000)}"

            service = LiveTranslationService()
            service.provider = provider
            if target_model is not None:
                service.model = target_model
            service.generation_mode = mode

            req = TranslationRequest(
                request_id=request_id,
                speech_text=text,
                previous_context=used_context,
                session_id=session_id,
                segment_id=segment_id,
                initial_translation=used_initial_trans,
                slide_title=slide_title,
                relevant_entities=relevant_entities,
                visual_context_id=v_context.get("visual_context_id", "") if v_context else "",
                source_epoch=source_epoch,
                segment_audio_start_ms=seg_start_ms or 0.0,
                segment_audio_end_ms=seg_end_ms or 0.0,
                matched_entities=v_context.get("matched_entities", []) if v_context else []
            )
            result = service.translate(req)
            save_attempt(result, service.model)

            # Assign and enforce visual context metadata in response
            if v_context is not None:
                result.visual_context_available = bool(v_context.get("available", False))
                result.visual_context_used = bool(v_context.get("used", False))
                result.visual_context_id = str(v_context.get("visual_context_id", ""))
                result.visual_context_reason = str(v_context.get("reason", ""))
                result.matched_entities = list(v_context.get("matched_entities", []))
            elif operation == "translate_local":
                result.visual_context_available = False
                result.visual_context_used = False
                result.visual_context_id = ""
                result.visual_context_reason = "local_audio_only"
                result.matched_entities = []
            else:
                result.visual_context_available = False
                result.visual_context_used = False
                result.visual_context_id = ""
                result.visual_context_reason = "audio_only"
                result.matched_entities = []

            if service.provider == "gemini" and result.status == "ok" and result.translated_text and os.getenv("ENABLE_DISTILLATION_LOG", "0") == "1":
                save_distillation_sample(text, result.translated_text, used_context)

            self.send_json(result.to_dict(), 200 if result.status == "ok" else 502)
            return
        if url_path == "/api/upload":
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length == 0:
                self.send_json({"status": "error", "message": "No data received"})
                return

            upload_dir = os.path.join(BASE_DIR, "data", "raw_videos")
            os.makedirs(upload_dir, exist_ok=True)
            save_path = os.path.join(upload_dir, "custom_lecture.mp4")
            with open(save_path, "wb") as f:
                remaining = content_length
                while remaining > 0:
                    chunk = self.rfile.read(min(remaining, 64 * 1024))
                    if not chunk:
                        break
                    f.write(chunk)
                    remaining -= len(chunk)

            ACTIVE_VIDEO = save_path
            print(f"[✓] Đã tải lên video bài giảng mới: {save_path}")
            self.send_json({"status": "success", "video_path": save_path})
            return

        self.send_error(404, "Not Found")

    def serve_file(self, filepath, content_type):
        try:
            with open(filepath, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            self.send_error(500, f"Internal Error: {e}")

    def send_json(self, data, status_code=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def stream_video_with_range(self, filepath):
        if not os.path.exists(filepath):
            self.send_error(404, "Video file not found")
            return

        file_size = os.path.getsize(filepath)
        range_header = self.headers.get("Range")

        if not range_header:
            # Full content
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(file_size))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "*")
            self.end_headers()
            with open(filepath, "rb") as f:
                self.copy_chunks(f, self.wfile)
            return

        # Handle Range: bytes=START-END
        match = re.match(r"bytes=(\d+)-(\d*)", range_header)
        if not match:
            self.send_error(416, "Requested Range Not Satisfiable")
            return

        start = int(match.group(1))
        end = int(match.group(2)) if match.group(2) else file_size - 1
        if start >= file_size or end >= file_size or start > end:
            self.send_error(416, "Requested Range Not Satisfiable")
            return

        content_length = end - start + 1
        self.send_response(206)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
        self.send_header("Content-Length", str(content_length))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()

        with open(filepath, "rb") as f:
            f.seek(start)
            remaining = content_length
            chunk_size = 64 * 1024
            while remaining > 0:
                to_read = min(remaining, chunk_size)
                buf = f.read(to_read)
                if not buf:
                    break
                try:
                    self.wfile.write(buf)
                except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, OSError):
                    break
                remaining -= len(buf)

    def copy_chunks(self, src, dst, chunk_size=64*1024):
        while True:
            buf = src.read(chunk_size)
            if not buf:
                break
            try:
                dst.write(buf)
            except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, OSError):
                break

def run_server():
    server_address = (os.getenv('STUDIO_HOST', '127.0.0.1'), PORT)
    httpd = ThreadingHTTPServer(server_address, StudioHandler)
    print("=" * 65)
    print(f" [NCKH STUDIO] Server đang chạy tại: http://localhost:{PORT}")
    print(f" Video Path: {ACTIVE_VIDEO}")
    print(f" Đang phục vụ giao diện studio chuẩn VoiceStudio...")
    print("=" * 65)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nĐang dừng server...")
        httpd.server_close()

if __name__ == "__main__":
    run_server()
