# Pilot A/B/C — cách thực hiện và trạng thái hiện tại

Ngày chuẩn bị: 07/10/2026. Skill `nature-statistics` được áp dụng để giữ nguồn video là đơn vị độc lập và tách preparation/dry-run khỏi kết quả chất lượng. Website chưa được thay đổi.

## Mục tiêu của đợt này

Kiểm tra ngữ cảnh chữ slide có giúp dịch hay không, sau đó kiểm tra OCR có thu được lợi ích đó không. Cùng engine, cùng instruction, cùng transcript và câu trước; chỉ thay `slide_text`:

| Arm | Input |
|---|---|
| A | Transcript kiểm tra thủ công + câu trước; chữ slide rỗng |
| B | Như A + chữ đọc được từ frame, chép thủ công và xác minh |
| C | Như A + OCR thật trên cùng frame, toàn bộ text blocks, không chọn riêng từ khớp lời nói |

Đây là diagnostic **offline**, không phải mô phỏng streaming hoặc benchmark deadline. B cung cấp chữ slide chuẩn; không phải oracle chất lượng dịch. Slide không có chữ là một trường hợp hợp lệ: B rỗng, không tự thêm mô tả ảnh.

## Những gì đã thực hiện

- Video có sẵn: 1026.55 giây, một nguồn; SHA-256 lưu trong manifest.
- Chọn trước năm cửa sổ 30 giây bắt đầu tại 0, 110, 280, 580, 850 giây; lấy tối đa năm segment đầu mỗi cửa sổ. Không chọn theo bản dịch tốt/xấu.
- ASR thật `base.en`, CPU INT8, beam=1 từ model đã cache; không tải model mới.
- Trích **24 audio clip WAV và 24 frame**, OCR thật bằng RapidOCR. Mỗi clip có thêm ba giây trước/sau để người kiểm tra nghe ngữ cảnh; transcript mục tiêu là segment ghi trong manifest.
- OCR đo trong đợt chuẩn bị: median **935.57 ms**, min **283.42 ms**, max **1738.96 ms**, bảy frame không trả text. Đây là thời gian OCR của các frame này; chưa phải p95 production hoặc tốc độ hệ thống live.
- Tám candidate chạm biên cửa sổ ASR, có cảnh báo trong review. Chưa xác minh transcript, chữ slide hoặc reference nào.
- Chạy dry-run tạo **72 prompt A/B/C**, không gọi dịch và không tạo điểm chất lượng.
- Chưa có `GEMINI_API_KEY` trong môi trường chạy khi kiểm tra. Provider Gemini thật đã được triển khai trong runner nhưng chưa gọi; local backend của website hiện không được dùng làm provider pilot.

Đợt này là **chuẩn bị feasibility từ một nguồn**. Để thành pilot 3–5 nguồn như kế hoạch, bổ sung video độc lập và chuẩn bị theo cùng quy tắc; thêm câu từ cùng keynote không làm tăng số nguồn độc lập.

## Bước 1: kiểm tra dữ liệu

Mở `data/pilot_abc/source01/review.html` trong trình duyệt. Trang hoạt động bằng file local, không cần chạy website. Mỗi thẻ có frame, đoạn nghe và các trường:

1. Nghe và sửa transcript mục tiêu; kiểm tra cả câu trước. Draft là ASR, không tự coi là gold.
2. Chép chữ đọc được trên frame trước khi mở phần OCR. Không thêm thông tin từ các slide khác hoặc lời diễn giả vào trường này.
3. Viết/kiểm tra reference tiếng Việt độc lập trước khi xem output A/B/C; phải có ngữ cảnh đúng. Có thể nhờ người song ngữ khác kiểm tra, ghi ID người thực hiện thực tế.
4. Gán nhãn `not_needed`, `useful`, `misleading`, `uncertain`. Đây là phán đoán annotation, chưa phải kết luận OCR cải thiện dịch.
5. Tích ba ô xác nhận chỉ sau khi kiểm tra. Nhập annotator ID.
6. Với đoạn chạm biên: kiểm tra ASR bị cắt hoặc timestamp vượt cửa sổ; sửa transcript/mốc trong JSON nếu cần. Có thể loại candidate không đánh giá được trước run, ghi segment_id và lý do trong exclusion log; không loại theo kết quả dịch.
7. Xuất `manifest.reviewed.json`, lưu **cùng thư mục với manifest.draft.json** để các đường dẫn frame/audio vẫn đúng. Nút lưu nháp chỉ lưu vào trình duyệt, không sửa file trên đĩa.

Gold không nên được xác nhận từ transcript cũ hoặc từ kết quả OCR tự động. Tôi chưa nghe/đánh giá độc lập các clip nên để toàn bộ verification flags là false.

Kiểm tra dữ liệu trước chạy, trong PowerShell tại thư mục gốc:

```powershell
.\.venv\Scripts\python.exe experiments/pilot_abc.py validate --manifest data/pilot_abc/source01/manifest.reviewed.json
```

Lệnh chỉ báo ready khi các trường kiểm tra bắt buộc đã đầy đủ. Đây là kiểm tra schema/xác nhận, không thay người đánh giá tính đúng của gold.

