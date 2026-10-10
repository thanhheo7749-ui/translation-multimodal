"""
NCKH Multimodal Video Translation Studio - Live Vision Service
Phase 3 & Phase 4: Video Capture, Scene Stabilization, Background OCR & Session Slide Cache.

Manages isolated vision state per session, validates source epochs, stabilizes frame transitions
before OCR dispatch, runs non-blocking CPU OCR in background worker, and provides structured snapshots.
"""

import hashlib
import logging
import queue
import re
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union

import cv2
import numpy as np

from backend.controller.state import VisualMemoryCache
from backend.translation.contracts import VisualEntity
from backend.vision.scene_detector import SlideTransitionDetector

logger = logging.getLogger("studio.vision")


@dataclass
class SlideSnapshot:
    """Immutable snapshot of a recognized presentation slide."""
    session_id: str
    source_epoch: int
    frame_id: str
    slide_id: int
    slide_revision: int
    status: str  # "READY" | "EMPTY" | "ERROR" | "NO_FRAME" | "STABILIZING" | "OCR_PENDING"
    title: str
    entities: List[Dict[str, Any]]
    content_hash: str
    captured_client_ms: float = 0.0
    available_server_ms: float = 0.0
    server_ocr_ms: float = 0.0
    is_stale: bool = False
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "source_epoch": self.source_epoch,
            "frame_id": self.frame_id,
            "slide_id": self.slide_id,
            "slide_revision": self.slide_revision,
            "status": self.status,
            "title": self.title,
            "entities": self.entities,
            "content_hash": self.content_hash,
            "captured_client_ms": self.captured_client_ms,
            "available_server_ms": self.available_server_ms,
            "server_ocr_ms": self.server_ocr_ms,
            "is_stale": self.is_stale,
        }


@dataclass
class OCRJob:
    """Candidate job submitted to background CPU worker."""
    session_id: str
    source_epoch: int
    frame_id: str
    frame: np.ndarray
    captured_client_ms: float
    created_at: float = field(default_factory=time.time)


def compare_frames(
    frame1: np.ndarray,
    frame2: np.ndarray,
    downsample_size: Tuple[int, int] = (320, 180)
) -> Tuple[float, float]:
    """
    Computes (mean_pixel_diff, hist_correlation) between two frames.
    mean_diff: 0.0 to 255.0 (lower is more identical).
    correlation: -1.0 to 1.0 (higher is more identical).
    """
    if frame1 is None or frame2 is None or frame1.size == 0 or frame2.size == 0:
        return 255.0, 0.0

    r1 = cv2.resize(frame1, downsample_size, interpolation=cv2.INTER_AREA)
    r2 = cv2.resize(frame2, downsample_size, interpolation=cv2.INTER_AREA)

    g1 = cv2.cvtColor(r1, cv2.COLOR_BGR2GRAY) if len(r1.shape) == 3 else r1
    g2 = cv2.cvtColor(r2, cv2.COLOR_BGR2GRAY) if len(r2.shape) == 3 else r2

    h1 = cv2.calcHist([g1], [0], None, [64], [0, 256])
    h2 = cv2.calcHist([g2], [0], None, [64], [0, 256])
    cv2.normalize(h1, h1, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)
    cv2.normalize(h2, h2, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)

    correlation = float(cv2.compareHist(h1, h2, cv2.HISTCMP_CORREL))
    mean_diff = float(np.mean(cv2.absdiff(g1, g2)))
    return mean_diff, correlation


def compute_content_hash(entities: List[Dict[str, Any]]) -> str:
    """Computes a normalized SHA-256 prefix hash across extracted text entities."""
    if not entities:
        return ""
    normalized = [re.sub(r"\s+", " ", e.get("text", "").strip().lower()) for e in entities if e.get("text")]
    combined = "\n".join(filter(None, normalized))
    if not combined:
        return ""
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()[:16]


