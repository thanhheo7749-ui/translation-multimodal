# Thử dịch trực tiếp từ tab hoặc micro

**Bản mới nhất:** xem `16_caption_visibility_and_parallel_mt.md`. Đã bỏ ẩn phụ đề muộn và cho hai request dịch chạy đồng thời. Khi server đã hỗ trợ ASR tăng dần, chỉ cần Ctrl+F5 để nạp giao diện mới.

**Cập nhật mới nhất:** luồng hiện đã chuyển sang ASR cập nhật dần, chốt từ ổn định và MT độc lập; phần mô tả phân đoạn 8 giây bên dưới là lịch sử cấu hình trước. Xem `15_live_caption_timing_fix.md` để biết hành vi hiện tại và giới hạn đồng bộ. Cần khởi động lại server để nhận timestamp từ.

Cập nhật: 08/10/2026. Đã triển khai luồng audio thật, xử lý tăng dần; chưa kiểm chứng thao tác cấp quyền capture và cửa sổ nổi trên Chrome của người dùng.

## Cách chạy

### Thử ngay với video NVIDIA có sẵn

Khởi động lại server bằng `run_studio.cmd`, mở `/live`, đợi ASR sẵn sàng rồi bấm **Phát video NVIDIA và dịch**. Video được phục vụ từ tệp NVIDIA gốc qua HTTP Range; việc tải/buffer video không chạy ASR hoặc dịch. Browser dùng `video.captureStream()` lấy âm thanh đang phát và đưa vào cùng luồng PCM trực tiếp. Có thể xem phụ đề trong cửa sổ nổi. Tạm dừng trên trình phát sẽ dừng nguồn lời nói mới; các đoạn đã thu vẫn có thể xử lý tiếp. Khi tua, ứng dụng dừng phiên và yêu cầu bấm bắt đầu lại tại vị trí mới để reset ngữ cảnh. Chức năng này cần thử thực tế trên Chrome; kiểm tra backend đã xác nhận tải video không gọi ASR/MT hoặc pipeline batch.

### Thu từ tab khác hoặc micro

1. Trong cửa sổ server đang chạy, nhấn **Ctrl+C**. Server cũ không có endpoint thu âm trực tiếp.
2. Mở lại **run_studio.cmd**. Nhập khóa tại terminal nếu được hỏi; không nhập vào trang web. Model mặc định là `gemini-3.5-flash-lite`.
3. Trang `/live` tự mở. Dùng địa chỉ/port terminal in ra nếu không tự mở; ví dụ `http://localhost:8003/live`. Chờ trạng thái **Sẵn sàng chia sẻ tab** sau khi nạp ASR local.
4. Mở video nói tiếng Anh trong một tab Chrome khác. Trong trang dịch, bấm **Chia sẻ tab**, chọn **Chrome Tab**, chọn tab video và bật **Share tab audio / Chia sẻ âm thanh tab**. Phát video ở tab nguồn.
5. Quan sát thanh mức âm thanh, thời gian đã thu, lời nói tiếng Anh và bản dịch tiếng Việt. Bấm **Mở cửa sổ nổi** để xem phụ đề khi trở lại tab video.
6. Bấm **Dừng thu** để xử lý đoạn cuối. Bấm **Xuất nhật ký** để lưu kết quả và số đo của phiên.

Có thể dùng **Thử bằng micro**, nói tiếng Anh, để kiểm tra nhanh mà không cần YouTube. Nếu tab không có audio track, ứng dụng báo lỗi và yêu cầu chọn lại. Quyền chia sẻ do người dùng xác nhận trong hộp thoại trình duyệt.

## Luồng thực tế và độ trễ

Browser thu PCM liên tục qua AudioWorklet, chuyển về mono 16 kHz, phát hiện năng lượng lời nói rồi đóng đoạn khi có khoảng nghỉ hoặc đạt độ dài đã chọn. Mặc định tối đa khoảng **2,5 giây** mỗi đoạn; có tùy chọn 1,5 hoặc 4 giây. Đây là phân đoạn bằng ngưỡng năng lượng, chưa phải VAD học máy trong browser.

