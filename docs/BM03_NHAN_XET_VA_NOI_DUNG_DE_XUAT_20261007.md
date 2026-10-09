# Rà soát bản đăng ký BM03 đã điền

Ngày rà soát: 07/10/2026.

Tài liệu được đọc trực tiếp: `1.BM03_Ban dang ky de tai NCKH SV_DIEN_SAN.doc`. File `extracted_bm03.txt` cũ chỉ chứa mẫu trống nên không được dùng để nhận xét bản đã điền. Nội dung được trích từ WordDocument/Table stream; chưa kiểm tra trực quan bố cục trang hoặc chữ ký. File gốc được giữ nguyên.

## Kết luận

**Nên chỉnh phần nội dung nghiên cứu và sản phẩm dự kiến trước khi nộp.** Bản đăng ký đã có cấu trúc và hướng đi phù hợp, nhưng đang kết hợp nhiều mục tiêu kỹ thuật với các cam kết định lượng chưa có bằng chứng. Phạm vi nghiên cứu nên tập trung vào lựa chọn ngữ cảnh OCR cho phụ đề video bài giảng/thuyết trình Anh–Việt. Streaming và website là thành phần hệ thống phục vụ đánh giá; hiệu quả policy là giả thuyết cần kiểm chứng.

Đây là đăng ký nghiên cứu nên được phép nêu mục tiêu chưa đạt. Điều cần chỉnh là cách diễn đạt: tách mục tiêu dự kiến khỏi kết quả đã xác nhận, xác định điều kiện đo và giữ quy mô khả thi.

## Những phần nên sửa

| Vị trí | Nội dung hiện tại | Nhận xét và đề xuất |
|---|---|---|
| Tên đề tài | Hệ thống dịch video trực tuyến… thời gian thực… ngữ cảnh đa phương thức thích ứng | Có thể giữ nếu hồ sơ đã duyệt và phần phạm vi được làm rõ. Nếu đang đăng ký mới, tên nhấn vào lựa chọn OCR và ràng buộc độ trễ phản ánh đóng góp rõ hơn. Không tự thay tên trong hồ sơ đã ký/duyệt. |
| Nội dung 1 | “trần trễ cabin (< 1.500ms)” | Chưa có nguồn xác lập đây là chuẩn cabin. Đổi thành ngân sách độ trễ mục tiêu, định nghĩa điểm đầu/cuối đo. Có thể khảo sát 1.5/3/5 giây trên dev nếu phù hợp, khóa trước test. |
| Nội dung 1 | RTX 3050 <= 3.8GB | Là giới hạn triển khai cần kiểm kê và chốt trên máy đích, không phải thông số chung của mọi RTX 3050. Ghi phần cứng thực nghiệm và theo dõi RAM/VRAM, chưa cam kết một trần không có benchmark. |
| Nội dung 2 và sản phẩm 3 | “150 video” nhưng sản phẩm “150 video clip” | Chưa nhất quán đơn vị. Đề xuất 150–200 **đoạn trích**, dự kiến từ ít nhất 10 video/bài nói độc lập; quy mô chốt sau pilot và nguồn lực. Mỗi nguồn có thể chứa nhiều đoạn, split theo nguồn. Đây là đề xuất thay đổi quy mô, không phải dữ liệu đã có. |
| Nội dung 2 | “Gán nhãn chuyên gia”, “bản dịch tham chiếu chuẩn” | Chưa xác nhận có chuyên gia hoặc quy trình chuẩn hóa. Đổi thành gán nhãn theo hướng dẫn, reference được kiểm tra bởi người có năng lực Anh–Việt; ghi kiểm tra chéo và xử lý bất đồng. |
| Nội dung 3 | Chunk 250–300ms “đạt RTF <= 0.1” | Kết quả trên audio dài không bảo đảm cho chunk ngắn. Giữ như cấu hình khảo sát, đo WER/RTF/lag; không khóa mức đạt trước khi thử nghiệm. |
| Nội dung 4 | Detector <2ms, lookup “xấp xỉ 0ms” | Có thể nêu mục tiêu nhưng không dùng để đại diện độ trễ thị giác. Đo frame sampling/acquisition, detector, OCR, queue và lookup riêng. Cache không xóa chi phí OCR. |
| Nội dung 5 | Nháp tức thì <350ms | Chưa xác định từ lúc thu âm, hết chunk hay hoàn thành ASR. Đổi thành đo first-draft/commit lag có mốc thời gian và miss rate. |
| Nội dung 5 | Tự sửa câu trước khi gặp liên từ/đại từ nối | Trigger chỉ là heuristic, không bảo đảm sửa đúng. Xem revision là cơ chế phụ, có state nháp/chốt và đo flicker; giữ cùng thiết lập giữa các arm policy. |
| Nội dung 6 | “bảo toàn chuẩn xác” thương hiệu/thuật ngữ | Đây là mục tiêu, không bảo đảm. Đổi thành “hỗ trợ bảo toàn thuật ngữ; đánh giá lỗi thuật ngữ, thiếu ý và thêm ý”. Bỏ ví dụ gắn một keynote khỏi mô tả tổng quát. |
| Nội dung 7 | Chỉ audio-only và always-multimodal | Bổ sung audio có cùng text context/cleaning và scene-triggered OCR. Đây là baseline cần có để đánh giá lợi ích tăng thêm của policy. |
| Nội dung 7 | BLEU, COMET, AL là “metric chuẩn quốc tế” | Ghi metric thường dùng, điều kiện áp dụng và phiên bản. Bổ sung đánh giá người, p50/p95 lag, deadline misses và số OCR/MT calls. AL chỉ dùng khi có read/write stream và alignment phù hợp. |
| Nội dung 7 | Tiết kiệm VRAM/GPU | OCR/ASR hiện có thể chạy CPU; VRAM không phản ánh toàn bộ cost. Bổ sung OCR calls/min, CPU time, RAM, thời gian OCR, token/API usage khi có. |
| Nội dung 8 | WebSocket full-duplex | Đây là lựa chọn kỹ thuật, không phải đóng góp nghiên cứu. Nêu website theo dõi xử lý và xuất kết quả; chọn SSE/WebSocket khi triển khai theo yêu cầu luồng. |
| Sản phẩm 4 | Một bản thảo định hướng công bố | Có thể giữ dưới dạng bản thảo dự kiến; không cam kết bài được chấp nhận. Phải dựa trên dữ liệu thực và phản ánh cả kết quả âm. |
| Phần đơn vị | “KHOA CÔNG NGHỆ THÔNG TIN” và “KHOA/VIỆN Công Nghệ Phần Mềm” | Cần kiểm tra đơn vị quản lý chính thức của hồ sơ; không tự coi ngành/chuyên ngành là tên khoa. Thống nhất một tên đúng theo yêu cầu của trường. |
| Ngày tháng, thông tin cá nhân/chữ ký | Ngày 06/10/2026, các trường đã điền | Giữ thông tin người thực hiện/GVHD; người dùng tự kiểm tra tính đúng. Không đổi ngày hoặc chữ ký khi chưa xác định ngày ký/nộp. Dòng ký GVHD trong text thiếu ngoặc mở; kiểm tra trên bản Word xem cần sửa “(ký và ghi rõ họ tên)”. |

