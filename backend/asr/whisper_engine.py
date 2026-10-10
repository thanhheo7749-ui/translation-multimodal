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
if sys.platform != "win32":
    # Auto-discover nvidia cuda library paths if installed in site-packages
    nvidia_dirs = []
    for pkg_dir in ("/opt/conda/lib/python3.11/site-packages/nvidia", "/usr/local/lib/python3.11/dist-packages/nvidia"):
        if os.path.isdir(pkg_dir):
            for sub in os.listdir(pkg_dir):
                lib_path = os.path.join(pkg_dir, sub, "lib")
                if os.path.isdir(lib_path):
                    nvidia_dirs.append(lib_path)
    if nvidia_dirs:
        current_ld = os.environ.get("LD_LIBRARY_PATH", "")
        os.environ["LD_LIBRARY_PATH"] = ":".join(nvidia_dirs) + (":" + current_ld if current_ld else "")

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
        model_size = os.getenv("WHISPER_MODEL", model_size)
        pref_device = os.getenv("WHISPER_DEVICE", "auto").strip().lower()

        device = "cpu"
        compute_type = "int8"
        if pref_device in ("cuda", "auto"):
            try:
                import ctranslate2
                if ctranslate2.get_cuda_device_count() > 0:
                    device = "cuda"
                    compute_type = os.getenv("WHISPER_COMPUTE_TYPE", "float16")
            except Exception as e:
                device = "cpu"
                compute_type = "int8"
        if pref_device == "cpu":
            device = "cpu"
            compute_type = "int8"

        self.device = device
        self.compute_type = compute_type
        self.beam_size = int(os.getenv("WHISPER_BEAM_SIZE", "1"))

        print(f"[*] Đang khởi tạo LiveWhisperEngine (Model: {model_size}, Device: {device}, Type: {compute_type}, Beam: {self.beam_size})...")
        t0 = time.perf_counter()
        self.model = WhisperModel(
            model_size,
            device=device,
            compute_type=compute_type,
            cpu_threads=4,
            local_files_only=os.getenv("ALLOW_MODEL_DOWNLOAD", "0") != "1"
        )
        self._inference_lock = threading.Lock()
        self.init_time_ms = (time.perf_counter() - t0) * 1000
        print(f"[✓] LiveWhisperEngine sẵn sàng trong {self.init_time_ms:.1f}ms (Device: {device})")

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
            segments, _ = self.model.transcribe(audio, beam_size=getattr(self, 'beam_size', 1), temperature=0, language="en",
                word_timestamps=True, vad_filter=True, condition_on_previous_text=False)
            rows = [{"text": s.text.strip(), "start": float(s.start), "end": float(s.end),
                "words": [{"text": w.word.strip(), "start": float(w.start), "end": float(w.end)} for w in (getattr(s, 'words', None) or [])]}
                for s in segments if s.text.strip()]
        device = getattr(self, 'device', 'cpu')
        compute_type = getattr(self, 'compute_type', 'int8')
        beam_size = getattr(self, 'beam_size', 1)
        return {"text": " ".join(r["text"] for r in rows), "segments": rows,
            "words": [w for r in rows for w in r["words"]],
            "asr_latency_ms": round((time.perf_counter()-started)*1000, 1),
            "audio_duration_sec": len(audio)/16000,
            "model": f"base.en {device} {compute_type} (beam {beam_size})"}