Backend nhận dạng bằng Whisper `base.en` local, sau đó dịch qua Gemini Lite, có ngữ cảnh từ các đoạn đã xử lý trước. Tiếng Anh hiện ra trước, tiếng Việt cập nhật sau khi dịch xong. Âm thanh video gốc vẫn phát bình thường. Phiên này không đọc file tương lai hoặc xử lý trước toàn bộ video.

Phụ đề cập nhật theo đoạn ngắn, chưa dịch từng từ ngay lập tức. Thời gian gom đoạn, thời gian chờ hàng đợi, ASR và MT đều ảnh hưởng trải nghiệm. Chỉ số **sau cuối đoạn** đo từ lúc browser nhận gói PCM cuối của đoạn đến lúc hiển thị bản dịch; không bao gồm toàn bộ thời gian gom đoạn và không phải độ trễ so với timestamp YouTube. Không dùng con số này thay cho độ trễ từ đầu lời nói.

Hàng đợi tối đa 3 đoạn đang chờ; khi đầy bỏ đoạn chờ cũ nhất. Đoạn chờ quá 12 giây cũng bị bỏ và ghi rõ trên UI/nhật ký. Đây là chính sách bắt kịp nguồn, có đánh đổi coverage; chưa bảo đảm hệ thống xử lý kịp lời nói liên tục. Có 100 ms âm thanh chồng giữa các đoạn để giảm mất từ ở ranh giới, nên vẫn có thể lặp từ. Khi tua video hoặc đổi nội dung, nên dừng rồi bắt đầu phiên mới để reset ngữ cảnh.

Hiện tại luồng live chỉ dùng audio và ngữ cảnh văn bản. **OCR thích ứng và lồng tiếng chưa bật**. Khi không hỗ trợ Document PiP, ứng dụng mở cửa sổ thường và thông báo rằng cửa sổ này không bảo đảm luôn nổi.

## Kiểm tra đã thực hiện

- Toàn bộ bộ kiểm tra Python: 65 test đạt, gồm endpoint PCM, ngữ cảnh dịch, chặn Origin khác và khả năng server trả trạng thái khi ASR đang chạy.
- Kiểm tra JavaScript đạt: phân đoạn, hàng đợi, PCM little-endian và resample từ 16/44,1/48 kHz về 16 kHz. Đã kiểm tra cú pháp JavaScript/Python.
- Một đoạn PCM thật 3 giây được nhận dạng thành `My relationship with you started here.` rồi dịch thành `Mối quan hệ của tôi với bạn bắt đầu từ đây.` ASR khoảng 912 ms; MT khoảng 1.594 ms. Nạp model ban đầu khoảng 718 ms, được thực hiện ở bước warmup.
- Bằng chứng lưu tại `experiments/runtime_logs/live_pcm_smoke.json`. Phép thử dùng PCM từ file để kiểm tra ASR thật và provider thật; không chứng minh capture/PiP trên trình duyệt đã hoạt động.

## Kiểm tra tiếp trên Chrome

Thử video tiếng Anh liên tục 2–3 phút, xem thanh âm thanh có hoạt động, bản dịch có cập nhật khi tab nguồn vẫn phát và PiP có giữ trạng thái khi đổi tab. Sau đó thử dừng chia sẻ bằng nút của Chrome, thử micro và xuất nhật ký. Ghi nhận đoạn bị bỏ, lỗi nhận dạng, lặp từ và độ trễ; chưa kết luận chất lượng nghiên cứu từ một phiên demo.

Tài liệu API: [getDisplayMedia](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getDisplayMedia), [AudioWorklet](https://developer.mozilla.org/en-US/docs/Web/API/AudioWorklet), [Document Picture-in-Picture](https://developer.chrome.com/docs/web-platform/document-picture-in-picture).
