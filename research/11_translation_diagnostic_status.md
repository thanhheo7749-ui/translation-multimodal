# Tình trạng chẩn đoán dịch — 08/10/2026

## Bằng chứng mới từ môi trường người dùng

`experiments/runtime_logs/network_diagnostic.json` ghi DNS Google API thành công; HTTPS tới `/v1beta/models` nhận HTTP 403 với cả CA hệ thống và CA bổ sung; HTTPS Google thông thường nhận 204. Đây là probe không có API key: 403 chứng minh đã tới HTTP service, không chứng minh key sai hoặc thiếu quota. Không tiếp tục coi sự cố socket của phiên trợ lý là kết quả đo mạng trên môi trường người dùng.

## Thay đổi phục vụ xác định nguyên nhân

- `LiveTranslationService.check_access()` gửi GET metadata của model với khóa trong header; timeout 10 giây; không tạo bản dịch. Phân biệt metadata access với quota/chất lượng/tốc độ generation.
- Launcher kiểm tra có xác thực khi khởi chạy; trang `/translation-test` có nút kiểm tra khóa/model riêng.
- HTTP error được phân loại từ các reason/status đã định nghĩa: invalid/expired key, giới hạn key/API, API chưa bật, model unavailable, quota, request không hợp lệ. Không in body/message/URL/header từ provider.
- Log an toàn `translation_attempts.jsonl` chỉ lưu timestamp, phase, provider/model, status/error code, timing và diagnostic codes; không lưu key, prompt hoặc nội dung dịch.
- 52 test pass; kiểm tra syntax Python/JavaScript pass. Các fixture này kiểm tra error handling, không phải kết quả Gemini thật.

## Điều chưa xác nhận

Chưa có kết quả kiểm tra có xác thực từ server người dùng sau cập nhật. Không kết luận API key hợp lệ, model có quyền truy cập hoặc pipeline đã dịch thành công. Cần mở lại `run_studio.cmd`, đọc phase `model_access`; nếu phase này thành công, chạy `translation` để phân biệt generation timeout/quota với lỗi cấu hình.

## Cập nhật từ log thực tế lúc 12:14–12:15 ngày 08/10/2026

- Hai request model_access tới `gemini-3.8-flash` thành công, 1372.7 ms và 1569.1 ms. Khóa cấu hình được Google chấp nhận cho metadata của model tại thời điểm đó.
- Request translation bị TimeoutError sau 30635.8 ms. Log cũ chưa ghi response headers nên chưa biết timeout trước headers hay khi đọc body; không quy lỗi này cho DNS, TLS hoặc khóa dựa trên kết quả đã có.
- Bản demo được đổi mặc định sang `gemini-3.5-flash-lite` với thinking `minimal`, dựa trên [đặc tả model](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite) và [thinking levels](https://ai.google.dev/gemini-api/docs/thinking). Đây là cấu hình thử mới, chưa có kết quả generation thành công xác nhận trên máy người dùng.
- Adapter gọi `streamGenerateContent?alt=sse`, ghi thời gian headers/dòng phản hồi/text đầu tiên; JSON vẫn có để đối chiếu cùng payload. Giao diện thử nghiệm vẫn hiển thị bản dịch hoàn chỉnh, chưa stream các token ra browser.
- Socket timeout thử nghiệm là 60 giây cho các thao tác mạng, không phải bảo đảm hard end-to-end deadline. Tăng thời gian chờ chỉ hỗ trợ chẩn đoán, không đủ chứng minh real-time.
- Bản bị cắt cụt hoặc timeout giữa stream không được tính là dịch thành công. Không retry tự động hoặc chuyển model âm thầm trong benchmark.

## Xác nhận Flash-Lite trên server người dùng

- Metadata `gemini-3.5-flash-lite` thành công trong 656.9 ms và 598.5 ms.
- Request streaming đầu tiên trong log thành công, tổng 2048.9 ms, text đầu tiên 1810.2 ms.
- Kiểm tra trực tiếp endpoint của server cổng 8003: câu “Your companies started here.” được trả “Các công ty của các bạn đã bắt đầu ở đây.”; status=ok, model=gemini-3.5-flash-lite, tổng request 1592.4 ms. Artifact: `experiments/runtime_logs/translation_smoke_verified.json`.
- Người dùng xác nhận Lite hoạt động. Giữ Lite làm default demo; đây là smoke test vài request, không phải chứng minh quality benchmark, p95 hay end-to-end latency live.
- Không cần đổi API key tiếp để giải quyết timeout đã thấy ở cấu hình Flash trước. Kết quả không chứng minh nguyên nhân duy nhất là model: endpoint, chế độ stream, prompt và timeout đã thay đổi cùng đợt; cần phép so sánh có kiểm soát nếu muốn quy nguyên nhân.
