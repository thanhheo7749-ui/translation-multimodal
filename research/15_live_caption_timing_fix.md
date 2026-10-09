# Sửa phụ đề về muộn và tách ASR/MT

**Đã thay đổi sau phản hồi người dùng:** quy tắc ẩn sau 2,5 giây bên dưới làm mất phụ đề và đã được thay. Hành vi hiện tại ở `16_caption_visibility_and_parallel_mt.md`: hiển thị có nhãn độ trễ, chống quay ngược và MT song song tối đa hai request.

Ngày 08/10/2026. Người dùng báo video đang nói câu này nhưng phụ đề hiện câu khác.

## Nguyên nhân xác nhận từ code

Lớp phụ đề trước đây lấy bản dịch mới nhận được và giữ tối đa 15 giây theo đồng hồ giao diện, không kiểm tra timestamp của lời nói. ASR và MT dùng chung vòng chờ nối tiếp. Vì vậy bản dịch của đoạn cũ có thể xuất hiện trên đoạn video mới. Phép thử trước về tính đúng của một câu không xác nhận đồng bộ video.

## Đã thay đổi

- Thu PCM liên tục, cập nhật ASR trên cửa sổ audio chồng nhau tối đa 12 giây, chu kỳ đề xuất mặc định 1,5 giây. Không đọc audio tương lai. Khi xử lý bận, giữ snapshot mới nhất thay cho các lần nhận dạng cũ đang chờ; nếu phần chưa chốt trôi khỏi cửa sổ thì ghi rõ đoạn bỏ.
- ASR trả timestamp từng từ. Chốt tiền tố trùng nhau qua hai lần nhận dạng liên tiếp; khoảng nghỉ hoặc dừng phiên chốt phần đuôi. Từ đã chốt có bộ lọc lặp khi timestamp dịch nhẹ. Giữ lại 1,5 giây audio trước mốc chốt, loại phần cũ hơn để giảm tính toán.
- Nhận dạng tiếp tục trong lúc MT chờ mạng. Các cụm ổn định được gom trước MT (dấu câu, khoảng sáu từ hoặc chờ 1,2 giây). Văn bản đang chờ có thể được gộp; nếu vượt 1.600 ký tự thì báo overflow thay vì âm thầm bỏ.
- Phụ đề video dựa trên timestamp lời nói, không dựa trên giờ nhận response. Hết hạn sau cuối cụm 2,5 giây; kết quả về quá hạn vẫn lưu lịch sử và được đếm là bản dịch muộn. Khi tua, vô hiệu hóa phụ đề của phiên cũ. PiP dùng cùng quy tắc và cùng cặp câu Anh–Việt.
- Bản nháp ASR được hiển thị riêng; phụ đề Việt không bị thay bằng chữ nháp nhận dạng. Có thể còn khoảng trống khi kết quả đến muộn. Cơ chế hết hạn không phải bằng chứng hệ thống đã nhanh hơn hoặc dịch đầy đủ.

## Kiểm tra

- Test JavaScript kiểm tra snapshot chỉ chứa audio đã tới, giới hạn 12 giây, trim giữ đúng offset, chốt tiền tố, sửa từ nháp, tránh lặp do timestamp lệch và không xóa lần lặp từ thật.
- Test frontend với network giả lập giữ MT chưa trả: ASR đoạn tiếp vẫn được gọi. Kiểm tra MT có thứ tự, phụ đề quá hạn không hiện và phụ đề bị vô hiệu khi tua.
- Chạy ASR thật trên 29 snapshot từ 40 giây đầu video NVIDIA, lưu ở `experiments/runtime_logs/asr_debug/rolling_results.json`. Đây là replay offline; không phải đo tốc độ phát video thật. Lần replay này chưa áp dụng trim động theo kết quả từng lượt, nên không dùng nó để kết luận latency bản cuối. Đầu ra vẫn có lỗi từ ở một số chỗ; chưa có WER chuẩn.

## Còn cần xác nhận

Khởi động lại server, tải lại `/live`, phát NVIDIA từ đầu. Quan sát số bản dịch muộn, đoạn bỏ và khoảng trống phụ đề; xuất log phiên. Timestamp từ Whisper là ước lượng, biên 2,5 giây là quy tắc hiển thị có thể điều chỉnh, không chứng minh khớp chính xác từng câu. Các kiểm tra tự động chưa thay thế phép thử Chrome/capture thật.

Nếu vẫn có nhiều bản dịch muộn, phải cải thiện tốc độ ASR/MT hoặc thử trì hoãn video hiển thị. Không tăng thời gian giữ câu cũ để che độ trễ. Chưa triển khai phát video có bộ đệm trễ.