## Nội dung thay thế có thể đưa vào BM03

### Ô TÊN ĐỀ TÀI — phương án đề xuất nếu đang đăng ký mới

**Tiếng Việt:** Nghiên cứu cơ chế lựa chọn ngữ cảnh OCR thích ứng cho dịch phụ đề video bài giảng Anh–Việt dưới ràng buộc độ trễ.

**Tiếng Anh:** Adaptive OCR Context Acquisition for English–Vietnamese Lecture Video Subtitle Translation under Latency Constraints.

Nếu tên cũ đã được giảng viên/trường duyệt, có thể giữ tên cũ và dùng nội dung dưới đây để xác định phạm vi: video có slide, phụ đề Anh–Việt, ngữ cảnh thị giác chủ yếu là chữ được OCR, đánh giá online bằng replay đầu vào tăng dần. Live capture là bước mở rộng, không coi phát lại phụ đề đã xử lý trước là luồng trực tiếp.

### Ô NỘI DUNG NGHIÊN CỨU — bản đề xuất

1. Khảo sát các phương pháp dịch đồng thời, dịch có ngữ cảnh thị giác và lựa chọn thông tin bổ trợ. Xác lập câu hỏi nghiên cứu: lựa chọn ngữ cảnh OCR thích ứng có thể giảm lượng xử lý thị giác mà vẫn duy trì chất lượng dịch phụ đề Anh–Việt trong ngân sách độ trễ xác định hay không? Phạm vi tập trung vào video bài giảng/thuyết trình có slide; không mặc định ngữ cảnh thị giác luôn hữu ích.

2. Xây dựng bộ dữ liệu đánh giá gồm transcript, mốc thời gian, frame tương ứng, chữ slide được kiểm tra, bản dịch tham chiếu và nhãn mức độ hữu ích dự kiến của ngữ cảnh thị giác. Dự kiến 150–200 đoạn trích từ ít nhất 10 video/bài nói độc lập; quy mô được chốt sau thử nghiệm thăm dò và xác nhận nguồn lực. Thực hiện kiểm tra chéo một phần nhãn/reference, ghi nguồn và điều kiện sử dụng, chia tập theo nguồn để hạn chế rò rỉ dữ liệu.

3. Thực hiện thử nghiệm thăm dò với ba điều kiện: transcript và ngữ cảnh câu trước; bổ sung chữ slide chép thủ công; bổ sung OCR thật trên cùng frame. Giữ nguyên engine và chỉ dẫn dịch để đánh giá giá trị của chữ slide và ảnh hưởng của lỗi OCR trước khi xây dựng chính sách thích ứng.

