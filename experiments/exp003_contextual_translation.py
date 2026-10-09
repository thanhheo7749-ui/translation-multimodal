"""
EXP-003: Context-Aware Adaptive Translation & Sliding Window Revision Simulation
Project: Adaptive Multimodal Online Video Translation (NCKH)
Author: Thanh (MSSV: 2380602051)
Supervisor: ThS. Nguyen Dinh Anh
"""

import sys
import os
import time
import json
import urllib.request
import urllib.parse
import re

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

# The 5 real sentences extracted from Jensen Huang's keynote (EXP-002)
KEYNOTE_SEGMENTS = [
    {
        "id": 1,
        "start": 3.98,
        "end": 13.26,
        "text": "My relationship with you started here and many of you many of you many of my friends and partners here in Taiwan"
    },
    {
        "id": 2,
        "start": 13.72,
        "end": 15.72,
        "text": "Your companies started here"
    },
    {
        "id": 3,
        "start": 17.48,
        "end": 23.68,
        "text": "This is in a lot of ways the beginning of the modern computer industry 40 years now"
    },
    {
        "id": 4,
        "start": 24.60,
        "end": 26.60,
        "text": "And it is 33 years old"
    },
    {
        "id": 5,
        "start": 26.92,
        "end": 29.82,
        "text": "The PC industry was already starting to get the people"
    }
]

def query_translate(text, sl="en", tl="vi"):
    """Query translation endpoint (zero extra dependencies)."""
    clean_text = text.strip()
    if not clean_text:
        return ""
    url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl={sl}&tl={tl}&dt=t&q=" + urllib.parse.quote(clean_text)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            return ''.join([part[0] for part in data[0] if part[0]])
    except Exception as e:
        return f"[Translation Error: {e}]"

def clean_speech_disfluencies(text):
    """Clean spoken disfluencies such as stuttering or repeated words."""
    # e.g. "many of you many of you" -> "many of you"
    words = text.split()
    cleaned = []
    # Simple ngram deduplication
    cleaned_text = re.sub(r'\b(\w+(?:\s+\w+){1,3})\s+\1\b', r'\1', text, flags=re.IGNORECASE)
    return cleaned_text

def has_connector_or_pronoun(text):
    """Check if the sentence starts with a coordinating connector or dangling pronoun."""
    stripped = text.strip().lower()
    connectors = ["and ", "but ", "or ", "so ", "because ", "which ", "that ", "where ", "it is ", "they are "]
    for c in connectors:
        if stripped.startswith(c):
            return True, c.strip()
    return False, ""

