"""
Vision subsystem for slide transition detection and automated entity extraction.
"""
from backend.vision.scene_detector import SlideTransitionDetector
from backend.vision.slide_pipeline import SlideVisionPipeline

__all__ = [
    "SlideTransitionDetector",
    "SlideVisionPipeline"
]
