# Thử NLLB local và Gemini — trạng thái thực tế

Ngày 08/10/2026. **Chưa có kết quả local, chưa kết luận model nào nhanh hoặc tốt hơn.**

## Đã kiểm tra

- Máy có RTX 3050 Laptop 6 GB và khoảng 16 GB RAM.
- Môi trường Python hiện tại có CTranslate2 nhưng chưa có PyTorch, Transformers hoặc SentencePiece; cache chưa có NLLB.
- Thử tải cấu hình NLLB từ kho chính thức thất bại do socket bị chặn với `WinError 10013` trong môi trường agent. Không bỏ kiểm tra TLS hoặc đổi đường kết nối để vượt hạn chế.
- Tại thời điểm chạy bộ thử, server Gemini không phản hồi trên localhost:8000–8010. Kết quả lần thử lưu ở `experiments/local_comparison/20261008T065934_071482Z/results.json`: hai provider unavailable, không có mẫu dịch. Không dùng output giả từ `backend/translation/local_provider.py` để đo local.
- Số liệu lịch sử Gemini trước đó (20 request: median 2.335 ms, max 8.085,6 ms) chỉ là thông tin tham khảo, không phải đối chứng cùng phiên với local.

## Chạy phép thử thật

1. Mở lại `run_studio.cmd`, giữ server Gemini đang chạy.
2. Mở `run_local_comparison.cmd`. Nếu server dùng port khác 8003, chạy trong PowerShell: `./run_local_comparison.cmd -Server http://127.0.0.1:8004` (thay đúng port).
3. Lần đầu script tạo `.venv-mt-benchmark`, tải PyTorch CUDA và model NLLB chính thức vào `models/hf-cache`. Tổng cần tải vài GB. Kho NLLB chứa trọng số khoảng 2,46 GB; xem [tệp chính thức](https://huggingface.co/facebook/nllb-200-distilled-600M/tree/main). Môi trường của studio giữ nguyên.
4. Script chạy local GPU và gọi endpoint Gemini của server hiện tại; không đọc, nhập hoặc lưu API key. Nếu CUDA không dùng được, báo lỗi chứ không âm thầm đổi sang CPU. Muốn đo CPU riêng, dùng `--device cpu` trong Python runner.
5. Kết quả nằm ở đường dẫn `REPORT` được in ra: `results.json`, `summary.md`, `translations.csv`.

Lệnh chạy lại sau khi đã có thư viện/trọng số, không cho tải model mới:

```powershell
./.venv-mt-benchmark/Scripts/python.exe -X utf8 experiments/compare_local_translation.py --providers both --repeats 3
```

## Thiết kế phép so sánh

Cùng sáu chuỗi tiếng Anh từ kết quả ASR của 40 giây đầu NVIDIA, chưa là transcript chuẩn đã được người duyệt. Một video, sáu đầu vào, ba lần lặp kỹ thuật; không coi 18 request là 18 nguồn độc lập. Mỗi câu được dịch bởi hai provider; thứ tự câu và provider được xáo trộn bằng seed 42. Không có OCR hoặc ngữ cảnh bổ sung. NLLB beam 4, không sampling; Gemini giữ cấu hình server và ghi model thực tế.

Tải/kiểm tra cache, nạp model và warmup được ghi riêng. Latency local gồm tokenize + generate + decode với CUDA synchronize; Gemini gồm HTTP localhost + xử lý API. Các request trong phép so sánh chạy nối tiếp, để đo một yêu cầu thay vì trộn với lợi ích chạy song song. Báo số thành công/thử, trung vị và max trên các request thành công; lỗi vẫn nằm trong mẫu số và log. Không suy ra latency toàn bộ phụ đề từ phép thử dịch văn bản.

Chất lượng giữ trạng thái `NOT_SCORED`. CSV có bản dịch và ô ghi lỗi nghĩa/thuật ngữ cho người kiểm tra. Không tự tạo BLEU/COMET hoặc điểm chất lượng khi chưa có bản dịch tham chiếu được duyệt. Không tính p-value hoặc khẳng định tổng quát từ một video.

## Kiểm tra bộ thử và giới hạn

Ba test đã đạt: giữ lỗi trong mẫu số; model thiếu không tạo bản dịch local giả; warmup được tách khỏi bảng latency. PowerShell đã kiểm tra cú pháp. Đây là kiểm tra mã điều phối, chưa xác nhận NLLB suy luận GPU vì trọng số/thư viện chưa tải được.

Skill `nature-statistics` đã áp dụng để xác định đơn vị quan sát và ranh giới suy luận. Vấn đề P0 nếu báo model thắng lúc này: thiếu cả kết quả local và đối chứng cùng phiên. Việc cần làm tiếp: chạy launcher trên máy người dùng để có dữ liệu thật, sau đó đọc và đánh giá từng bản dịch.

Nguồn triển khai: [NLLB model card](https://huggingface.co/facebook/nllb-200-distilled-600M), [Transformers NLLB](https://huggingface.co/docs/transformers/v4.50.0/model_doc/nllb), [PyTorch installation](https://pytorch.org/get-started/locally/).