def simulate_streaming_translation():
    print("=" * 75)
    print(" THỰC NGHIỆM EXP-003: MÔ PHỎNG DỊCH THÍCH ỨNG CÓ MỞ RỘNG NGỮ CẢNH (ADAPTIVE REVISION)")
    print(" Dữ liệu kiểm thử: 5 câu khẩu ngữ thực tế của Jensen Huang (GTC Taipei Keynote)")
    print("=" * 75)

    print("\n--- PHẦN 1: DỊCH ĐƠN LẺ TỪNG CÂU (BASELINE AUDIO-ONLY, KHÔNG NGỮ CẢNH) ---")
    baseline_results = []
    for seg in KEYNOTE_SEGMENTS:
        t0 = time.perf_counter()
        raw_vi = query_translate(seg['text'])
        lat = (time.perf_counter() - t0) * 1000
        baseline_results.append({
            "id": seg['id'],
            "en": seg['text'],
            "vi_isolated": raw_vi,
            "latency_ms": round(lat, 1)
        })
        print(f"\n[Câu {seg['id']}] ({seg['start']}s -> {seg['end']}s)")
        print(f"  EN gốc   : \"{seg['text']}\"")
        print(f"  VI đơn lẻ: \"{raw_vi}\" (Độ trễ: {lat:.1f}ms)")

    print("\n" + "=" * 75)
    print("--- PHẦN 2: DỊCH THÍCH ỨNG THEO Ý TƯỞNG CỦA BẠN (STREAMING + SLIDING WINDOW + REVISION) ---")
    print("Cơ chế:")
    print("1. Pha 1 (First-pass): Nghe xong 1 câu -> Dịch ngay hiển thị sơ bộ để không trễ.")
    print("2. Pha 2 (Sliding Context): Tích lũy 3-4 câu trong bộ nhớ đệm.")
    print("3. Pha 3 (Revision): Nếu phát hiện câu sau bắt đầu bằng từ nối ('And', 'Which', 'Because')")
    print("   hoặc đại từ ám chỉ ('it'), kích hoạt hợp nhất ngữ cảnh và CẬP NHẬT LẠI bản dịch câu trước!\n")

    history = []
    adaptive_log = []
    
    for seg in KEYNOTE_SEGMENTS:
        seg_id = seg['id']
        raw_en = seg['text']
        cleaned_en = clean_speech_disfluencies(raw_en)
        
        print(f">>> [T={seg['end']:05.2f}s] Nhận câu #{seg_id}: \"{raw_en}\"")
        
        # 1. First-pass provisional translation (Độ trễ tối thiểu)
        t_first_start = time.perf_counter()
        first_pass_vi = query_translate(cleaned_en)
        t_first = (time.perf_counter() - t_first_start) * 1000
        
        print(f"    [Pha 1 - Hiển thị tức thì]: \"{first_pass_vi}\" ({t_first:.1f}ms)")

        # 2. Check connector / dependent clause
        is_dependent, keyword = has_connector_or_pronoun(raw_en)
        
        if is_dependent and len(history) > 0:
            prev_seg = history[-1]
            print(f"    [Phát hiện nối nghĩa!]: Câu #{seg_id} bắt đầu bằng từ nối/đại từ '{keyword}' phụ thuộc Câu #{prev_seg['id']}!")
            
            # Kết hợp câu trước + câu hiện tại để dịch hoàn chỉnh
            combined_en = f"{prev_seg['cleaned_en']}. {cleaned_en}"
            t_rev_start = time.perf_counter()
            revised_combined_vi = query_translate(combined_en)
            t_rev = (time.perf_counter() - t_rev_start) * 1000
            
            print(f"    [Pha 3 - Sửa câu trước & Hợp nhất nghĩa]:")
            print(f"      -> Câu trước chưa sửa: \"{prev_seg['provisional_vi']}\"")
            print(f"      -> Câu sau đơn lẻ   : \"{first_pass_vi}\"")
            print(f"      => BẢN DỊCH HỢP NHẤT MỚI: \"{revised_combined_vi}\" (Cập nhật sau {t_rev:.1f}ms)")
            
            adaptive_log.append({
                "id": seg_id,
                "status": "REVISED_WITH_PREVIOUS",
                "trigger_word": keyword,
                "combined_en": combined_en,
                "revised_vi": revised_combined_vi
            })
        else:
            adaptive_log.append({
                "id": seg_id,
                "status": "PROVISIONAL_COMMITTED",
                "first_pass_vi": first_pass_vi
            })

        history.append({
            "id": seg_id,
            "raw_en": raw_en,
            "cleaned_en": cleaned_en,
            "provisional_vi": first_pass_vi
        })
        time.sleep(0.3)

    # Output summary comparison
    print("\n" + "=" * 75)
    print(" BẢNG ĐỐI CHỨNG HIỆU QUẢ CƠ CHẾ SỬA CÂU THÍCH ỨNG")
    print("=" * 75)
    print("Trường hợp Câu #3 + Câu #4:")
    print("  * Câu #3 EN: \"This is in a lot of ways the beginning of the modern computer industry 40 years now\"")
    print("  * Câu #4 EN: \"And it is 33 years old\"")
    print("-" * 75)
    print("  [Cũ - Dịch rời rạc]:")
    print(f"    - Câu 3: \"{baseline_results[2]['vi_isolated']}\"")
    print(f"    - Câu 4: \"{baseline_results[3]['vi_isolated']}\"  <-- 'nó' tối nghĩa, không rõ nghĩa.")
    print("-" * 75)
    print("  [Mới - Dịch thích ứng sửa câu]:")
    for log in adaptive_log:
        if log.get("status") == "REVISED_WITH_PREVIOUS":
            print(f"    => Bản dịch cập nhật hoàn chỉnh: \"{log['revised_vi']}\"")
    print("=" * 75)

    # Save results to json
    out_path = "experiments/results_exp003.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "experiment_id": "EXP-003",
            "baseline": baseline_results,
            "adaptive": adaptive_log
        }, f, ensure_ascii=False, indent=2)
    print(f"[+] Kết quả thực nghiệm đã ghi vào: {out_path}")

if __name__ == "__main__":
    simulate_streaming_translation()
