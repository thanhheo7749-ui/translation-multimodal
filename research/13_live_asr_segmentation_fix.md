# Sửa nhận dạng bị mất từ ở luồng live

Ngày: 08/10/2026. Người dùng báo tiếng Anh nhận thiếu từ, dẫn tới bản dịch Việt sai.

## Lỗi tái hiện

Dùng 40 giây đầu của tệp NVIDIA, giải mã thành PCM mono 16 kHz rồi đưa từng gói 20 ms qua chính `frontend/live-core.js`. Mỗi đầu vào ASR chỉ chứa các gói đến thời điểm đóng đoạn. Đây là mô phỏng bằng tệp để kiểm tra phân đoạn/ASR, chưa đo đường thu âm trong Chrome.

Cấu hình cũ giới hạn 2,5 giây, khoảng nghỉ 500 ms, đoạn tối thiểu 800 ms. Câu đầu bị tách thành `My release` và `relationship with you started here.` Các đoạn sau cũng bị tách thành `This is in a lot of ways.`, `the beginning.`, `of the modern computer industry 40 years.`, `Now`. Cắt lời nói sớm làm mất ngữ cảnh âm thanh và tạo các bản dịch rời rạc. Hàng đợi còn có thể bỏ đoạn nếu xử lý không kịp; UI đã có bộ đếm riêng cho trường hợp đó.

## Thay đổi

- Mặc định chờ khoảng nghỉ 800 ms, tối thiểu 2 giây, tối đa 8 giây. Có chế độ 10 giây cho câu dài hoặc 4 giây nếu muốn thử đánh đổi tốc độ.
- Whisper dùng beam size 5 và temperature 0 thay vì beam size 1. Giữ model local đang có để so sánh cùng nguồn audio.
- Chưa thay đổi cơ chế thu âm, giới hạn hàng đợi hoặc mô hình dịch. Không thêm transcript của video vào prompt ASR.

## Kết quả kiểm tra

Trong cùng 40 giây, cấu hình cũ tạo 17 đoạn, cấu hình mới tạo 6 đoạn. Cấu hình mới nhận được câu đầu `My relationship with you started here.` và câu dài kế tiếp gồm cả `... here in Taiwan, your companies started here.` ASR cấu hình mới trong phép thử khoảng 550–995 ms mỗi đoạn. Thời gian này không bao gồm chờ thu đủ lời nói hoặc dịch.

Đầu vào/phân đoạn và kết quả trước–sau ở `experiments/runtime_logs/asr_debug/`. Không có transcript chuẩn được duyệt để tính WER; những ví dụ này chưa xác nhận mọi câu đều đúng. Câu nói liên tục dài hơn giới hạn vẫn có thể bị cắt; chồng âm thanh 100 ms vẫn có thể gây lặp từ ở biên.

Kiểm tra hồi quy bao gồm giữ nguyên một cụm có khoảng nghỉ 500 ms giữa câu và đóng đoạn khi đạt giới hạn 8 giây. Các kiểm tra PCM, resample, endpoint và hàng đợi tiếp tục đạt.

## Thử lại

Dừng server cũ, mở lại `run_studio.cmd`, tải lại `/live` và để tùy chọn **8 giây · ưu tiên đủ câu**. Phát video NVIDIA từ đầu. Kiểm tra tiếng Anh trước tiếng Việt và theo dõi **Đoạn bỏ qua**. Bản sửa tăng thời gian chờ lời nói để giữ đủ cụm; chưa phải nhận dạng liên tục từng từ với bản nháp có thể chỉnh sửa.
