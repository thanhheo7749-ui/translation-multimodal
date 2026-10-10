import os
from backend.translation.base import BaseTranslator
from backend.translation.mock_provider import MockTranslator
from backend.translation.gemini_provider import GeminiTranslator
from backend.translation.local_provider import LocalLLMTranslator

def get_translator(provider_type: str = None) -> BaseTranslator:
    """
    Factory function returning a configured translation engine.
    Priority: Explicit parameter > TRANSLATION_PROVIDER env var > default 'mock'.
    """
    p_type = (provider_type or os.getenv("TRANSLATION_PROVIDER", "mock")).lower().strip()

    if p_type in ["mock", "test"]:
        return MockTranslator()
    elif p_type in ["gemini", "google", "cloud"]:
        return GeminiTranslator()
    elif p_type == "qwen":
        raise ValueError("Qwen is not implemented; select local for the NLLB engine")
    elif p_type in ["local", "nllb", "gpu"]:
        return LocalLLMTranslator()
    else:
        # Default to mock
        return MockTranslator()
