# Translation Multimodal — chạy bằng Docker

## Khởi động

Mở Docker Desktop (Linux containers, WSL2), rồi chạy **`studio.cmd`**.
Trang web: **http://localhost:8004/live**. Trang thử một câu: http://localhost:8004/translation-test.
Một container phục vụ giao diện, nhận dạng tiếng Anh và dịch tiếng Việt; không cần bật frontend/backend riêng.
Đã có [báo cáo so sánh thực tế local/API](docs/LOCAL_API_COMPARISON.md).

```powershell
.\studio.cmd          # build khi mã nguồn thay đổi, chạy nền và mở trình duyệt
.\studio.cmd stop     # dừng, giữ model và dữ liệu
.\studio.cmd logs     # xem log
.\studio.cmd diagnose # kiểm tra HTTPS, không gửi API key
```

Máy cần NVIDIA GPU và Docker Desktop hỗ trợ GPU qua WSL2. Lần đầu tải image CUDA/PyTorch,
model NLLB và Whisper (nhiều GB); thời gian nạp/tải này không phải tốc độ dịch sau warmup.
Model giữ trong `models/`, video giữ trong `data/`, log trong `experiments/runtime_logs/`.
Lần nạp NLLB đã đo mất khoảng 54–63 giây; chờ trang báo sẵn sàng trước khi bắt đầu video.
Không chạy `docker compose down -v` để dọn dữ liệu. Port 8004 tách khỏi server Gemini 8003 dùng đối chiếu.

Mặc định dùng **local NLLB-200 distilled 600M trên GPU**, nhận dạng **Whisper base.en CPU int8**.
Local chỉ dịch văn bản Anh–Việt; chưa sử dụng ngữ cảnh OCR hoặc tự hiệu chỉnh bằng API.
Giao diện sẽ nạp model trước khi cho bắt đầu thu âm. Không có bản dịch giả khi thiếu model.
Video NVIDIA hiện có được mount vào container. Chọn video trên trang để xử lý âm thanh theo lúc phát.
Phần hiệu chỉnh local bằng API và bộ phát hình–tiếng có độ trễ theo kế hoạch trước chưa được tích hợp.
Hai test `test_delayed_playback_js.cjs` và `test_subtitle_scheduler_js.cjs` vẫn là test cho phần chưa triển khai;
không coi việc đóng gói Docker là đã giải quyết xong độ trễ phụ đề đầu cuối.

## Đối chiếu local và Gemini

Chạy lệnh dưới đây và nhập khóa Gemini trong terminal (ký tự nhập được ẩn):

```powershell
.\studio.cmd test
```

Phép thử dùng cùng sáu đoạn tiếng Anh từ video NVIDIA, thứ tự ngẫu nhiên cố định, ba lượt lặp,
warmup riêng; ghi thời gian, lỗi và bản dịch vào `experiments/local_comparison/<thời điểm>/`.
Không cần bật server API riêng. Benchmark dùng cùng adapter Gemini với website, gọi HTTPS trực tiếp.
Khóa nhập chỉ tồn tại trong tiến trình container test, không lưu vào mã nguồn/báo cáo.
Lệnh test tạm dừng container local để tránh hai bản model tranh GPU, rồi khởi động lại khi đo xong.
Đây là phép đo **dịch văn bản**, không phải độ trễ ASR/phụ đề trực tiếp hay chứng nhận chất lượng dịch.
Nếu không có khóa hoặc provider lỗi, báo cáo ghi rõ và lệnh trả mã lỗi; không tự thay bằng Google demo.
Nếu bạn ngắt test giữa chừng, chạy lại `studio.cmd` để mở web.

Đổi beam size để đo thêm tốc độ/chất lượng:

```powershell
docker compose run --rm --no-deps studio python experiments/compare_local_translation.py --providers both --download --beam-size 1 --gemini-direct --prompt-key
```

## Chạy Gemini thay cho local

Chạy `studio.cmd gemini` và nhập khóa ẩn trong terminal. Hoặc truyền `TRANSLATION_PROVIDER=gemini`
và `GEMINI_API_KEY` từ môi trường PowerShell rồi chạy `studio.cmd`.
Không đưa khóa vào mã nguồn hoặc Git. Model mặc định giữ nguyên cấu hình hiện có: `gemini-3.5-flash-lite`.
Container nhận biến môi trường khi được tạo; thay cấu hình cần chạy lại `studio.cmd`.
Để về local: chạy lại `studio.cmd`. Nếu đã đặt biến môi trường provider, đặt
`$env:TRANSLATION_PROVIDER='local'` trước.

## Cấu trúc và dọn file

- `backend/`, `frontend/`: ứng dụng.
- `experiments/`, `tests/`: phép đo và kiểm thử; giữ kết quả để đối chiếu nghiên cứu.
- `docs/`, `research/`: tài liệu, kế hoạch.
- `Dockerfile`, `compose.yaml`, `requirements.txt`: cấu hình chạy thống nhất.
- `studio.cmd`: file khởi chạy duy nhất cho Windows.

Các launcher Python/PowerShell cũ được thay bằng Docker. Tài liệu cũ trong `docs/` có thể nhắc
`run_studio.cmd` hoặc `start_studio.ps1`; dùng hướng dẫn này cho phiên bản hiện tại.
Không xóa video, model, tài liệu đề tài hoặc kết quả thí nghiệm khi dọn launcher.

NLLB dùng giấy phép CC-BY-NC-4.0, phục vụ nghiên cứu; xem
[model card](https://huggingface.co/facebook/nllb-200-distilled-600M).
Thiết lập GPU dựa trên [hướng dẫn Docker Compose](https://docs.docker.com/compose/how-tos/gpu-support/).

Để so với server Gemini đã mở sẵn, dùng `--server http://host.docker.internal:8003` thay cho
`--gemini-direct --prompt-key` trong lệnh benchmark. Không cần nhập lại khóa cho cách này.
