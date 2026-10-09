# 01. Hardware Specifications & Resource Budget

## 1. Mục tiêu tài liệu
Tài liệu này xác lập các giới hạn cứng (Hard Constraints) về phần cứng, bộ nhớ đồ họa (VRAM), và ngân sách độ trễ (Latency Budget) cho hệ thống dịch video trực tuyến đa phương thức thích ứng, đảm bảo toàn bộ pipeline vận hành ổn định trên card đồ họa **NVIDIA GeForce RTX 3050**.

---

## 2. Thông số phần cứng đích (Target Hardware Profile)

* **GPU:** NVIDIA GeForce RTX 3050
  * **Kiến trúc:** Ampere (Compute Capability 8.6)
  * **VRAM khả dụng:** 4.096 MB – 6.144 MB (tùy phiên bản Laptop/Desktop)
  * **Hỗ trợ tính toán:** Tensor Cores, FP16, INT8, BF16
* **CPU đề xuất:** 6 cores / 12 threads trở lên (Intel Core i5 Gen 11+ hoặc AMD Ryzen 5 5000+)
* **RAM hệ thống:** 16 GB DDR4/DDR5
* **Hệ điều hành:** Windows 11 / Ubuntu Linux (WSL2 supported)

---

## 3. Ngân sách bộ nhớ đồ họa (VRAM Allocation Matrix)

Để tránh hiện tượng tràn bộ nhớ đồ họa (CUDA Out of Memory - OOM), tổng dung lượng phân bổ tĩnh cho các module không được vượt quá **3.800 MB** (đối với bản 4GB) hoặc **5.200 MB** (đối với bản 6GB):

| Module | Công nghệ / Mô hình | Định dạng tính toán | VRAM dự kiến | Mục tiêu thời gian |
| :--- | :--- | :--- | :--- | :--- |
| **ASR Streaming** | Faster-Whisper (`small.en` hoặc `base.en`) | FP16 / INT8 (CTranslate2) | ~1.100 MB | 200 ms – 300 ms |
| **Vision & OCR** | PaddleOCR (Det + Rec) | FP16 / TensorRT ONNX | ~450 MB | 50 ms – 70 ms (chỉ chạy khi đổi slide) |
| **Adaptive Controller** | Feature-based Rule / Tiny Scoring | CPU / Memory | ~20 MB | < 5 ms |
| **Translation Engine** | Qwen2.5-1.5B-Instruct (Local) / Cloud API | INT4 / AWQ hoặc vLLM Cloud | ~1.600 MB (nếu chạy local) | 250 ms – 350 ms |
| **VRAM Buffer & OS** | Bộ nhớ đệm biến thiên CUDA | - | ~600 MB | Phòng ngừa giật spike |
| **TỔNG CỘNG** | **Toàn bộ hệ thống** | **Phối hợp đa tầng** | **~3.770 MB** | **Tổng trễ: ~1.000 ms – 1.200 ms** |

---

## 4. Ngân sách độ trễ luồng trực tiếp (Simultaneous Latency Budget)

Hệ thống tuân thủ nghiêm ngặt chuẩn dịch cabin quốc tế: **Tổng độ trễ không vượt quá 1.500 mili-giây (1.5 giây)**.

```text
[0 ms]  Âm thanh phát ra từ video
  │
  ├── [0 - 300 ms]    : Thu âm đoạn nói (Audio chunk 300ms)
  ├── [300 - 550 ms]  : Nhận diện giọng nói (WhisperLive ASR - tốn 250ms)
  ├── [550 - 555 ms]  : Bộ điều khiển quét điều kiện & tra cứu Visual Cache (tốn 5ms)
  ├── [555 - 900 ms]  : Mô hình ngôn ngữ dịch sang tiếng Việt (LLM Translation - tốn 345ms)
  └── [900 - 950 ms]  : Đẩy phụ đề qua WebSocket lên Web Dashboard (tốn 50ms)
  │
[950 ms] Phụ đề tiếng Việt xuất hiện trên màn hình! (Dư 550 ms so với giới hạn 1.500 ms)
```

---

## 5. Quy tắc Hạn chót cứng (Hard Deadline Fallback Rule)
* Mọi tác vụ liên quan đến hình ảnh (chụp frame, OCR) tuyệt đối **không được làm nghẽn luồng âm thanh**.
* Nếu tại bất kỳ thời điểm nào việc xử lý OCR hoặc Vision vượt quá **150 mili-giây**, hệ thống phải lập tức kích hoạt cơ chế `DROP_VISION_FALLBACK` và dịch ngay bằng Audio-only để đảm bảo luồng phụ đề không bao giờ bị đứng hình.
