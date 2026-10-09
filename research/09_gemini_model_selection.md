# Cấu hình dịch thử Gemini — 07/10/2026

- Model đề xuất vòng đầu: `gemini-3.8-flash`, stable; thinking level `low`. Mục đích là thử chất lượng dịch có context và đo latency, chưa kết luận đây là model dịch Anh–Việt tốt nhất từ benchmark.
- Nguồn chính thức: [model card/specifications](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash), [danh mục models](https://ai.google.dev/gemini-api/docs/models). Tài liệu liệt kê stable 3.8 Flash và hỗ trợ text input/output, thinking low/medium/high. Danh mục hiện ghi quyền truy cập dòng 2.5 hạn chế cho người đã dùng trước, nên đổi default của project mới khỏi 2.5.
- Default đã đồng bộ ở web adapter, async Gemini provider và launch script. Pilot runner ghi thinking level vào config khi chọn model này. Không thay model giữa các arm trong cùng benchmark.
- Key do người dùng cung cấp được truyền vào stdin có che ký tự rồi môi trường của child process; không lưu key trong source/config/log/file dữ liệu. Không ghi lại giá trị hoặc fingerprint key ở đây.
- Probe model access và thử dịch một câu đều gặp `network_blocked` / WinError 10013 từ môi trường hiện tại. **Chưa xác minh key hợp lệ, quota hoặc model access; chưa có bản dịch provider thật.**
- Server cấu hình Gemini cho phép xem trạng thái tại `http://localhost:8004/translation-test`; configured=true chỉ nghĩa là có key trong môi trường, không nghĩa là API đã thành công.
- Để chạy ngoài môi trường hạn chế của phiên trợ lý, người dùng mở PowerShell tại thư mục dự án, chạy `./start_studio.ps1 -Provider gemini -GeminiModel gemini-3.8-flash -Port 8003`, rồi dùng trang thử một câu. Khóa mới nhập ẩn khi script hỏi, không dán vào chat.
- Khóa đã xuất hiện trong chat cần được thu hồi/thay thế. Sau khi tạo key mới, chạy lại script bằng key mới trên máy.
- 44 tests pass sau thay đổi; tests dùng fixture để kiểm tra parsing/config/error handling, không xác nhận chất lượng hoặc latency thực tế của Gemini.
