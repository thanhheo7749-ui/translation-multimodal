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
    session_id: str = ""
    segment_id: Optional[int] = None
    initial_translation: str = ""
    visual_context_id: str = ""
    source_epoch: int = 0
    segment_audio_start_ms: float = 0.0
    segment_audio_end_ms: float = 0.0
    matched_entities: List[str] = field(default_factory=list)

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
    visual_context_available: bool = False
    visual_context_used: bool = False
    visual_context_id: str = ""
    visual_context_reason: str = ""
    matched_entities: List[str] = field(default_factory=list)

    def to_dict(self):
        from dataclasses import asdict
        return asdict(self)

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
    visual_context_available: bool = False
    visual_context_used: bool = False
    visual_context_id: str = ""
    visual_context_reason: str = ""
    matched_entities: List[str] = field(default_factory=list)

