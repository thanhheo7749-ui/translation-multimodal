"""
EXP-004: Visual Working Memory & Slide OCR Entity Extraction Benchmark
Project: Adaptive Multimodal Online Video Translation (NCKH)
Author: Thanh (MSSV: 2380602051)
Supervisor: ThS. Nguyen Dinh Anh
"""

import sys
import os
import time
import json
import numpy as np
from PIL import Image
from rapidocr_onnxruntime import RapidOCR

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

FRAME_PATH = r"data/annotations/frame_120s.jpg"
RESULTS_PATH = r"experiments/results_exp004.json"

class VisualWorkingMemory:
    """
    Proactive Visual Working Memory (Bộ nhớ đệm thị giác chủ động).
    Indexes slide text and technical entities upon slide change.
    Provides ~0ms retrieval latency during subsequent speech translation.
    """
    def __init__(self):
        t0 = time.perf_counter()
        # Initialize RapidOCR (PaddleOCR ONNX engine)
        self.engine = RapidOCR()
        self.init_time_ms = (time.perf_counter() - t0) * 1000
        self.current_slide_entities = []
        self.current_slide_title = ""
        self.indexed_keywords = set()

    def process_slide_frame(self, image_path):
        """Perform OCR and index entities into RAM."""
        t_ocr_start = time.perf_counter()
        result, elapse_list = self.engine(image_path)
        t_ocr_total = (time.perf_counter() - t_ocr_start) * 1000

        detected_items = []
        self.indexed_keywords.clear()
        
        if result:
            for item in result:
                box, text, score = item[0], item[1].strip(), float(item[2])
                if score >= 0.6 and len(text) > 1:
                    detected_items.append({
                        "text": text,
                        "score": round(score, 3),
                        "box": box
                    })
                    # Index words for fast lookup
                    for word in text.split():
                        self.indexed_keywords.add(word.lower())

        # Determine Title (usually near top) and Technical entities
        title_candidates = [it['text'] for it in detected_items if "reinvent" in it['text'].lower() or "nvidia" in it['text'].lower()]
        self.current_slide_title = title_candidates[0] if title_candidates else (detected_items[0]['text'] if detected_items else "")
        self.current_slide_entities = detected_items

        return {
            "ocr_latency_ms": round(t_ocr_total, 1),
            "engine_elapse": elapse_list,
            "total_detected": len(detected_items),
            "items": detected_items,
            "title": self.current_slide_title
        }

    def retrieve_context_for_speech(self, speech_text):
        """Retrieve relevant visual entities matching speech text (Latency in RAM: <1ms)."""
        t0 = time.perf_counter()
        speech_words = set(speech_text.lower().split())
        matched = []
        
        for item in self.current_slide_entities:
            item_text = item['text']
            item_words = set(item_text.lower().split())
            # Check overlap or entity relevance
            if speech_words.intersection(item_words) or any(w in speech_text.lower() for w in item_words):
                matched.append(item_text)
                
        retrieval_ms = (time.perf_counter() - t0) * 1000
        return matched, round(retrieval_ms, 3)

def run_experiment():
    print("=" * 75)
    print(" THỰC NGHIỆM EXP-004: TRÍCH XUẤT THỰC THỂ SLIDE (VISUAL WORKING MEMORY)")
    print(f" Khung hình thực tế: {FRAME_PATH} (Jensen Huang GTC Taipei Keynote @ 120s)")
    print("=" * 75)

    # 1. Initialize Visual Memory
    print("[1] Khởi tạo Bộ nhớ đệm Thị giác (RapidOCR ONNX Engine)...")
    vwm = VisualWorkingMemory()
    print(f"[+] Thời gian nạp Engine vào bộ nhớ: {vwm.init_time_ms:.1f} ms")

    # 2. Process Slide Frame
    print(f"\n[2] Đang quét OCR khung hình slide thuyết trình ({FRAME_PATH})...")
    ocr_result = vwm.process_slide_frame(FRAME_PATH)
    
    print(f"[+] Tốc độ đọc slide OCR hoàn tất: {ocr_result['ocr_latency_ms']} ms")
    print(f"    - Thời gian chi tiết (Det / Cls / Rec): {ocr_result['engine_elapse']}")
    print(f"[+] Số lượng thực thể/văn bản phát hiện: {ocr_result['total_detected']}")
    print(f"[+] Tiêu đề slide phát hiện: \"{ocr_result['title']}\"")
    
    print("\n--- DANH MỤC THỰC THỂ ĐÃ ĐƯỢC CHỈ MỤC VÀO BỘ NHỚ RAM ---")
    for idx, item in enumerate(ocr_result['items'], 1):
        print(f"  {idx:02d}. [{item['score']*100:.1f}%] \"{item['text']}\"")

    # 3. Simulate Speech Matching & Visual Context Injection
    print("\n" + "=" * 75)
    print("--- PHẦN 3: MÔ PHỎNG LIÊN KẾT ÂM THANH - HÌNH ẢNH TRONG THỜI GIAN THỰC ---")
    
    test_speeches = [
        "Microsoft NVIDIA over the last three years, it took this long to completely reinvent how the PC is going to work",
        "We are running local LLM models like DeepSeek, Gemma, and Qwen",
        "that compute pattern called the agent is going to connect with OpenShell"
    ]

    context_injections = []
    for sp in test_speeches:
        matched_entities, ret_ms = vwm.retrieve_context_for_speech(sp)
        print(f"\n* Lời nói Jensen: \"{sp}\"")
        print(f"  -> Tra cứu Visual Memory (RAM): {ret_ms} ms (Gần như bằng 0ms!)")
        print(f"  -> Thực thể hình ảnh khớp được: {matched_entities}")
        
        # Build Augmented Prompt
        augmented_prompt = f"[Visual Context: {', '.join(matched_entities)}] {sp}" if matched_entities else sp
        print(f"  => Câu đưa vào dịch có bổ trợ Visual: \"{augmented_prompt}\"")
        
        context_injections.append({
            "speech": sp,
            "matched_entities": matched_entities,
            "retrieval_latency_ms": ret_ms,
            "augmented_prompt": augmented_prompt
        })

    # 4. Save results to JSON
    summary = {
        "experiment_id": "EXP-004",
        "slide_frame": FRAME_PATH,
        "engine": "RapidOCR ONNX (PaddleOCR architecture)",
        "metrics": {
            "init_time_ms": round(vwm.init_time_ms, 1),
            "ocr_slide_latency_ms": ocr_result['ocr_latency_ms'],
            "budget_target_ms": 150,
            "within_budget": bool(ocr_result['ocr_latency_ms'] <= 150),
            "total_entities_extracted": ocr_result['total_detected']
        },
        "extracted_items": ocr_result['items'],
        "speech_context_injections": context_injections
    }

    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 75)
    print(f"[+] Kết quả thực nghiệm EXP-004 đã được lưu vào: {RESULTS_PATH}")
    print("=" * 75)

if __name__ == "__main__":
    run_experiment()
