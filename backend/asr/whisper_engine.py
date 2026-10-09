"""
Live Whisper Streaming Engine using faster-whisper.
Runs CPU int8 with multi-threading; latency is measured for each input.
Zero hardcoded data - decodes real audio and transcribes on-the-fly.
"""

import os
import sys
import time
import threading
import av
import numpy as np

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
from typing import List, Dict, Any, Optional
from faster_whisper import WhisperModel

class LiveWhisperEngine:
    _instance = None
    _instance_lock = threading.Lock()

    @classmethod
    def get_instance(cls, model_size: str = "base.en"):
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls(model_size=model_size)
        return cls._instance

    def __init__(self, model_size: str = "base.en"):
        print(f"[*] Đang khởi tạo LiveWhisperEngine (Model: {model_size}, CPU int8, 4 threads)...")
        t0 = time.perf_counter()
        self.model = WhisperModel(
            model_size,
            device="cpu",
            compute_type="int8",
            cpu_threads=4,
            local_files_only=True
        )
        self._inference_lock = threading.Lock()
        self.init_time_ms = (time.perf_counter() - t0) * 1000
        print(f"[✓] LiveWhisperEngine sẵn sàng trong {self.init_time_ms:.1f}ms")

    def decode_audio_slice(self, video_path: str, start_sec: float = 0.0, duration_sec: float = 10.0, sample_rate: int = 16000) -> np.ndarray:
        """Decode a specific time slice from a video or audio file into 16kHz float32 mono array."""
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")

        container = av.open(video_path)
        stream = container.streams.audio[0]
        resampler = av.AudioResampler(format='fltp', layout='mono', rate=sample_rate)

        target_samples = int(duration_sec * sample_rate)
        samples = []

        if start_sec > 0:
            # Seek container to approximate position
            seek_pts = int(start_sec / stream.time_base)
            container.seek(seek_pts, stream=stream)

        current_samples = 0
        for frame in container.decode(stream):
            frame.pts = None
            for rf in resampler.resample(frame):
                arr = rf.to_ndarray()[0]
                samples.append(arr)
                current_samples += len(arr)
            if current_samples >= target_samples:
                break

        container.close()
        if not samples:
            return np.zeros(target_samples, dtype=np.float32)

        audio = np.concatenate(samples)[:target_samples]
        return audio

    def transcribe_slice(self, video_path: str, start_sec: float = 0.0, duration_sec: float = 10.0) -> List[Dict[str, Any]]:
        """
        Transcribe audio slice with real faster-whisper model.
        Returns recognized segments with word-level timestamps and measured latency.
        """
        t0 = time.perf_counter()
        audio = self.decode_audio_slice(video_path, start_sec=start_sec, duration_sec=duration_sec)
        decode_ms = (time.perf_counter() - t0) * 1000

        t1 = time.perf_counter()
        with self._inference_lock:
            segments_gen, info = self.model.transcribe(
                audio,
                beam_size=1,
                word_timestamps=True,
                language="en"
            )
        
            results = []
            for s in segments_gen:
                words = []
                if s.words:
                    for w in s.words:
                        words.append({
                            "word": w.word.strip(),
                            "start": round(start_sec + float(w.start), 2),
                            "end": round(start_sec + float(w.end), 2),
                            "probability": round(float(w.probability), 3)
                        })
            
                clean_text = s.text.strip()
                if clean_text:
                    results.append({
                        "start": round(start_sec + float(s.start), 2),
                        "end": round(start_sec + float(s.end), 2),
                        "text": clean_text,
                        "words": words
                    })

        infer_ms = (time.perf_counter() - t1) * 1000
        total_asr_ms = decode_ms + infer_ms

        for r in results:
            r["asr_latency_ms"] = round(total_asr_ms, 1)

        return results

    def transcribe_pcm(self, pcm_bytes: bytes) -> Dict[str, Any]:
        """Transcribe only the received 16kHz mono PCM block, never future audio."""
        if len(pcm_bytes) < 3200 or len(pcm_bytes) > 16000 * 2 * 12 or len(pcm_bytes) % 2:
            raise ValueError("PCM must contain 0.1–12s of 16kHz mono int16 audio")
        audio = np.frombuffer(pcm_bytes, dtype="<i2").astype(np.float32) / 32768.0
        started = time.perf_counter()
        with self._inference_lock:
            segments, _ = self.model.transcribe(audio, beam_size=5, temperature=0, language="en",
                word_timestamps=True, vad_filter=True, condition_on_previous_text=False)
            rows = [{"text": s.text.strip(), "start": float(s.start), "end": float(s.end),
                "words": [{"text": w.word.strip(), "start": float(w.start), "end": float(w.end)} for w in (getattr(s, 'words', None) or [])]}
                for s in segments if s.text.strip()]
        return {"text": " ".join(r["text"] for r in rows), "segments": rows,
            "words": [w for r in rows for w in r["words"]],
            "asr_latency_ms": round((time.perf_counter()-started)*1000, 1),
            "audio_duration_sec": len(audio)/16000, "model": "base.en CPU int8"}