def extract_title_heuristic(entities: List[Dict[str, Any]], frame_height: int, frame_width: int) -> str:
    """
    Extracts slide title using layout geometry and bounding box prominence.
    No hardcoded domain keywords (e.g. no hardcoded NVIDIA/keynote).

    Criteria:
    1. Upper 40% vertical region of slide (y_min <= 0.40 * frame_height).
    2. Box height (font size) relative to slide height.
    3. Filter out noise: length < 3, pure digits (page numbers), score < 0.65.
    4. Prominence score: (h / frame_height) * 3.0 - (y_min / frame_height) * 1.0 + (score * 0.2).
    5. Returns candidate text with highest prominence >= 0.05, else empty string.
    """
    if frame_height <= 0 or not entities:
        return ""

    candidates = []
    for e in entities:
        text = e.get("text", "").strip()
        score = float(e.get("score", 0.0))
        box = e.get("box", [])
        if score < 0.65 or len(text) < 3:
            continue
        if re.fullmatch(r"^\d+$", text):
            continue
        if not box or len(box) < 4:
            continue

        ys = [p[1] for p in box]
        y_min = min(ys)
        y_max = max(ys)
        h = y_max - y_min

        if y_min / frame_height <= 0.40:
            rel_h = h / frame_height
            if rel_h < 0.02:  # Must have minimal font height
                continue
            prominence = rel_h * 3.0 - (y_min / frame_height) * 1.0 + (score * 0.2)
            candidates.append((prominence, text))

    if not candidates:
        return ""

    candidates.sort(key=lambda c: c[0], reverse=True)
    best_prominence, best_text = candidates[0]
    return best_text if best_prominence >= 0.05 else ""


def is_content_revision(prev_entities: List[Dict[str, Any]], new_entities: List[Dict[str, Any]]) -> bool:
    """
    Detects if the new entities represent a bullet-point revision of the existing slide.
    If the previous slide's texts are a strict subset of the new texts, it is a revision.
    """
    if not prev_entities or not new_entities:
        return False
    prev_set = set(e["text"].strip().lower() for e in prev_entities if e.get("text"))
    new_set = set(e["text"].strip().lower() for e in new_entities if e.get("text"))
    return len(prev_set) > 0 and len(new_set) > len(prev_set) and prev_set.issubset(new_set)


