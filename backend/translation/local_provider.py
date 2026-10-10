"""Local provider backed by real NLLB weights; errors never echo source text."""
import asyncio
import time
from backend.translation.base import BaseTranslator
from backend.translation.contracts import TranslationResponse
from backend.translation.nllb_engine import MODEL, get_local_engine

class LocalLLMTranslator(BaseTranslator):
    @property
    def provider_name(self):
        return f"local ({MODEL})"

    async def translate(self, request):
        started = time.perf_counter()
        def infer():
            return get_local_engine().translate(request.speech_text)
        result = await asyncio.to_thread(infer)
        return TranslationResponse(
            request_id=request.request_id, original_text=request.speech_text,
            translated_text=result['translation'], provider=self.provider_name,
            latency_ms=round((time.perf_counter() - started) * 1000, 1),
            visual_grounded=False, is_revision=request.action == 'REVISE_PREVIOUS')
