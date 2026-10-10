"""Synchronous translation adapter for the local demo, with explicit failures."""
from dataclasses import asdict, dataclass, field
import json
import os
import re
import time
from typing import Optional
import urllib.error
import urllib.parse
import urllib.request

from backend.translation.contracts import TranslationRequest
from backend.translation.nllb_engine import MODEL as LOCAL_MODEL, get_local_engine
from backend.translation.network_support import classify_network_error, verified_ssl_context


@dataclass
class TranslationOutcome:
    status: str
    provider: str
    translated_text: str = ""
    latency_ms: float = 0
    error_code: str = ""
    message: str = ""
    context_supported: bool = False
    diagnostic: dict = field(default_factory=dict)
    phase: str = "translation"
    model: str = ""
    request_id: str = ""
    session_id: str = ""
    segment_id: Optional[int] = None

    def to_dict(self):
        return asdict(self)


class LiveTranslationService:
    def __init__(self):
        self.provider = os.getenv("TRANSLATION_PROVIDER", "google-demo").strip().lower()
        self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite").strip()
        self.model = LOCAL_MODEL if self.provider == "local" else self.gemini_model
        self.api_key = os.getenv("GEMINI_API_KEY", "")
        self.generation_mode = os.getenv("GEMINI_GENERATION_MODE", "stream")

    def info(self):
        gemini_model = self.model if (self.model and self.model != LOCAL_MODEL) else self.gemini_model
        gemini_configured = bool(self.api_key.strip()) if hasattr(self.api_key, 'strip') else bool(self.api_key)
        supported = self.provider in ("gemini", "google-demo", "local")
        return {
            "provider": self.provider,
            "local_model": LOCAL_MODEL,
            "gemini_model": gemini_model,
            "gemini_configured": gemini_configured,
            "context_supported": self.provider == "gemini",
            "generation_mode": self.generation_mode,
            "build": "2026-10-08-stream-1",
            "model": LOCAL_MODEL if self.provider == "local" else gemini_model if self.provider == "gemini" else None,
            "configured": supported and (self.provider != "gemini" or gemini_configured),
            "network_verified": False,
            "note": "Local NLLB; first use loads model weights. Text translation only; no visual context support." if self.provider == "local" else "google-demo chỉ để thử dịch văn bản; không hỗ trợ Fusion Prompt hoặc dùng làm benchmark đa phương thức." if self.provider == "google-demo" else "Cần API key và kết nối mạng; model phải có quyền truy cập trong API project."
        }

    def _configuration_error(self, outcome):
        if not self.api_key:
            outcome.error_code, outcome.message = "missing_api_key", "Chưa cấu hình GEMINI_API_KEY trên máy chạy server."
            return True
        if self.model == LOCAL_MODEL or not re.fullmatch(r"[a-zA-Z0-9._-]+", self.model):
            outcome.error_code, outcome.message = "invalid_model", "Tên GEMINI_MODEL không hợp lệ."
            return True
        return False

    def _http_failure(self, error, outcome):
        status, reason = "", ""
        try:
            body = json.loads(error.read(32768).decode("utf-8"))
            payload = body.get("error", {})
            candidate = payload.get("status", "")
            if candidate in ("INVALID_ARGUMENT", "UNAUTHENTICATED", "PERMISSION_DENIED", "NOT_FOUND", "RESOURCE_EXHAUSTED", "UNAVAILABLE", "INTERNAL", "FAILED_PRECONDITION", "DEADLINE_EXCEEDED", "ABORTED", "ALREADY_EXISTS", "OUT_OF_RANGE", "UNIMPLEMENTED", "DATA_LOSS", "CANCELLED", "UNKNOWN"):
                status = candidate
            for detail in payload.get("details", []):
                candidate = detail.get("reason", "") if isinstance(detail, dict) else ""
                if isinstance(candidate, str) and re.fullmatch(r"[A-Z_]{1,80}", candidate):
                    reason = candidate
                    break
            message = payload.get("message", "")
            if not reason and isinstance(message, str) and "api key not valid" in message.lower():
                reason = "API_KEY_INVALID"
        except (ValueError, OSError, AttributeError, TypeError):
            pass
        # Use known codes, never remote messages, headers, URLs or error bodies.
        known = {
            "API_KEY_INVALID": ("invalid_api_key", "Google không chấp nhận API key này. Tạo hoặc kiểm tra khóa Gemini trong Google AI Studio, rồi nhập lại trên máy."),
            "API_KEY_EXPIRED": ("expired_api_key", "API key đã hết hạn. Cấu hình một khóa Gemini mới trên máy."),
            "API_KEY_HTTP_REFERRER_BLOCKED": ("key_restricted", "Khóa bị giới hạn cho website/referrer; backend Python không đáp ứng điều kiện đó. Kiểm tra cấu hình giới hạn của khóa."),
            "API_KEY_IP_ADDRESS_BLOCKED": ("key_restricted", "Địa chỉ IP của backend không được phép dùng khóa này. Kiểm tra giới hạn IP của khóa."),
            "API_KEY_SERVICE_BLOCKED": ("key_restricted", "Khóa không được phép gọi Generative Language API. Kiểm tra giới hạn API của khóa."),
            "SERVICE_DISABLED": ("api_disabled", "Generative Language API chưa được bật cho project của khóa."),
        }
        if reason in known:
            outcome.error_code, outcome.message = known[reason]
        elif error.code == 429:
            outcome.error_code, outcome.message = "quota_exceeded", "Google báo hết quota hoặc vượt giới hạn request. Kiểm tra quota/billing của project trước khi thử lại."
        elif error.code == 404:
            outcome.error_code, outcome.message = "model_unavailable", f"Không truy cập được model {self.model} qua API hiện tại. Cần kiểm tra tên model và danh sách model của project."
        elif error.code in (401, 403):
            outcome.error_code, outcome.message = f"http_{error.code}", "Google từ chối xác thực hoặc quyền truy cập. Kiểm tra loại khóa, giới hạn API và quyền của project."
        elif error.code == 400:
            outcome.error_code, outcome.message = "invalid_request", "Google báo request không hợp lệ. Cần đối chiếu cấu hình model/tham số; không kết luận lỗi mạng."
        else:
            outcome.error_code, outcome.message = f"http_{error.code}", f"Provider trả HTTP {error.code}; request đã nhận được phản hồi HTTP."
        outcome.diagnostic = {"http_status": error.code}
        if status:
            outcome.diagnostic["api_status"] = status
        if reason in known:
            outcome.diagnostic["api_reason"] = reason

    def check_access(self):
        """Authenticated metadata request; no generation charge or translation claim."""
        started = time.perf_counter()
        outcome = TranslationOutcome("error", self.provider, context_supported=self.provider == "gemini", phase="model_access")
        outcome.model = self.model if self.provider == "gemini" else ""
        try:
            if self.provider != "gemini":
                outcome.error_code, outcome.message = "not_applicable", "Phép kiểm tra khóa/model này dành cho Gemini."
                return outcome
            if self._configuration_error(outcome):
                return outcome
            req = urllib.request.Request(
                f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}",
                headers={"x-goog-api-key": self.api_key})
            with urllib.request.urlopen(req, timeout=10, context=verified_ssl_context()) as response:
                model = json.loads(response.read().decode("utf-8"))
            if "generateContent" not in model.get("supportedGenerationMethods", []):
                outcome.error_code, outcome.message = "unsupported_generation", "Model trả metadata nhưng không hỗ trợ generateContent."
            else:
                outcome.status, outcome.message = "ok", f"Đã xác minh request có khóa truy cập được model {self.model}. Chưa kiểm tra quota/tốc độ tạo bản dịch."
        except urllib.error.HTTPError as error:
            self._http_failure(error, outcome)
        except (urllib.error.URLError, OSError) as error:
            outcome.error_code, outcome.message, outcome.diagnostic = classify_network_error(error)
        except (ValueError, AttributeError, TypeError):
            outcome.error_code, outcome.message = "invalid_response", "Không đọc được metadata model từ Google."
        finally:
            outcome.latency_ms = round((time.perf_counter()-started)*1000, 1)
        return outcome

    def translate(self, request: TranslationRequest) -> TranslationOutcome:
        started = time.perf_counter()
        outcome = TranslationOutcome(
            status="error",
            provider=self.provider,
            context_supported=self.provider == "gemini",
            request_id=request.request_id,
            session_id=request.session_id,
            segment_id=request.segment_id,
        )
        outcome.model = LOCAL_MODEL if self.provider == "local" else self.model if self.provider == "gemini" else ""
        stage = "configuration"
        speech = request.speech_text.strip()
        try:
            if not speech:
                outcome.error_code, outcome.message = "empty_input", "Hãy nhập một câu tiếng Anh."
                return outcome
            if self.provider == "gemini":
                outcome.model = self.model
                if self._configuration_error(outcome):
                    return outcome
                if request.initial_translation and request.initial_translation.strip():
                    prompt = (
                        "Bạn là chuyên gia hiệu chỉnh phụ đề trực tiếp. "
                        "Dưới đây là câu tiếng Anh gốc, bản dịch ban đầu và ngữ cảnh trước đó. "
                        "Hãy hiệu chỉnh bản dịch tiếng Việt sao cho ngắn gọn, tự nhiên, chuẩn văn phong hội thảo/thuyết trình, "
                        "bảo toàn ý câu, giữ nguyên tên riêng và các con số, không thêm thông tin. "
                        "Chỉ trả về duy nhất một câu dịch tiếng Việt đã hiệu chỉnh:\n"
                        + json.dumps({
                            "speech": speech,
                            "initial_translation": request.initial_translation.strip(),
                            "previous_context": request.previous_context,
                            "slide_title": request.slide_title,
                            "slide_entities": request.relevant_entities
                        }, ensure_ascii=False)
                    )
                else:
                    # Expert simultaneous interpreter prompt; natural spoken tone.
                    prompt = "Dịch đoạn nói tiếng Anh sau sang tiếng Việt tự nhiên, uyển chuyển, chuẩn văn phong hội thảo/thuyết trình, tuyệt đối không dịch máy móc theo từng từ. Chỉ trả về duy nhất câu dịch tiếng Việt:\n" + json.dumps({
                        "speech": speech, "previous_context": request.previous_context,
                        "slide_title": request.slide_title, "slide_entities": request.relevant_entities}, ensure_ascii=False)
                payload = {"contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": 0.2, "maxOutputTokens": 256}}
                if self.model == "gemini-3.8-flash":
                    payload["generationConfig"]["thinkingConfig"] = {"thinkingLevel": "low"}
                elif self.model == "gemini-3.5-flash-lite":
                    payload["generationConfig"]["thinkingConfig"] = {"thinkingLevel": "minimal"}
                if self.generation_mode not in ("stream", "json"):
                    outcome.error_code, outcome.message = "invalid_generation_mode", "Chọn chế độ stream hoặc json."
                    return outcome
                method = "streamGenerateContent?alt=sse" if self.generation_mode == "stream" else "generateContent"
                outcome.diagnostic = {"mode": self.generation_mode, "request_timeout_sec": 60}
                req = urllib.request.Request(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:{method}",
                    data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json", "x-goog-api-key": self.api_key})
                stage = "connect_or_response_headers"
                with urllib.request.urlopen(req, timeout=60, context=verified_ssl_context()) as response:
                    outcome.diagnostic["response_headers_ms"] = round((time.perf_counter()-started)*1000, 1)
                    stage = "response_body"
                    if self.generation_mode == "stream":
                        translated, finish = read_generation_stream(response, started, outcome.diagnostic)
                    else:
                        data = json.loads(response.read().decode("utf-8"))
                        candidate = data.get("candidates", [{}])[0]
                        finish = candidate.get("finishReason")
                        translated = "".join(p.get("text", "") for p in candidate.get("content", {}).get("parts", []) if not p.get("thought")).strip()
                if finish != "STOP":
                    outcome.error_code, outcome.message = "incomplete_generation", "Provider chưa trả bản dịch đầy đủ."
                    return outcome
            elif self.provider == "local":
                outcome.model = LOCAL_MODEL
                outcome.context_supported = False
                try:
                    result = get_local_engine().translate(speech)
                except Exception as error:
                    outcome.error_code = "local_model_error"
                    outcome.message = "Local model could not translate. Check model cache, GPU and dependencies."
                    outcome.diagnostic = {"exception_type": type(error).__name__}
                    return outcome
                translated = result["translation"]
            elif self.provider == "google-demo":
                url = "https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=vi&dt=t&q=" + urllib.parse.quote(speech)
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=8, context=verified_ssl_context()) as response:
                    data = json.loads(response.read().decode("utf-8"))
                translated = "".join(part[0] for part in data[0] if part[0]).strip()
            else:
                outcome.error_code, outcome.message = "unsupported_provider", "Chọn TRANSLATION_PROVIDER=local, gemini hoặc google-demo."
                return outcome
            if not translated:
                outcome.error_code, outcome.message = "empty_response", "Provider trả kết quả rỗng."
            elif translated.casefold() == speech.casefold():
                outcome.error_code, outcome.message = "unchanged_output", "Provider trả nguyên văn nguồn; cần kiểm tra, chưa coi là bản dịch tiếng Việt."
            else:
                outcome.status, outcome.translated_text = "ok", translated
                outcome.message = "Đã nhận bản dịch từ provider."
        except urllib.error.HTTPError as error:
            self._http_failure(error, outcome)
        except (urllib.error.URLError, OSError) as error:
            code, message, details = classify_network_error(error)
            outcome.error_code, outcome.message = code, message
            outcome.diagnostic.update(details)
            outcome.diagnostic["stage"] = stage
            if code == "network_timeout" and self.provider == "gemini":
                outcome.message = "Request tạo bản dịch quá thời gian chờ. Xem stage: connect_or_response_headers là chưa nhận HTTP headers; response_body là đã nhận headers nhưng chưa đọc xong nội dung. Kiểm tra log, không cần đổi khóa nếu model_access đã thành công."
        except (ValueError, KeyError, IndexError, TypeError):
            outcome.error_code, outcome.message = "invalid_response", "Không đọc được phản hồi của provider."
        finally:
            outcome.latency_ms = round((time.perf_counter()-started)*1000, 1)
        return outcome


