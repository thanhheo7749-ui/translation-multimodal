import re
from typing import List, Dict, Optional, Set
from collections import deque
from backend.translation.contracts import VisualEntity

class VisualMemoryCache:
    """
    In-memory working cache for the current presentation slide.
    Stores OCR-extracted entities and provides microsecond-level keyword matching.
    """
    def __init__(self):
        self.slide_id: int = 0
        self.title: str = ""
        self.entities: List[VisualEntity] = []
        self._keyword_index: Dict[str, str] = {}  # lowercase_token -> original_entity_text

    STOPWORDS = {
        "and", "the", "for", "with", "from", "that", "this", "these", "those",
        "are", "was", "were", "been", "have", "has", "had", "not", "but", "you", "all",
        "can", "will", "our", "their", "its", "into", "over", "more", "most", "how", "what"
    }

    def update_slide(self, slide_id: int, title: str, entities: List[VisualEntity]):
        """Updates the working visual memory when a slide transition is detected."""
        self.slide_id = slide_id
        self.title = title
        self.entities = entities
        self._keyword_index.clear()

        for ent in entities:
            # Index each alphanumeric word token of entity (e.g. 'OPENSHELL', 'DeepSeek', 'Reinvent')
            tokens = re.findall(r'\b\w+\b', ent.text.lower())
            for clean_token in tokens:
                if len(clean_token) > 2 and clean_token not in self.STOPWORDS:
                    self._keyword_index[clean_token] = ent.text

    def match_entities_in_text(self, text: str) -> List[str]:
        """Matches words in the speech against cached visual entities."""
        matched: Set[str] = set()
        words = re.findall(r'\b\w+\b', text.lower())
        for clean_w in words:
            if clean_w in self._keyword_index:
                matched.add(self._keyword_index[clean_w])
        return list(matched)


class ContextWindowManager:
    """
    Sliding window manager that tracks recent speech segments and their translations.
    Supports anaphora resolution and revision across sentence boundaries.
    """
    def __init__(self, max_history: int = 4):
        self.max_history = max_history
        self.history: deque = deque(maxlen=max_history)

    def add_segment(self, segment_id: int, original_text: str, translated_text: str):
        self.history.append({
            "segment_id": segment_id,
            "original_text": original_text,
            "translated_text": translated_text
        })

    def get_last_segment(self) -> Optional[dict]:
        if self.history:
            return self.history[-1]
        return None

    def clear(self):
        self.history.clear()
