# Đánh giá phương án nghe hai câu, dịch một câu

Cập nhật cuối ngày 08/10: đã triển khai phiên bản đầu của ASR chốt dần, tách MT và lọc phụ đề về muộn; xem `15_live_caption_timing_fix.md`. Kế hoạch so sánh A/B/C và kiểm chứng chất lượng dưới đây vẫn chưa được thực hiện đầy đủ.

Ngày 08/10/2026. Phạm vi: bổ sung kế hoạch thử nghiệm nội bộ cho ASR/subtitle; không thay câu hỏi nghiên cứu chính về OCR thích ứng. Trạng thái: phương án chưa triển khai, chưa có kết quả so sánh độ trễ. Đã thêm lớp phụ đề Việt trên video vào giao diện hiện tại.

## Đánh giá đề xuất

Giữ thêm âm thanh/ngữ cảnh có thể giúp giải quyết phần cuối chưa rõ của câu trước. Tuy nhiên, đợi hết câu thứ hai rồi dịch câu thứ nhất khiến độ trễ của câu thứ nhất bao gồm thời gian nói câu thứ hai. Với câu dài hoặc người nói ít ngắt, độ trễ có thể lớn hơn cửa sổ 8 giây. Nếu dùng cửa sổ trượt `(câu 1, câu 2) → dịch câu 1`, `(câu 2, câu 3) → dịch câu 2` thì phải xử lý riêng câu cuối khi dừng, và câu đã chốt không được phát lại.

Hiện tại audio vẫn được thu trong lúc ASR/MT xử lý. Chờ đủ đoạn làm tăng latency, không tự động gây mất audio. Giới hạn hàng đợi hoặc nhận dạng sai ranh giới mới có thể làm mất nội dung ở đầu ra. Vòng xử lý hiện tại còn đợi MT xong mới ASR đoạn kế tiếp; cần tách hai công đoạn để MT chậm không ngăn nhận dạng mới.

Phương án ưu tiên thử: thu liên tục; cập nhật ASR mỗi 1–2 giây trên phần audio gần nhất chưa chốt, giữ đủ ngữ cảnh. So sánh các lần nhận dạng liên tiếp, chốt tiền tố ổn định và giữ phần đuôi để nhận dạng lại. **Hai lần nhận dạng đồng thuận khác với đợi hai câu hoàn chỉnh.** Đây là hướng đã có trong Whisper-Streaming, không phải tính mới được đề xuất cho đề tài. [Macháček, Dabre và Bojar, 2023](https://aclanthology.org/2023.ijcnlp-demo.3/).

Chu kỳ 1–2 giây là thông số dự kiến để thử, không phải cam kết latency. Local agreement cũng không bảo đảm đúng: hai lần nhận dạng có thể lặp cùng một lỗi. Cần timestamp từ, prompt chỉ từ phần đã chốt, giới hạn bộ đệm và xử lý khi mô hình sửa ranh giới.

## Trình tự triển khai đề xuất

1. Tách hàng đợi ASR và MT. Audio tiếp tục được thu; ASR cập nhật bản nháp trong lúc câu đã chốt đang dịch. Ghi rõ overflow, không bỏ nội dung rồi báo thành công.
2. Thêm bộ đệm audio và mốc chốt theo session. Chỉ đọc mẫu đã tới; chạy lại phần chưa ổn định; tránh dịch lặp phần chồng âm thanh. Nếu quá tải, gộp lần cập nhật nháp thay vì tự bỏ câu đã chốt.
3. Chốt theo sự ổn định và ranh giới cụm có nghĩa. Dấu câu ASR chỉ là một tín hiệu. Đặt hạn chờ cho phần đuôi; khi dừng, xử lý nốt và gắn nhãn phần chưa xác nhận nếu cần.
4. Dịch cụm đã chốt với ngữ cảnh văn bản trước đó; thử riêng bản dịch nháp có sửa, đo số lần sửa để đánh giá mức nhấp nháy.
5. Trên video, hiển thị phụ đề Việt, tùy chọn dòng tiếng Anh nháp, trạng thái nháp/chốt và độ trễ thực. Không gọi bản dịch đến muộn là đồng bộ với timestamp gốc.

Nếu cần hình ảnh và phụ đề khớp nhau hơn, có thể thử trì hoãn phần video người dùng nhìn thấy trong khi audio đầu vào vẫn tiến đều theo đồng hồ thực. Trễ hình là một đánh đổi riêng, không loại bỏ độ trễ xử lý và không cho phép đọc audio tương lai. Chưa triển khai chế độ này.

## So sánh để ra quyết định

| Nhánh | Chính sách | Điều cần kiểm chứng |
|---|---|---|
| A | Khoảng nghỉ, tối đa 8 giây hiện tại | Mốc chuẩn về lỗi, thời gian chờ và coverage |
| B | Hai câu → chốt câu trước, trượt một câu | Lợi ích của ngữ cảnh tương lai đã đến và chi phí chờ câu sau |
| C | Cập nhật audio tăng dần, chốt phần ổn định | Giảm chờ mà không tăng mất/lặp từ quá mức |

Dùng cùng video NVIDIA, cùng model ASR/MT và transcript chuẩn do người kiểm tra. NVIDIA là tập phát triển; sau đó dùng các video độc lập để kiểm tra tổng quát. Không lấy transcript từ lần ASR dài làm ground truth. Chạy replay theo đồng hồ thực, lặp nhiều lượt và thay đổi thứ tự các nhánh khi dùng API để giảm ảnh hưởng biến động mạng.

Đo: WER và thành phần xóa từ của ASR; số câu/đoạn bỏ do quá tải; số từ lặp; độ trễ đến bản nháp và bản chốt (p50/p95, từ mốc kết thúc lời nói được gán nhãn tới hiển thị); lỗi dịch nghĩa/thuật ngữ; thời gian ASR, MT, hàng đợi và chi phí API. Những đoạn bị bỏ vẫn được tính vào chất lượng và coverage; không chỉ đo latency trên đoạn thành công. Đo riêng kết thúc phiên và khoảng không có lời nói.

Tiêu chí chọn phải được chốt trên tập phát triển trước khi đánh giá tập kiểm tra. Chưa có cơ sở cam kết 0 giây, 1 giây hoặc khẳng định phương án C tốt hơn trên máy hiện tại.

## QA nội bộ

- Dữ kiện: lỗi chia đoạn đã tái hiện trong `13_live_asr_segmentation_fix.md`; đường xử lý nối tiếp đọc từ `frontend/live.js`.
- Bằng chứng công bố: Whisper-Streaming hỗ trợ lập luận thử local agreement; không dùng số đo của bài báo làm thành tích của dự án.
- Giả thuyết: C giảm latency so với A ở mức lỗi chấp nhận được; cần thực nghiệm.
- Rủi ro: chi phí chạy lại ASR, sửa từ ở biên, câu không có dấu chấm, MT chậm và thiếu ground truth. Chưa chạy phản biện chuyên gia hoặc chấm điểm định lượng.
- Bước tiếp theo: triển khai nhánh C có log timestamp trước khi chạy so sánh A/B/C.