def read_generation_stream(response, started, diagnostic):
    """Collect SSE text with timings; never treat truncated output as a completed translation."""
    texts, lines, plain_json = [], [], []
    finish = None

    def consume():
        nonlocal finish
        if not lines:
            return
        value = "\n".join(lines)
        lines.clear()
        if value.strip() == "[DONE]":
            return
        data = json.loads(value)
        candidates = data.get("candidates", [])
        if not candidates:
            return
        candidate = candidates[0]
        if candidate.get("finishReason"):
            finish = candidate["finishReason"]
        for part in candidate.get("content", {}).get("parts", []):
            if not part.get("thought") and part.get("text"):
                if "first_text_ms" not in diagnostic:
                    diagnostic["first_text_ms"] = round((time.perf_counter()-started)*1000, 1)
                texts.append(part["text"])

    for raw in response:
        if "first_response_line_ms" not in diagnostic:
            diagnostic["first_response_line_ms"] = round((time.perf_counter()-started)*1000, 1)
        line = raw.decode("utf-8").rstrip("\r\n")
        if line.startswith("data:"):
            lines.append(line[5:].lstrip())
        elif not line:
            consume()
            if finish == "STOP":
                break
        elif not line.startswith((":", "event:", "id:", "retry:")):
            plain_json.append(line)
    consume()
    if plain_json and not texts:
        # Support a normal JSON response while retaining the same completion checks.
        data = json.loads("\n".join(plain_json))
        candidate = data.get("candidates", [{}])[0]
        finish = candidate.get("finishReason")
        texts = [p.get("text", "") for p in candidate.get("content", {}).get("parts", []) if not p.get("thought")]
    return "".join(texts).strip(), finish
