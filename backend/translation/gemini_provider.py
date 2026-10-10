import os
import time
import httpx
from backend.translation.base import BaseTranslator
from backend.translation.contracts import TranslationRequest, TranslationResponse
from backend.translation.prompt_builder import build_fusion_prompt

class GeminiTranslator(BaseTranslator):
    """
    Production-grade LLM translator utilizing Google Gemini API with Fusion Prompt injection.
    Supports asynchronous streaming and low-latency response generation.
    """
    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key if api_key is not None else os.getenv("GEMINI_API_KEY", "")
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
        self.base_url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"

    @property
    def provider_name(self) -> str:
        return f"gemini ({self.model})"

    async def translate(self, request: TranslationRequest) -> TranslationResponse:
        t0 = time.perf_counter()
        visual_grounded = bool(request.relevant_entities or request.slide_title)
        prompt = build_fusion_prompt(request)

        if not self.api_key:
            # If no API key is provided, return a structured fallback notice
            elapsed_ms = (time.perf_counter() - t0) * 1000
            return TranslationResponse(
                request_id=request.request_id,
                original_text=request.speech_text,
                translated_text=f"[GEMINI_API_KEY chưa cấu hình] {request.speech_text}",
                provider=self.provider_name,
                latency_ms=round(elapsed_ms, 2),
                visual_grounded=visual_grounded,
                is_revision=request.action == "REVISE_PREVIOUS"
            )

        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 200,
                "topP": 0.95
            }
        }

        if self.model == "gemini-3.8-flash":
            payload["generationConfig"]["thinkingConfig"] = {"thinkingLevel": "low"}
        url = self.base_url
        timeout = httpx.Timeout(request.deadline_budget_ms / 1000.0, connect=5.0)

        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                resp = await client.post(url, json=payload, headers={"x-goog-api-key": self.api_key})
                resp.raise_for_status()
                data = resp.json()
                translated_text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            except Exception as e:
                translated_text = f"[Lỗi dịch Gemini: {type(e).__name__}]"

        elapsed_ms = (time.perf_counter() - t0) * 1000
        return TranslationResponse(
            request_id=request.request_id,
            original_text=request.speech_text,
            translated_text=translated_text,
            provider=self.provider_name,
            latency_ms=round(elapsed_ms, 2),
            visual_grounded=visual_grounded,
            is_revision=request.action == "REVISE_PREVIOUS"
        )