class SessionVisionState:
    """Maintains independent vision lifecycle, transition detector, and cache for one session."""

    def __init__(self, session_id: str, source_epoch: int = 0, max_history: int = 20):
        self.session_id = session_id
        self.source_epoch = source_epoch
        self.max_history = max_history

        self.detector = SlideTransitionDetector()
        self.visual_cache = VisualMemoryCache()
        self.current_snapshot: Optional[SlideSnapshot] = None
        self.history: deque = deque(maxlen=max_history)

        self.state = "IDLE"  # "IDLE" | "STABILIZING" | "OCR_PENDING" | "READY" | "EMPTY" | "ERROR"
        self.candidate_frame: Optional[np.ndarray] = None
        self.candidate_frame_id: str = ""
        self.candidate_captured_ms: float = 0.0
        self.candidate_first_seen_time: float = 0.0

        self.last_stable_frame: Optional[np.ndarray] = None
        self.last_frame_received_time: float = time.time()
        self.slide_counter: int = 0
        self.slide_revision: int = 0
        self.last_ocr_hash: str = ""
        self.lock = threading.Lock()

    def reset_epoch(self, new_epoch: int):
        """Resets detector and visual memory when source or timeline changes."""
        self.source_epoch = new_epoch
        self.detector.reset()
        self.candidate_frame = None
        self.candidate_frame_id = ""
        self.candidate_captured_ms = 0.0
        self.candidate_first_seen_time = 0.0

        self.last_stable_frame = None
        self.current_snapshot = None
        self.history.clear()
        self.state = "IDLE"
        self.slide_counter = 0
        self.slide_revision = 0
        self.last_ocr_hash = ""
        self.visual_cache = VisualMemoryCache()
        logger.info("Session %s reset to source_epoch %s", self.session_id, new_epoch)

    def ingest_frame(
        self,
        frame: np.ndarray,
        frame_id: str,
        captured_client_ms: float = 0.0,
        source_epoch: int = 0,
        stabilization_delay_sec: float = 0.6
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        """
        Evaluates incoming frame with temporal stabilization.

        Returns:
            (action, payload)
            action in: "DISPATCH_OCR", "STABILIZING", "UNCHANGED", "EMPTY"
        """
        self.last_frame_received_time = time.time()

        # Step 1: Check epoch
        if source_epoch != self.source_epoch:
            self.reset_epoch(source_epoch)

        # Step 2: Check for blank/solid color screen (talking head or black screen)
        if frame is None or frame.size == 0:
            return "EMPTY", self._make_empty_payload(frame_id, captured_client_ms)

        if float(np.std(frame)) < 2.0:
            self.state = "EMPTY"
            self.last_stable_frame = frame
            self.candidate_frame = None
            snap = SlideSnapshot(
                session_id=self.session_id,
                source_epoch=self.source_epoch,
                frame_id=frame_id,
                slide_id=self.slide_counter,
                slide_revision=0,
                status="EMPTY",
                title="",
                entities=[],
                content_hash="",
                captured_client_ms=captured_client_ms,
                available_server_ms=time.time() * 1000
            )
            self.current_snapshot = snap
            self.history.append(snap)
            self.visual_cache.update_slide(slide_id=self.slide_counter, title="", entities=[])
            return "EMPTY", snap.to_dict()

        # Step 3: Scene transition evaluation
        if self.state == "STABILIZING":
            # Compare current frame with the candidate frame to see if transition has settled
            mean_diff, corr = compare_frames(self.candidate_frame, frame)
            is_similar_to_candidate = (corr >= 0.88) and (mean_diff <= 28.0)

            if not is_similar_to_candidate:
                # Transition animation (fade/wipe) still active! Update candidate and restart timer
                self.candidate_frame = frame
                self.candidate_frame_id = frame_id
                self.candidate_captured_ms = captured_client_ms
                self.candidate_first_seen_time = time.monotonic()
                return "STABILIZING", {
                    "frame_id": frame_id,
                    "session_id": self.session_id,
                    "status": "stabilizing",
                    "reason": "transition_in_progress",
                    "mean_diff": round(mean_diff, 2),
                    "correlation": round(corr, 4)
                }

            # Frame is similar to candidate. Check elapsed time
            if captured_client_ms > 0 and self.candidate_captured_ms > 0 and captured_client_ms >= self.candidate_captured_ms:
                elapsed_sec = (captured_client_ms - self.candidate_captured_ms) / 1000.0
            else:
                elapsed_sec = time.monotonic() - self.candidate_first_seen_time

            if elapsed_sec >= stabilization_delay_sec:
                # Settled and stabilized! Dispatch to RapidOCR
                self.last_stable_frame = frame
                self.state = "OCR_PENDING"
                return "DISPATCH_OCR", {
                    "frame": frame,
                    "frame_id": frame_id,
                    "captured_client_ms": captured_client_ms,
                    "elapsed_sec": round(elapsed_sec, 3)
                }
            return "STABILIZING", {
                "frame_id": frame_id,
                "session_id": self.session_id,
                "status": "stabilizing",
                "reason": "stabilizing_wait",
                "elapsed_sec": round(elapsed_sec, 3),
                "required_sec": stabilization_delay_sec
            }

        if self.last_stable_frame is None:
            # First frame in this epoch
            if stabilization_delay_sec <= 0.0:
                self.last_stable_frame = frame
                self.state = "OCR_PENDING"
                return "DISPATCH_OCR", {
                    "frame": frame,
                    "frame_id": frame_id,
                    "captured_client_ms": captured_client_ms
                }
            self.candidate_frame = frame
            self.candidate_frame_id = frame_id
            self.candidate_captured_ms = captured_client_ms
            self.candidate_first_seen_time = time.monotonic()
            self.state = "STABILIZING"
            return "STABILIZING", {
                "frame_id": frame_id,
                "session_id": self.session_id,
                "epoch": self.source_epoch,
                "status": "stabilizing"
            }

        if self.state in ("READY", "EMPTY", "IDLE"):
            mean_diff, corr = compare_frames(self.last_stable_frame, frame)
            is_changed = (corr < 0.88) or (mean_diff > 28.0)

            if not is_changed:
                # Identical frame or minor webcam motion: deduplicate!
                snap_dict = self.current_snapshot.to_dict() if self.current_snapshot else {
                    "status": self.state,
                    "session_id": self.session_id,
                    "source_epoch": self.source_epoch,
                    "frame_id": frame_id,
                    "slide_id": self.slide_counter,
                    "content_hash": self.last_ocr_hash
                }
                return "UNCHANGED", snap_dict

            # Change detected! Enter stabilization phase
            if stabilization_delay_sec <= 0.0:
                self.last_stable_frame = frame
                self.state = "OCR_PENDING"
                return "DISPATCH_OCR", {
                    "frame": frame,
                    "frame_id": frame_id,
                    "captured_client_ms": captured_client_ms
                }
            self.candidate_frame = frame
            self.candidate_frame_id = frame_id
            self.candidate_captured_ms = captured_client_ms
            self.candidate_first_seen_time = time.monotonic()
            self.state = "STABILIZING"
            return "STABILIZING", {
                "frame_id": frame_id,
                "session_id": self.session_id,
                "epoch": self.source_epoch,
                "status": "stabilizing"
            }


        if self.state == "OCR_PENDING":
            # OCR is actively processing previous candidate.
            # If incoming frame is similar to the dispatched stable frame, deduplicate:
            mean_diff, corr = compare_frames(self.last_stable_frame, frame) if self.last_stable_frame is not None else (255.0, 0.0)
            if corr >= 0.88 and mean_diff <= 28.0:
                snap_dict = self.current_snapshot.to_dict() if self.current_snapshot else {
                    "status": "OCR_PENDING",
                    "session_id": self.session_id,
                    "source_epoch": self.source_epoch,
                    "frame_id": frame_id,
                    "slide_id": self.slide_counter
                }
                return "UNCHANGED", snap_dict

            # Brand new change occurred while previous OCR was pending
            self.candidate_frame = frame
            self.candidate_frame_id = frame_id
            self.candidate_captured_ms = captured_client_ms
            self.candidate_first_seen_time = time.monotonic()
            self.state = "STABILIZING"
            return "STABILIZING", {
                "frame_id": frame_id,
                "session_id": self.session_id,
                "status": "stabilizing",
                "reason": "new_change_while_ocr_pending"
            }

        return "UNCHANGED", None

    def _make_empty_payload(self, frame_id: str, captured_client_ms: float) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "source_epoch": self.source_epoch,
            "frame_id": frame_id,
            "slide_id": self.slide_counter,
            "slide_revision": 0,
            "status": "EMPTY",
            "title": "",
            "entities": [],
            "content_hash": "",
            "captured_client_ms": captured_client_ms,
            "is_stale": False
        }

    def get_snapshot(self, max_stale_sec: float = 5.0) -> Dict[str, Any]:
        """Returns snapshot, marking stale if heartbeat exceeded 5 seconds."""
        is_stale = (time.time() - self.last_frame_received_time) > max_stale_sec
        if self.current_snapshot is None:
            return {
                "session_id": self.session_id,
                "source_epoch": self.source_epoch,
                "frame_id": "",
                "slide_id": 0,
                "slide_revision": 0,
                "status": "NO_FRAME" if self.state == "IDLE" else self.state,
                "title": "",
                "entities": [],
                "content_hash": "",
                "captured_client_ms": 0.0,
                "available_server_ms": time.time() * 1000,
                "server_ocr_ms": 0.0,
                "is_stale": is_stale
            }

        snap_dict = self.current_snapshot.to_dict()
        snap_dict["is_stale"] = is_stale
        return snap_dict

    def select_visual_context(
        self,
        source_epoch: int = 0,
        segment_end_ms: Optional[float] = None,
        speech_text: str = "",
        min_entity_score: float = 0.85,
        max_entities: int = 20,
        max_chars: int = 1500,
        max_stale_sec: float = 5.0
    ) -> Dict[str, Any]:
        """
        Selects valid, temporally aligned visual context for translation/correction.
        Applies rules a-h from SPEC sections 8, 9, 10 & Phase 5:
        a) Session check: if no frame received -> available=False, used=False, reason="session_not_found"
        b) Epoch check: if self.source_epoch != source_epoch -> available=False, used=False, reason="epoch_mismatch"
        c) Snapshot status: must be "READY"
        d) Stale heartbeat: if last frame received > max_stale_sec -> available=False, used=False, is_stale=True, reason="context_stale"
        e) Anti-future frame: if segment_end_ms > 0 and captured_client_ms > segment_end_ms, search backwards in history.
        f) Filter entity confidence (score >= min_entity_score)
        g) Keyword matching & bounds (max 20 entities, max 1500 chars)
        h) Standard return dictionary.
        """
        # Rule b: Source epoch check
        if self.source_epoch != source_epoch:
            return {
                "available": False,
                "used": False,
                "visual_context_id": "",
                "reason": "epoch_mismatch",
                "slide_title": "",
                "relevant_entities": [],
                "matched_entities": []
            }

        # Rule a: Session check (no frames ingested yet)
        if self.current_snapshot is None and not self.history:
            return {
                "available": False,
                "used": False,
                "visual_context_id": "",
                "reason": "session_not_found",
                "slide_title": "",
                "relevant_entities": [],
                "matched_entities": []
            }

        # Rule d: Stale heartbeat check
        is_stale = (time.time() - self.last_frame_received_time) > max_stale_sec
        if is_stale:
            return {
                "available": False,
                "used": False,
                "is_stale": True,
                "visual_context_id": "",
                "reason": "context_stale",
                "slide_title": "",
                "relevant_entities": [],
                "matched_entities": []
            }

        # Rule e: Future frame rejection and historical fallback
        target_snapshot: Optional[SlideSnapshot] = None
        if segment_end_ms is not None and segment_end_ms > 0:
            if self.current_snapshot and self.current_snapshot.captured_client_ms <= segment_end_ms:
                target_snapshot = self.current_snapshot
            else:
                for snap in reversed(self.history):
                    if snap.captured_client_ms <= segment_end_ms and snap.status == "READY":
                        target_snapshot = snap
                        break
                if target_snapshot is None:
                    return {
                        "available": False,
                        "used": False,
                        "visual_context_id": "",
                        "reason": "future_frame_rejected",
                        "slide_title": "",
                        "relevant_entities": [],
                        "matched_entities": []
                    }
        else:
            target_snapshot = self.current_snapshot

        # Rule c: Snapshot status check - must be READY
        if target_snapshot is None or target_snapshot.status != "READY":
            status_reason = f"snapshot_{target_snapshot.status.lower()}" if target_snapshot else "no_snapshot"
            return {
                "available": False,
                "used": False,
                "visual_context_id": "",
                "reason": status_reason,
                "slide_title": "",
                "relevant_entities": [],
                "matched_entities": []
            }

        # Rule f: Filter entity confidence (score >= min_entity_score)
        high_conf_entities = []
        for e in target_snapshot.entities:
            sc = float(e.get("score", 0.0))
            txt = e.get("text", "").strip()
            if sc >= min_entity_score and txt:
                high_conf_entities.append({"text": txt, "score": sc, "box": e.get("box", [])})

        if not high_conf_entities and not target_snapshot.title:
            return {
                "available": True,
                "used": False,
                "visual_context_id": f"ctx_{target_snapshot.session_id}_{target_snapshot.source_epoch}_{target_snapshot.slide_id}_{target_snapshot.slide_revision}",
                "reason": "no_high_confidence_entities",
                "slide_title": "",
                "relevant_entities": [],
                "matched_entities": []
            }

        # Rule g: Keyword relevance matching using visual_cache and tokens
        temp_cache = VisualMemoryCache()
        temp_cache.update_slide(
            slide_id=target_snapshot.slide_id,
            title=target_snapshot.title,
            entities=[VisualEntity(text=e["text"], score=float(e["score"]), box=e.get("box", [])) for e in high_conf_entities]
        )
        raw_matched = temp_cache.match_entities_in_text(speech_text)

        matched_texts: List[str] = []
        for m in raw_matched:
            if m not in matched_texts:
                matched_texts.append(m)

        speech_tokens = set(re.findall(r"\b\w+\b", speech_text.lower()))
        for ent in high_conf_entities:
            txt = ent["text"]
            if txt not in matched_texts:
                e_tokens = [w for w in re.findall(r"\b\w+\b", txt.lower()) if len(w) > 2 and w not in VisualMemoryCache.STOPWORDS]
                if any(w in speech_tokens for w in e_tokens):
                    matched_texts.append(txt)

        # Prioritize matched entities, then other high confidence entities by score descending
        other_entities = [
            e["text"] for e in sorted(high_conf_entities, key=lambda x: float(x["score"]), reverse=True)
            if e["text"] not in matched_texts
        ]
        all_candidates = matched_texts + other_entities

        # Apply limits: max_entities (20) and max_chars (1500)
        relevant_entities: List[str] = []
        total_chars = len(target_snapshot.title)
        for ent_txt in all_candidates:
            if len(relevant_entities) >= max_entities:
                break
            if total_chars + len(ent_txt) + 2 > max_chars:
                break
            relevant_entities.append(ent_txt)
            total_chars += len(ent_txt) + 2

        final_matched = [m for m in matched_texts if m in relevant_entities]
        visual_context_id = f"ctx_{target_snapshot.session_id}_{target_snapshot.source_epoch}_{target_snapshot.slide_id}_{target_snapshot.slide_revision}"

        return {
            "available": True,
            "used": True,
            "visual_context_id": visual_context_id,
            "reason": "context_selected",
            "slide_title": target_snapshot.title,
            "relevant_entities": relevant_entities,
            "matched_entities": final_matched
        }



