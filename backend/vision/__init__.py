"""
Vision subsystem for slide transition detection and automated entity extraction.
"""
from backend.vision.scene_detector import SlideTransitionDetector
from backend.vision.slide_pipeline import SlideVisionPipeline
from backend.vision.live_vision_service import LiveVisionService, SlideSnapshot, SessionVisionState

__all__ = [
    "SlideTransitionDetector",
    "SlideVisionPipeline",
    "LiveVisionService",
    "SlideSnapshot",
    "SessionVisionState"
]

