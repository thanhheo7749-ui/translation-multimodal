from dataclasses import dataclass, field
from typing import Optional, List

@dataclass
class ASRSegment:
    segment_id: int
    text: str
    start_time: float
    end_time: float
    confidence: float = 1.0
    is_final: bool = True

@dataclass
class VisualEntity:
    text: str
    score: float
    box: List[List[int]] = field(default_factory=list)

@dataclass
class TranslationRequest:
    request_id: str
    speech_text: str
    action: str = "TRANSLATE_NOW"  # "TRANSLATE_NOW" | "REVISE_PREVIOUS" | "AUDIO_ONLY_FALLBACK"
    slide_title: str = ""
    relevant_entities: List[str] = field(default_factory=list)
    previous_context: str = ""
    deadline_budget_ms: float = 350.0

@dataclass
class TranslationResponse:
    request_id: str
    original_text: str
    translated_text: str
    provider: str
    latency_ms: float
    visual_grounded: bool
    is_revision: bool = False
    revised_segment_id: Optional[int] = None