class LiveVisionService:
    """
    Central Vision Service managing session states and CPU background OCR worker.
    Single worker queue with maxsize=1 ensures ASR and MT are never blocked.
    """
    _instance: Optional["LiveVisionService"] = None
    _instance_lock = threading.Lock()

    @classmethod
    def get_instance(cls, ocr_engine: Optional[Any] = None) -> "LiveVisionService":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls(ocr_engine=ocr_engine)
        return cls._instance

    def __init__(self, ocr_engine: Optional[Any] = None, max_history: int = 20):
        self._sessions: Dict[str, SessionVisionState] = {}
        self._sessions_lock = threading.Lock()
        self._ocr_engine = ocr_engine
        self._ocr_engine_lock = threading.Lock()
        self._max_history = max_history

        # Single worker queue holding at most 1 candidate
        self._job_queue: queue.Queue = queue.Queue(maxsize=1)
        self._queue_lock = threading.Lock()
        self._stopped = False
        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            name="VisionOCRWorker",
            daemon=True
        )
        self._worker_thread.start()

    def get_session(self, session_id: str, source_epoch: int = 0) -> SessionVisionState:
        with self._sessions_lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = SessionVisionState(
                    session_id=session_id,
                    source_epoch=source_epoch,
                    max_history=self._max_history
                )
            return self._sessions[session_id]

    def reset_session(self, session_id: str, new_epoch: Optional[int] = None) -> int:
        session = self.get_session(session_id)
        with session.lock:
            next_epoch = (session.source_epoch + 1) if new_epoch is None else new_epoch
            session.reset_epoch(next_epoch)
            return next_epoch

    def process_frame(
        self,
        session_id: str,
        frame: np.ndarray,
        frame_id: str,
        captured_client_ms: float = 0.0,
        source_epoch: int = 0,
        stabilization_delay_sec: float = 0.6
    ) -> Dict[str, Any]:
        """
        Receives frame, performs lightweight transition & stabilization check (<2ms).
        Dispatches to async OCR queue only when stabilized.
        """
        session = self.get_session(session_id, source_epoch)
        with session.lock:
            action, payload = session.ingest_frame(
                frame=frame,
                frame_id=frame_id,
                captured_client_ms=captured_client_ms,
                source_epoch=source_epoch,
                stabilization_delay_sec=stabilization_delay_sec
            )

        if action == "DISPATCH_OCR":
            job = OCRJob(
                session_id=session_id,
                source_epoch=source_epoch,
                frame_id=frame_id,
                frame=frame,
                captured_client_ms=captured_client_ms
            )
            self._dispatch_job(job)
            return {
                "status": "queued",
                "session_id": session_id,
                "source_epoch": source_epoch,
                "frame_id": frame_id,
                "state": "OCR_PENDING"
            }
        elif action == "UNCHANGED":
            return {
                "status": "unchanged",
                "session_id": session_id,
                "source_epoch": source_epoch,
                "frame_id": frame_id,
                "snapshot": payload
            }
        elif action == "STABILIZING":
            return {
                "status": "stabilizing",
                "session_id": session_id,
                "source_epoch": source_epoch,
                "frame_id": frame_id,
                **(payload or {})
            }
        elif action == "EMPTY":
            return {
                "status": "empty",
                "session_id": session_id,
                "source_epoch": source_epoch,
                "frame_id": frame_id,
                "snapshot": payload
            }

        return {"status": "ok", "session_id": session_id, "action": action}

    def process_frame_sync(
        self,
        session_id: str,
        frame: np.ndarray,
        frame_id: str,
        captured_client_ms: float = 0.0,
        source_epoch: int = 0,
        stabilization_delay_sec: float = 0.0
    ) -> Dict[str, Any]:
        """
        Synchronous processing mode for testing and evaluation.
        Executes OCR immediately if frame qualifies.
        """
        session = self.get_session(session_id, source_epoch)
        with session.lock:
            action, payload = session.ingest_frame(
                frame=frame,
                frame_id=frame_id,
                captured_client_ms=captured_client_ms,
                source_epoch=source_epoch,
                stabilization_delay_sec=stabilization_delay_sec
            )

        if action == "DISPATCH_OCR":
            job = OCRJob(
                session_id=session_id,
                source_epoch=source_epoch,
                frame_id=frame_id,
                frame=frame,
                captured_client_ms=captured_client_ms
            )
            self._execute_ocr_job(job)
            return session.get_snapshot()
        elif action in ("UNCHANGED", "EMPTY"):
            return payload if isinstance(payload, dict) else session.get_snapshot()
        else:
            return {"status": action.lower(), **(payload or {})}

    def get_latest_result(self, session_id: str, source_epoch: Optional[int] = None) -> Dict[str, Any]:
        """Returns the latest slide snapshot for the session."""
        with self._sessions_lock:
            if session_id not in self._sessions:
                return {
                    "status": "NO_FRAME",
                    "session_id": session_id,
                    "source_epoch": source_epoch or 0,
                    "frame_id": "",
                    "slide_id": 0,
                    "slide_revision": 0,
                    "title": "",
                    "entities": [],
                    "content_hash": "",
                    "is_stale": True
                }
            session = self._sessions[session_id]

        with session.lock:
            if source_epoch is not None and session.source_epoch != source_epoch:
                return {
                    "status": "NO_FRAME",
                    "session_id": session_id,
                    "source_epoch": source_epoch,
                    "frame_id": "",
                    "slide_id": 0,
                    "slide_revision": 0,
                    "title": "",
                    "entities": [],
                    "content_hash": "",
                    "is_stale": True
                }
            return session.get_snapshot()

    def _dispatch_job(self, job: OCRJob):
        """Puts candidate into worker queue; drops older waiting candidate if full."""
        with self._queue_lock:
            if self._job_queue.full():
                try:
                    _ = self._job_queue.get_nowait()
                    self._job_queue.task_done()
                except (queue.Empty, ValueError):
                    pass
            try:
                self._job_queue.put_nowait(job)
            except queue.Full:
                pass

    def _worker_loop(self):
        while not self._stopped:
            try:
                job: OCRJob = self._job_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            try:
                self._execute_ocr_job(job)
            except Exception as e:
                logger.exception("OCR Worker unhandled exception: %s", e)
            finally:
                self._job_queue.task_done()

    def _execute_ocr_job(self, job: OCRJob):
        session = self.get_session(job.session_id, job.source_epoch)
        with session.lock:
            if session.source_epoch != job.source_epoch:
                logger.info("Discarding outdated OCR job (epoch %s vs %s)", job.source_epoch, session.source_epoch)
                return

        # Lazy init RapidOCR engine
        if self._ocr_engine is None:
            with self._ocr_engine_lock:
                if self._ocr_engine is None:
                    from rapidocr_onnxruntime import RapidOCR
                    self._ocr_engine = RapidOCR()

        t0 = time.perf_counter()
        status_error = False
        ocr_result = None
        try:
            # Ensure frame has 3 color channels
            img = job.frame
            if len(img.shape) == 2:
                img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
            ocr_result, _ = self._ocr_engine(img)
            ocr_latency_ms = (time.perf_counter() - t0) * 1000
        except Exception as e:
            logger.exception("RapidOCR engine execution failed: %s", e)
            ocr_latency_ms = (time.perf_counter() - t0) * 1000
            status_error = True

        with session.lock:
            if session.source_epoch != job.source_epoch:
                return

            if status_error:
                snapshot = SlideSnapshot(
                    session_id=session.session_id,
                    source_epoch=session.source_epoch,
                    frame_id=job.frame_id,
                    slide_id=session.slide_counter,
                    slide_revision=session.slide_revision,
                    status="ERROR",
                    title="",
                    entities=[],
                    content_hash="",
                    captured_client_ms=job.captured_client_ms,
                    available_server_ms=time.time() * 1000,
                    server_ocr_ms=round(ocr_latency_ms, 2)
                )
                session.current_snapshot = snapshot
                session.state = "ERROR"
                session.history.append(snapshot)
                return

            entities = []
            if ocr_result:
                for item in ocr_result:
                    box, text, score = item[0], item[1].strip(), float(item[2])
                    if score >= 0.6 and len(text) > 1:
                        clean_box = [[round(float(coord), 1) for coord in pt] for pt in box]
                        entities.append({
                            "text": text,
                            "score": round(score, 3),
                            "box": clean_box
                        })

            c_hash = compute_content_hash(entities)
            h_img, w_img = job.frame.shape[:2]
            title = extract_title_heuristic(entities, h_img, w_img)
            status = "READY" if entities else "EMPTY"

            if status == "EMPTY":
                session.slide_counter += 1
                slide_id = session.slide_counter
                slide_revision = 1
            else:
                if (
                    session.current_snapshot
                    and session.current_snapshot.content_hash == c_hash
                    and session.current_snapshot.status == "READY"
                ):
                    slide_id = session.current_snapshot.slide_id
                    slide_revision = session.current_snapshot.slide_revision
                elif session.current_snapshot and is_content_revision(session.current_snapshot.entities, entities):
                    slide_id = session.current_snapshot.slide_id
                    slide_revision = session.current_snapshot.slide_revision + 1
                else:
                    session.slide_counter += 1
                    slide_id = session.slide_counter
                    slide_revision = 1

            session.slide_revision = slide_revision
            snapshot = SlideSnapshot(
                session_id=session.session_id,
                source_epoch=session.source_epoch,
                frame_id=job.frame_id,
                slide_id=slide_id,
                slide_revision=slide_revision,
                status=status,
                title=title,
                entities=entities,
                content_hash=c_hash,
                captured_client_ms=job.captured_client_ms,
                available_server_ms=time.time() * 1000,
                server_ocr_ms=round(ocr_latency_ms, 2)
            )

            session.current_snapshot = snapshot
            session.state = status
            session.last_ocr_hash = c_hash
            session.history.append(snapshot)

            # Update working memory in RAM
            v_entities = [VisualEntity(text=e["text"], score=e["score"], box=e["box"]) for e in entities]
            session.visual_cache.update_slide(
                slide_id=slide_id,
                title=title,
                entities=v_entities
            )

    def wait_for_idle(self, timeout: float = 5.0) -> bool:
        """Waits until worker queue has finished all pending jobs."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._queue_lock:
                if self._job_queue.unfinished_tasks == 0:
                    return True
            time.sleep(0.05)
        return False

    def select_visual_context(
        self,
        session_id: str,
        source_epoch: int = 0,
        segment_end_ms: Optional[float] = None,
        speech_text: str = "",
        min_entity_score: float = 0.85,
        max_entities: int = 20,
        max_chars: int = 1500,
        max_stale_sec: float = 5.0
    ) -> Dict[str, Any]:
        """
        Selects valid, temporally-aligned visual context for translation/correction.
        Enforces Gate Phase 5 criteria:
        - Session isolation and existence
        - Source epoch matching
        - Non-stale heartbeat (<= 5s)
        - Anti-future frame rejection
        - Snapshot READY status
        - Entity score >= min_entity_score (0.85)
        - Keyword relevance matching with bounds (max 20 entities, max 1500 chars)
        """
        with self._sessions_lock:
            if session_id not in self._sessions:
                return {
                    "available": False,
                    "used": False,
                    "visual_context_id": "",
                    "reason": "session_not_found",
                    "slide_title": "",
                    "relevant_entities": [],
                    "matched_entities": []
                }
            session = self._sessions[session_id]

        with session.lock:
            return session.select_visual_context(
                source_epoch=source_epoch,
                segment_end_ms=segment_end_ms,
                speech_text=speech_text,
                min_entity_score=min_entity_score,
                max_entities=max_entities,
                max_chars=max_chars,
                max_stale_sec=max_stale_sec
            )

    def stop(self):
        """Stops background worker thread."""
        self._stopped = True

