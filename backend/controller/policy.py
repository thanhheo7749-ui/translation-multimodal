import re
import time
from typing import Tuple, Dict, Any, Optional
from backend.translation.contracts import ASRSegment, TranslationRequest
from backend.controller.state import VisualMemoryCache, ContextWindowManager

class AdaptiveController:
    """
    Adaptive Policy Controller (Module 3).
    Executes rule-based and entity-driven decisions to determine:
    1. If visual context (slide entities) is needed.
    2. If the current clause is dependent on the preceding sentence and warrants contextual revision.
    3. Enforces strict execution deadline budgets (< 10ms for controller, < 350ms for MT).
    """
    DEICTIC_KEYWORDS = {
        "table", "chart", "slide", "screen", "shown", "graph", "diagram", "figure"
    }

    CONNECTORS = [
        "and ", "but ", "or ", "so ", "because ", "which ", "where ", "while ",
        "it is ", "it's ", "they are ", "they're "
    ]

    def __init__(self, visual_cache: Optional[VisualMemoryCache] = None, max_history: int = 4):
        self.visual_cache = visual_cache or VisualMemoryCache()
        self.context_mgr = ContextWindowManager(max_history=max_history)

    def clean_disfluencies(self, text: str) -> str:
        """
        Removes repeated spoken stuttering / disfluency n-grams.
        e.g. 'many of you many of you' -> 'many of you'
        """
        cleaned = text.strip()
        # Repeatedly collapse repeated 1 to 4 word sequences
        pattern = r'\b(\w+(?:\s+\w+){0,3})\s+\1\b'
        prev = ""
        while prev != cleaned:
            prev = cleaned
            cleaned = re.sub(pattern, r'\1', cleaned, flags=re.IGNORECASE).strip()
        return cleaned

    def check_deictic_triggers(self, text: str) -> bool:
        """Checks if speech contains demonstratives or references to visual aids."""
        words = text.lower().split()
        for w in words:
            clean_w = w.strip(".,:;()[]\"'")
            if clean_w in self.DEICTIC_KEYWORDS:
                return True
        return False

    def check_connector_dependency(self, text: str) -> Tuple[bool, str]:
        """Checks if sentence begins with a dependent coordinating connector or dangling pronoun."""
        stripped = text.strip().lower()
        for c in self.CONNECTORS:
            if stripped.startswith(c):
                return True, c.strip()
        return False, ""

    def process_segment(self, segment: ASRSegment) -> Tuple[TranslationRequest, Dict[str, Any]]:
        """
        Processes an incoming ASR segment and constructs the optimal TranslationRequest.
        """
        t0 = time.perf_counter()

        # 1. Clean disfluencies
        cleaned_text = self.clean_disfluencies(segment.text)

        # 2. Match entities in RAM Visual Working Memory
        matched_entities = self.visual_cache.match_entities_in_text(cleaned_text)
        has_deictic = self.check_deictic_triggers(cleaned_text)
        visual_needed = bool(matched_entities or has_deictic)

        # 3. Check for discourse continuity / revision
        is_dependent, conn_keyword = self.check_connector_dependency(cleaned_text)
        last_seg = self.context_mgr.get_last_segment()

        action = "TRANSLATE_NOW"
        is_revision = False
        revised_id = None
        prev_context = ""

        if is_dependent and last_seg is not None:
            action = "REVISE_PREVIOUS"
            is_revision = True
            revised_id = last_seg["segment_id"]
            prev_context = last_seg["original_text"]

        elapsed_ms = (time.perf_counter() - t0) * 1000

        req = TranslationRequest(
            request_id=f"req_{segment.segment_id}_{int(time.time()*1000)%10000}",
            speech_text=cleaned_text,
            action=action,
            slide_title=self.visual_cache.title if visual_needed else "",
            relevant_entities=matched_entities if visual_needed else [],
            previous_context=prev_context,
            deadline_budget_ms=350.0
        )

        metadata = {
            "controller_latency_ms": round(elapsed_ms, 3),
            "visual_grounded": visual_needed,
            "matched_entities": matched_entities,
            "has_deictic": has_deictic,
            "is_revision": is_revision,
            "revised_segment_id": revised_id,
            "connector_keyword": conn_keyword
        }

        return req, metadata

    def record_completed_translation(self, segment_id: int, original_text: str, translated_text: str):
        """Records a completed translation into the sliding window buffer."""
        self.context_mgr.add_segment(segment_id, original_text, translated_text)
