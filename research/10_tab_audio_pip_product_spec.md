# Đặc tả sản phẩm: dịch âm thanh tab và phụ đề nổi

Ngày cập nhật: 08/10/2026. Căn cứ: hai ảnh người dùng cung cấp (`Screenshot 2026-10-08 075120.png`, `Screenshot 2026-10-08 075225.png`) và mô tả trải nghiệm. Chưa đọc được mã nguồn hoặc gọi thử engine của ZolaChat; các nhận xét dưới đây không suy đoán model/ASR/backend của họ.

## 1. Những gì xác nhận được từ ảnh

| Quan sát | Mức bằng chứng |
|---|---|
| Có hộp thoại Chrome chọn tab/window/screen, bật chia sẻ âm thanh tab | Thấy trong ảnh thứ nhất |
| Có chọn ngôn ngữ nguồn/đích Anh–Việt và nút bật/tắt loa đọc | Thấy trong cả hai ảnh; chưa xác nhận đầu ra TTS thực tế |
| Trang chính có vùng lời nói gốc và bản dịch | Thấy tiêu đề các vùng trong ảnh thứ nhất |
| YouTube tiếp tục phát trong khi tab đang chia sẻ | Thấy trạng thái phát và thanh chia sẻ ở ảnh thứ hai; người dùng mô tả cùng luồng |
| Có cửa sổ nhỏ riêng, nút dừng và trạng thái đang dịch | Thấy trong ảnh thứ hai |
| Có bản dịch Việt đúng/nhanh hoặc có OCR thích ứng | Chưa có bằng chứng: vùng kết quả trong ảnh còn trống |
| Engine STT/MT và việc có xử lý hình ảnh phía sau | Chưa xác nhận; nhãn thương hiệu trên UI không xác định implementation |

Đây là reference về trải nghiệm sản phẩm. Không dùng ảnh để kết luận chất lượng/latency hoặc baseline khoa học của engine bên ngoài.

## 2. Luồng sử dụng chính của dự án

1. Người dùng mở video YouTube/bài giảng trong tab nguồn.
2. Mở ứng dụng dịch, chọn Anh → Việt và bấm **Chia sẻ tab để dịch**.
3. Chọn đúng tab, bật **Share tab audio** và xác nhận trong hộp thoại của trình duyệt.
4. Ứng dụng kiểm tra có audio track; nếu thiếu thì hướng dẫn chọn lại thay vì tiếp tục nhận dạng im lặng.
5. Audio được xử lý tăng dần; lời nói gốc và bản dịch cập nhật ở trang chính.
6. Người dùng bấm **Mở cửa sổ nổi** để theo dõi phụ đề khi xem tab nguồn.
7. Có thể dừng, chọn lại nguồn và đóng PiP; trạng thái lỗi mạng/ASR/MT được hiển thị rõ ở cả hai nơi.

Tab capture và cửa sổ nổi được đưa thành **yêu cầu sản phẩm lõi theo trải nghiệm người dùng đã xác định**, thay cho việc chỉ để live capture ở giai đoạn mở rộng. Upload/replay tiếp tục phục vụ gán nhãn, tái lập và benchmark.

## 3. Nền tảng kỹ thuật phù hợp

