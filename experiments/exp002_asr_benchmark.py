"""
EXP-002: ASR Streaming Latency & VRAM Benchmark on NVIDIA RTX 3050 Laptop GPU
Project: Adaptive Multimodal Online Video Translation (NCKH)
Author: Thanh (MSSV: 2380602051)
Supervisor: ThS. Nguyen Dinh Anh
"""

import sys
import os
import time
import subprocess
import json
import numpy as np
import av
from faster_whisper import WhisperModel

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

VIDEO_PATH = r"data/raw_videos/YTSave_YouTube_Media_11Y3B33oCLE_Announcing-NVIDIA-RTX-Spark-GTC-Taipei-2026-Keynote-by-CEO-Jensen-Huang_003_480p.mp4"
OUTPUT_RESULT_PATH = r"experiments/results_exp002.json"

def get_vram_mb():
    """Query current used VRAM in MB via nvidia-smi."""
    try:
        res = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            encoding="utf-8"
        )
        return int(res.strip())
    except Exception:
        return -1

def decode_audio_slice(video_path, start_sec=0, duration_sec=30, sample_rate=16000):
    """Decode audio slice to float32 16kHz mono numpy array."""
    print(f"[*] Decoding {duration_sec}s audio from {video_path} (from {start_sec}s)...")
    container = av.open(video_path)
    stream = container.streams.audio[0]
    resampler = av.AudioResampler(format='fltp', layout='mono', rate=sample_rate)

    target_samples = int(duration_sec * sample_rate)
    samples = []
    
    # Seek close to start_sec
    if start_sec > 0:
        container.seek(int(start_sec * av.time_base))

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
    audio = np.concatenate(samples)[:target_samples]
    return audio

def benchmark_asr(model_size="base.en", compute_type="float16", duration_sec=45):
    print("=" * 70)
    print(f" THỰC NGHIỆM EXP-002: ĐO ĐẠC FASTER-WHISPER ({model_size.upper()}) TRÊN RTX 3050")
    print("=" * 70)

    vram_before = get_vram_mb()
    print(f"[1] VRAM ban đầu của hệ thống: {vram_before} MB")

    # 1. Load Model
    t_load_start = time.perf_counter()
    print(f"[*] Đang khởi tạo mô hình '{model_size}' trên CUDA ({compute_type})...")
    model = WhisperModel(
        model_size,
        device="cuda",
        device_index=0,
        compute_type=compute_type,
        cpu_threads=4
    )
    t_load = (time.perf_counter() - t_load_start) * 1000
    vram_after_load = get_vram_mb()
    vram_model = vram_after_load - vram_before if vram_before >= 0 else -1

    print(f"[+] Thời gian tải mô hình vào GPU: {t_load:.1f} ms")
    print(f"[+] VRAM sau khi tải mô hình: {vram_after_load} MB (Mô hình chiếm ~{vram_model} MB VRAM)")

    # 2. Extract Audio (First 45 seconds of Jensen Huang's keynote)
    audio = decode_audio_slice(VIDEO_PATH, start_sec=10, duration_sec=duration_sec)
    audio_dur = len(audio) / 16000
    print(f"[+] Audio trích xuất thành công: {audio_dur:.2f} giây ({len(audio)} mẫu)")

    # 3. Test 1: VAD-guided Sentence Segmentation Transcription
    print("\n--- TEST 1: Nhận dạng phân đoạn câu bằng Silero-VAD ---")
    t_infer_start = time.perf_counter()
    segments, info = model.transcribe(
        audio,
        beam_size=3,
        language="en",
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=400)
    )
    
    recognized_segments = []
    seg_latencies = []
    for s in segments:
        t_seg_end = time.perf_counter()
        seg_duration = s.end - s.start
        recognized_segments.append({
            "id": s.id,
            "start": round(s.start, 2),
            "end": round(s.end, 2),
            "text": s.text.strip(),
            "avg_logprob": round(s.avg_logprob, 3),
            "no_speech_prob": round(s.no_speech_prob, 3)
        })
        print(f"  [{s.start:05.2f}s -> {s.end:05.2f}s] {s.text.strip()}")

    t_total_infer = (time.perf_counter() - t_infer_start) * 1000
    rtf = (t_total_infer / 1000) / audio_dur  # Real Time Factor

    print(f"\n[+] Tổng thời gian xử lý {audio_dur:.1f}s âm thanh: {t_total_infer:.1f} ms ({t_total_infer/1000:.2f}s)")
    print(f"[+] Real-Time Factor (RTF): {rtf:.4f} (Xử lý nhanh gấp {1.0/rtf:.1f}x so với thời gian thực!)")
    print(f"[+] Ngôn ngữ phát hiện: {info.language} (Xác suất: {info.language_probability:.2%})")

    # 4. Test 2: Chunk-level streaming latency simulation (2.0s chunks)
    print("\n--- TEST 2: Đo độ trễ Streaming theo từng Chunk (2.0s / chunk) ---")
    chunk_size = 16000 * 2  # 2 seconds
    chunk_times = []
    num_chunks = min(5, len(audio) // chunk_size)
    for i in range(num_chunks):
        c_audio = audio[i * chunk_size : (i + 1) * chunk_size]
        t0 = time.perf_counter()
        c_segs, _ = model.transcribe(c_audio, beam_size=1, vad_filter=False)
        c_text = " ".join([seg.text.strip() for seg in c_segs])
        t_elapsed = (time.perf_counter() - t0) * 1000
        chunk_times.append(t_elapsed)
        print(f"  * Chunk #{i+1} (2.0s audio): Độ trễ xử lý = {t_elapsed:.1f} ms | Nhận diện: \"{c_text}\"")

    avg_chunk_lat = np.mean(chunk_times) if chunk_times else 0
    p95_chunk_lat = np.percentile(chunk_times, 95) if chunk_times else 0
    print(f"\n[+] Độ trễ trung bình mỗi 2.0s chunk: {avg_chunk_lat:.1f} ms (P95: {p95_chunk_lat:.1f} ms)")
    
    # 5. Compile Results
    results = {
        "experiment_id": "EXP-002",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "model_name": f"faster-whisper-{model_size}",
        "device": "NVIDIA GeForce RTX 3050 Laptop GPU (6GB)",
        "compute_type": compute_type,
        "vram_metrics": {
            "vram_baseline_mb": vram_before,
            "vram_peak_mb": vram_after_load,
            "vram_model_footprint_mb": vram_model
        },
        "latency_metrics": {
            "audio_duration_sec": audio_dur,
            "total_inference_ms": round(t_total_infer, 1),
            "real_time_factor": round(rtf, 4),
            "speedup_vs_realtime": round(1.0 / rtf, 1),
            "avg_chunk_latency_ms": round(avg_chunk_lat, 1),
            "p95_chunk_latency_ms": round(p95_chunk_lat, 1)
        },
        "contract_budget_check": {
            "target_budget_ms": 300,
            "achieved_avg_latency_ms": round(avg_chunk_lat, 1),
            "budget_satisfied": bool(avg_chunk_lat <= 300)
        },
        "sample_transcriptions": recognized_segments
    }

    with open(OUTPUT_RESULT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n[+] Kết quả chi tiết đã được lưu vào: {OUTPUT_RESULT_PATH}")
    print("=" * 70)
    return results

if __name__ == "__main__":
    benchmark_asr()
