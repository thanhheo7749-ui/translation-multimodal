# Khôi phục phụ đề và giảm chờ dịch

Ngày 08/10/2026. Sửa sau phản hồi phụ đề biến mất và còn chậm.

## Bằng chứng

20 request MT thành công gần nhất trước bản sửa trong `translation_attempts.jsonl`: trung vị 2.335 ms, min 1.733,7 ms, max 8.085,6 ms. Chưa gồm ASR, chờ ổn định và hàng đợi. Quy tắc ẩn phụ đề sau cuối lời nói 2,5 giây trong bản 15 loại nhiều kết quả trước khi người dùng có thể đọc. Đây là lựa chọn hiển thị quá chặt, không phải cách giải quyết latency.

## Thay đổi đang dùng

- `CaptionPresenter` giữ kết quả mới nhận đủ tối thiểu 900 ms trước khi chuyển sang câu mới. Mỗi phụ đề hết hạn sau 6 giây hiển thị nếu không có bản mới. Kết quả có ID cũ về sau không được làm phụ đề quay ngược. Bản dịch trễ vẫn hiện, có nhãn thời gian sau lời nói; đây không phải đồng bộ hoàn hảo với video.
- Giới hạn hai request MT đồng thời; nhận dạng vẫn độc lập. Ngữ cảnh dịch lấy từ các đoạn nguồn có ID trước đoạn đang dịch, không phụ thuộc thứ tự response và không đưa câu tương lai vào context.
- Cụm ổn định từ bốn từ có thể chuyển sang MT thay vì đợi sáu từ. Phần ngắn vẫn được gom theo khoảng chờ và kết thúc câu. Không thay model hay giảm chất lượng ASR để đạt một con số latency.

## Kiểm chứng

`tests/test_live_pipeline_js.cjs` giữ hai request dịch chưa hoàn thành rồi đưa tiếp âm thanh: ASR vẫn chạy, request MT thứ ba chờ slot; phản hồi thứ hai về trước thứ nhất không gây lỗi. Kiểm tra phụ đề muộn vẫn hiện kèm độ trễ và phản hồi cũ không làm quay ngược. `tests/test_live_audio_js.cjs` kiểm tra thời gian đọc tối thiểu, hết hạn và không tái hiện câu cũ.

Gọi thực tế hai câu qua server đang dùng Gemini Lite: cả hai thành công, tổng wall time 2.172 ms, từng request khoảng 2.053 và 2.167 ms. Lưu `experiments/runtime_logs/parallel_mt_smoke.json`. Đây là phép thử dịch văn bản đồng thời; không phải phép đo latency phụ đề trên Chrome, không phải so sánh kiểm soát với bản cũ và không khẳng định mọi request sẽ nhanh như vậy.

## Thử lại và giới hạn

Tải lại `/live` bằng Ctrl+F5 để nạp JavaScript mới. Nếu server đã có `incremental_asr_enabled`, không cần khởi động lại vì bản này chỉ sửa frontend.

Video vẫn phát trực tiếp. Tổng độ trễ gồm thời gian ASR ổn định, ASR, MT và hàng đợi; hai request đồng thời giảm chờ, không rút ngắn thời gian mạng của từng request. Cần kiểm tra Chrome thực tế. Nếu người dùng cần hình và phụ đề khớp nhau thay vì phát sát nguồn, bước tiếp theo là chế độ có bộ đệm trễ cho video, được ghi rõ đánh đổi; hiện chưa triển khai chế độ đó.