- `getDisplayMedia()` tạo luồng từ bề mặt người dùng chọn, có video track và audio nếu nguồn/trình duyệt hỗ trợ. Phải kiểm tra audio track sau khi người dùng chọn; yêu cầu `audio: true` không bảo đảm luôn có âm thanh. Đây là lựa chọn triển khai cho dự án, không phải xác nhận ZolaChat sử dụng đúng code/API này. [MDN](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getDisplayMedia).
- Document Picture-in-Picture cho phép đưa nội dung HTML và điều khiển vào cửa sổ luôn nổi trong trình duyệt hỗ trợ. Phù hợp transcript + phụ đề + nút dừng/chọn ngôn ngữ. Nếu không hỗ trợ, dùng panel/tab riêng và ghi rõ cửa sổ thường không bảo đảm always-on-top. [Chrome documentation](https://developer.chrome.com/docs/web-platform/document-picture-in-picture).
- UI chính và PiP dùng chung state/event của một session; không mở thêm một ASR/MT pipeline khi mở PiP.
- Browser thu audio và gửi về backend nhận dạng local; backend gọi engine dịch rồi trả event có segment/version/status. Chọn transport/encoding sau khi kiểm tra streaming decoder và browser support.
- Lấy frame từ video track đã được người dùng chia sẻ để nghiên cứu OCR; chỉ xử lý frame thuộc session và đã khả dụng. Việc nhận được video track chưa đồng nghĩa mọi frame đều phải OCR.

## 4. Điểm riêng của nghiên cứu

Trải nghiệm tab capture/PiP là phần ứng dụng cần hoàn thiện. Câu hỏi nghiên cứu giữ nguyên: **khi nào chữ trên màn hình giúp dịch đủ để đáng bỏ thời gian/tài nguyên OCR?**

Pipeline đề xuất:

```text
Tab nguồn được chia sẻ
 ├─ Audio → ASR tăng dần → Transcript + text context
 └─ Video → Frame candidates / scene signal
                       ↓
            Policy + cache + deadline
             ├─ Dịch bằng văn bản
             ├─ Dùng OCR đã có
             └─ Yêu cầu OCR mới khi có ích
                       ↓
              Bản dịch nháp / chốt
                       ↓
               Trang chính + PiP
```

Chưa có bằng chứng reference sử dụng adaptive OCR, nên không gọi đây là tính năng mà họ thiếu. Điểm khác biệt phải xác lập từ phương pháp và thực nghiệm của dự án, không từ việc quan sát một UI.

## 5. Những điều cần kiểm chứng khi capture tab

- Frame có thể chứa player controls, tiêu đề, chat, phụ đề hoặc chữ ngoài slide. Cần chọn/crop vùng video/slide và log vùng OCR, tránh scene trigger từ menu hoặc chuyển động UI.
- Nếu nguồn có sẵn phụ đề, đặc biệt bản dịch Việt, OCR có thể đọc chính đáp án. Benchmark phải tắt hoặc che vùng phụ đề theo quy tắc cố định; giữ cùng điều kiện giữa các arm. Nếu khai thác captions là một baseline riêng thì khai báo rõ.
- Capture timestamps là thời gian thu ở browser; không mặc định chúng bằng `currentTime` của video bên trong tab khác. Cần định nghĩa lag từ input capture đến draft/commit và cách ánh xạ browser/backend clock.
- Tua video/chuyển tab/đổi nguồn có thể làm context lỗi thời; cần quy tắc flush/reset. Nếu chưa phát hiện seek tự động, UI phải cho phép reset session thủ công.
- Người dùng bấm Stop sharing ngoài app thì audio/video tracks kết thúc; app phải dừng queue/inference và cập nhật cả PiP/trang chính.
- Có quyền thu tab không chứng minh hệ thống xử lý kịp thời gian thực. Phải đo hàng đợi, lag, deadline miss và coverage trên run thực.

## 6. Thứ tự triển khai cập nhật

| Mốc | Việc | Nghiệm thu |
|---|---|---|
| T0 | Giải quyết kết nối MT hiện còn lỗi | Dịch thử một câu thành công; key/model/network được xác nhận bằng response thật |
| T1 | Tab capture + audio track check + nút dừng | Thu đúng nguồn khi video tiếp tục chạy; từ chối/hủy/chia sẻ thiếu audio có thông báo |
| T2 | ASR tăng dần + MT + event state | Transcript và bản dịch xuất trước khi nguồn hết; không đọc tương lai; lỗi không thành output success |
| T3 | Document PiP + state dùng chung | Mở/đóng PiP không nhân đôi xử lý; dừng từ PiP dừng session; trang chính/PiP nhất quán |
| T4 | Frame/OCR đúng nguồn và đúng thời điểm | Log vùng OCR, frame/capture/available time; không đọc đáp án từ captions hoặc cache cũ |
| T5 | A/B/C và adaptive policy | Benchmark nhiều nguồn, baseline công bằng, quality/latency/cost rõ |

TTS bật/tắt có thể thêm sau T3 nếu yêu cầu: chỉ đọc text đã chốt, không thu ngược giọng dịch vào tab nguồn. Chưa coi lồng tiếng là yêu cầu đã hoàn thành.

Trạng thái triển khai 08/10/2026: đã có trang /live, thu audio tab/micro, phân đoạn PCM, ASR local, dịch Gemini Lite và cửa sổ nổi. Kiểm tra tự động và phép thử PCM thật đã đạt; thao tác capture/PiP trên Chrome của người dùng còn cần kiểm chứng. Luồng live chưa bật OCR/TTS. Xem [hướng dẫn thử trực tiếp](12_live_audio_runbook.md).
