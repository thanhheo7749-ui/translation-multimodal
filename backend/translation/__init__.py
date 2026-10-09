"""
Translation subsystem package for multimodal video translation.
"""
from backend.translation.contracts import ASRSegment, TranslationRequest, TranslationResponse, VisualEntity
from backend.translation.prompt_builder import build_fusion_prompt
from backend.translation.base import BaseTranslator
from backend.translation.factory import get_translator

__all__ = [
    "ASRSegment",
    "TranslationRequest",
    "TranslationResponse",
    "VisualEntity",
    "build_fusion_prompt",
    "BaseTranslator",
    "get_translator"
]