4. Xây dựng pipeline nhận dạng lời nói, phát hiện đổi slide, OCR và cache ngữ cảnh. Cache lưu nguồn, thời điểm frame, thời điểm kết quả OCR khả dụng và thời hạn sử dụng; hệ thống không dùng thông tin tương lai trong đánh giá online. Đo riêng thời gian thu nhận/xử lý, chờ hàng đợi và tra cứu cache trên cấu hình phần cứng thực nghiệm.

5. Thiết kế và đánh giá bộ điều khiển lựa chọn ngữ cảnh dựa trên dấu hiệu tham chiếu thị giác trong lời nói, độ mới của cache, thay đổi slide và ngân sách độ trễ còn lại. Chính sách quyết định dịch bằng văn bản, dùng OCR đã có hoặc yêu cầu OCR mới; có phương án dự phòng khi evidence chưa sẵn sàng. Trọng số/ngưỡng được chọn trên tập phát triển và khóa trước khi đánh giá tập kiểm tra.

6. Tích hợp một engine dịch thật nhận cùng transcript và ngữ cảnh văn bản giữa các phương pháp. Quản lý phụ đề nháp/chốt; cơ chế sửa phụ đề, nếu triển khai, được đánh giá riêng về độ đúng và mức thay đổi nội dung. Không dùng đầu ra giả lập làm bằng chứng chất lượng hoặc độ trễ dịch thật.

7. So sánh chính sách đề xuất với audio có cùng ngữ cảnh văn bản, OCR thường xuyên và OCR khi đổi slide; bổ sung lấy mẫu cố định hoặc đối chứng khác theo kết quả khảo sát tài liệu. Đánh giá độ đúng bởi người có năng lực Anh–Việt, lỗi thuật ngữ/thiếu ý/thêm ý và metric tự động phù hợp; đo p50/p95 độ trễ phụ đề, tỷ lệ trễ hạn, số lần OCR/dịch và tài nguyên sử dụng. Phân tích paired trên cùng đầu vào, báo số nguồn độc lập và giới hạn của kết quả; sử dụng Average Lagging khi giao thức dịch tăng dần đáp ứng điều kiện tính metric.

8. Xây dựng website phục vụ upload/replay video, quan sát phụ đề song ngữ, ngữ cảnh đã sử dụng, trạng thái xử lý và xuất log/kết quả. Kiểm tra tính tái lập của thực nghiệm, phân tích các trường hợp OCR có ích hoặc gây hại, hoàn thiện báo cáo NCKH và bản thảo bài báo dựa trên kết quả thực tế.

### Ô SẢN PHẨM DỰ KIẾN — bản đề xuất

1. Một ứng dụng web thử nghiệm dịch phụ đề video bài giảng/thuyết trình Anh–Việt, hỗ trợ chạy các phương pháp đối chứng, hiển thị ngữ cảnh sử dụng và xuất kết quả. Khả năng xử lý tăng dần và giới hạn độ trễ được kiểm chứng bằng log thực nghiệm.

2. Bộ mã nguồn pipeline nhận dạng lời nói, OCR/cache, bộ điều khiển lựa chọn ngữ cảnh và engine dịch; kèm cấu hình, phiên bản phụ thuộc, hướng dẫn triển khai và chạy lại thực nghiệm.

3. Một bộ dữ liệu đánh giá dự kiến 150–200 đoạn trích từ ít nhất 10 video/bài nói độc lập, kèm transcript/reference được kiểm tra, nhãn ngữ cảnh thị giác, manifest và quy trình gán nhãn. Việc chia sẻ video hoặc annotation tuân theo điều kiện sử dụng của nguồn; quy mô chốt sau pilot.

4. Một báo cáo tổng kết NCKH sinh viên, kèm bảng/biểu đồ so sánh chất lượng–độ trễ–chi phí, log và phân tích giới hạn; một bản thảo bài báo khoa học dự kiến trên cơ sở kết quả thu được.

## Ghi chú trước khi chốt

- Quy mô 150–200 đoạn/ít nhất 10 nguồn là **phương án đề xuất mới**, không phải quy mô đã xác nhận với giảng viên. Đợt hiện tại mới chuẩn bị 24 candidate từ một nguồn, chưa có gold hoặc bản dịch A/B/C thật.
- Nếu hồ sơ đã được phê duyệt tên hoặc quy mô, đối chiếu quy trình sửa của trường/GVHD trước khi thay bản chính thức. Bản này chỉ cung cấp nội dung để review.
- BM03 là bảng đăng ký tóm tắt. Nếu ô quá dài, chuyển chi tiết protocol, metric, schema và cấu hình sang thuyết minh; giữ câu hỏi nghiên cứu, phương pháp chính và sản phẩm trong BM03.
- Chưa biết hạn thực hiện, ngân sách API, người kiểm tra reference và yêu cầu live capture/dubbing bắt buộc. Những mục này ảnh hưởng đến mức cam kết cuối cùng.
- Nội dung trích xuất cho phép rà soát ý nghĩa, chưa cho phép kết luận ô bảng tràn trang, cỡ chữ, căn lề hoặc bố cục chữ ký đúng.