## Bước 2: chọn và cấu hình provider thật

Runner hiện hỗ trợ Gemini qua HTTP chính thức. Chọn model có quyền truy cập trong API project; truyền `--model` rõ ràng, không mặc định một tên model chưa kiểm tra khả dụng. Cấu hình `GEMINI_API_KEY` trong môi trường của tiến trình chạy và giữ khóa trên máy, không đưa vào manifest/report/chat.

Nguồn kỹ thuật: [Google generateContent API](https://ai.google.dev/api/generate-content), đối chiếu ngày 07/10/2026. Request gửi key bằng header; lỗi chỉ lưu type/status, không lưu URL hoặc exception body có thể chứa credential. Không retry tự động để tránh biến đổi ngân sách và che lỗi. Max output tokens=2048, temperature=0; model có thể vẫn không deterministic, run ID và version được lưu.

Sau khi dữ liệu được xác minh và key đã cấu hình:

```powershell
.\.venv\Scripts\python.exe experiments/pilot_abc.py run --manifest data/pilot_abc/source01/manifest.reviewed.json --output experiments/runs/pilot_abc_source01_real_01 --model TEN_MODEL_TRONG_API_PROJECT
```

Thay tên model bằng cấu hình thực tế. Với 24 đoạn, lệnh lập kế hoạch **72 API calls**, chạy tuần tự theo thứ tự xáo trộn cố định. Output directory phải mới; runner không ghi đè run cũ. Có lỗi vẫn lưu record và trả exit code khác 0. Không có key hoặc gold chưa kiểm tra thì không gửi request.

Chỉ dùng local model nếu đã có engine suy luận thật hỗ trợ cùng prompt và logging; không dùng skeleton LocalLLMTranslator để tạo dữ liệu nghiên cứu. Nếu chọn local, cần bổ sung adapter rồi kiểm tra trước run.

## Bước 3: chấm mù và đọc kết quả

Sau run thật, `blind_scores.csv` chứa output thành công đã xáo trộn và ẩn arm. `PRIVATE_arm_mapping.json`, prompts và outputs.jsonl giữ cho người tổng hợp, không gửi cho người chấm. Không thể đảm bảo người chấm không đoán được arm từ nội dung; báo rõ giới hạn.

Mỗi row nhập rater ID, adequacy 1–5 và số lỗi thuật ngữ/thiếu ý/thêm ý/sai tham chiếu. Anchor đề xuất cho adequacy: 5=giữ đủ ý chính, không lỗi nghĩa đáng kể; 4=lỗi nhỏ không đổi ý chính; 3=hiểu được nhưng có một lỗi nghĩa quan trọng; 2=thiếu/sai nhiều ý; 1=không truyền đạt ý mục tiêu. Chốt rubric trước chấm; tránh chấm chỉ độ trôi chảy.

Thống kê descriptive paired:

```powershell
.\.venv\Scripts\python.exe experiments/pilot_abc.py summarize --run-dir experiments/runs/pilot_abc_source01_real_01 --scores experiments/runs/pilot_abc_source01_real_01/blind_scores.csv --output experiments/runs/pilot_abc_source01_real_01/quality_descriptive.json
```

Chỉ tổng hợp triplet A/B/C được chấm đầy đủ, báo coverage và số nguồn. Kiểm tra generation failures ở summary.json; không biến missing output thành điểm tốt hoặc im lặng bỏ lỗi. Không tạo p-value hoặc kết luận tương đương từ một nguồn.

- B−A có ích: evidence chữ slide có tiềm năng, cần xem lỗi cụ thể và xác nhận trên nguồn khác.
- C−B kém: OCR/độ đầy đủ text là bottleneck cần điều tra.
- C−A không có lợi: xem OCR và loại ca; chưa đủ lý do tăng độ phức tạp policy.
- B gây thêm ý: kiểm tra alignment/prompt/reference; evidence có thể gây hại.

## Chuẩn bị nguồn mới

```powershell
.\.venv\Scripts\python.exe experiments/pilot_abc.py prepare --video data/raw_videos/VIDEO_MOI.mp4 --output data/pilot_abc/source02 --offsets 0 60 120 --window-sec 30 --per-window 5
```

Chọn offsets phù hợp độ dài video trước khi xem output. Output mới có manifest, frame, audio và review page riêng. Có thể chạy từng nguồn rồi tổng hợp per-source; tuyệt đối không coi mỗi run/segment là một nguồn độc lập.

Hai nguồn đọc bổ sung để định hướng thiết kế: [Vision Matters When It Should](https://aclanthology.org/2021.emnlp-main.673/) nhấn mạnh benchmark phải làm rõ sự đóng góp visual; [Tackling Ambiguity with Images](https://aclanthology.org/2023.acl-long.295/) nghiên cứu ambiguity và contrastive evaluation. Đã đối chiếu abstract/metadata, chưa claim reproduction hoặc full-paper review. Các bài dùng image context, không tự chứng minh OCR hữu ích cho Anh–Việt.
