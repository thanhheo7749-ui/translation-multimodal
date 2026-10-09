import time
import asyncio
from backend.translation.base import BaseTranslator
from backend.translation.contracts import TranslationRequest, TranslationResponse

class MockTranslator(BaseTranslator):
    """
    Deterministic mock translator for testing, benchmarking, and offline simulation.
    Preserves known technical entities and models contextual revisions.
    """
    @property
    def provider_name(self) -> str:
        return "mock"

    async def translate(self, request: TranslationRequest) -> TranslationResponse:
        t0 = time.perf_counter()
        # Simulate slight inference delay (e.g. 5ms)
        await asyncio.sleep(0.005)

        text = request.speech_text.strip()
        lower_text = text.lower()
        visual_grounded = bool(request.relevant_entities or request.slide_title)
        is_rev = request.action == "REVISE_PREVIOUS"

        # Keynote demo responses
        if "relationship with you started here" in lower_text:
            vi = "Mối quan hệ của tôi với các bạn bắt đầu từ đây, và nhiều người trong số các bạn, nhiều đối tác của tôi tại Đài Loan."
        elif "your companies started here" in lower_text:
            vi = "Các công ty của quý vị đã khởi nguồn từ chính nơi này."
        elif "modern computer industry 40 years now" in lower_text:
            if is_rev:
                vi = "Theo nhiều cách, đây chính là sự khởi đầu của ngành công nghiệp máy tính hiện đại cách đây 40 năm, và nó đã 33 năm tuổi."
            else:
                vi = "Theo nhiều cách, đây là điểm khởi đầu của ngành công nghiệp máy tính hiện đại cách đây 40 năm."
        elif "and it is 33 years old" in lower_text:
            vi = "Và ngành công nghiệp này đã 33 năm tuổi."
        elif "pc industry was already starting" in lower_text:
            vi = "Ngành công nghiệp máy tính cá nhân khi đó đã bắt đầu thu hút mọi người."
        elif "reinvent how the pc is going to work" in lower_text:
            entities_str = ", ".join(request.relevant_entities) if request.relevant_entities else ""
            if "OPENSHELL" in request.relevant_entities:
                vi = f"[Ngữ cảnh: {request.slide_title}] NVIDIA và Microsoft hợp tác tái định nghĩa cách thức hoạt động của PC kết hợp với nền tảng OPENSHELL."
            else:
                vi = f"NVIDIA và Microsoft đã hợp tác tái định nghĩa lại hoàn toàn cách thức hoạt động của PC."
        else:
            # Fallback mock rule: preserve capitalized entities
            vi = f"[Bản dịch]: {text}"
            if request.relevant_entities:
                vi += f" (Thuật ngữ: {', '.join(request.relevant_entities)})"

        elapsed_ms = (time.perf_counter() - t0) * 1000

        return TranslationResponse(
            request_id=request.request_id,
            original_text=request.speech_text,
            translated_text=vi,
            provider=self.provider_name,
            latency_ms=round(elapsed_ms, 2),
            visual_grounded=visual_grounded,
            is_revision=is_rev
        )
