# SPEC + PLAN: Phụ đề bám sát lời nói, nền mờ và OCR slide trực tiếp

Ngày: 2026-10-10. Trạng thái: bàn giao cho AI triển khai; chưa phải báo cáo đã triển khai hoặc benchmark.

> Sửa theo phản hồi người dùng: ưu tiên theo kịp lời nói hơn giảm số lần đổi chữ. Hủy đề xuất đóng băng câu, giữ 1,2–3 giây, xếp hàng để đọc và chỉ cho sửa phụ đề trong chế độ thử nghiệm. Nếu giảm chữ nhảy làm phụ đề chậm hơn thì giữ hành vi cập nhật hiện tại. Đây là yêu cầu mới nhất, ưu tiên hơn các bản spec trước.

## 1. Mục tiêu và thứ tự ưu tiên

Người dùng đánh giá local đã nhanh và theo kịp lời nói, nhưng chữ thay đổi liên tục khó đọc và nền phụ đề chưa tạo hiệu ứng mờ mong muốn. Yêu cầu tiếp theo là đọc slide bằng OCR để bổ sung ngữ cảnh.

Thứ tự: bảo toàn tốc độ hiện có → giảm rung bố cục nếu không thêm độ trễ → nền dễ đọc → thu hình slide → OCR nền → dùng ngữ cảnh có kiểm soát → đánh giá nghiên cứu. Chưa giảm được chữ nhảy không phải lý do chặn việc triển khai OCR.

Tài liệu bổ sung cho `SPEC_LIVE_SUBTITLES_LOCAL_FIRST.md`. Với hành vi hiển thị/correction và OCR, ưu tiên kết quả mới hợp lệ theo segment/revision; được cập nhật câu đang xem, không cố tình trì hoãn để người dùng đọc đủ câu cũ; OCR không chặn bản local. Không triển khai lại những phần spec cũ đã hoàn thành.

Phạm vi là viết/sửa ứng dụng hiện có. Không thay model ASR/MT, tăng audio chunk, thêm dịch vụ cloud bắt buộc, extension hay desktop app chỉ để xử lý flicker hoặc blur.

## 2. Hiện trạng đã đọc từ code, cần kiểm tra lại trước khi sửa

- `frontend/live.js`: PiP đã dùng `TranscriptPair.select()` và DOM `#en`, `#vi`; khác bản trước dùng feed. Không áp dụng lại kết luận test/markup cũ mà chưa đối chiếu.
- `frontend/live-core.js`: `TranscriptPair` và `CaptionPresenter` giữ tham chiếu row có thể bị sửa; thời gian giữ tối thiểu hiện khoảng 900 ms. Đây là quan sát về code, không phải yêu cầu đóng băng row hay tăng thời gian giữ. Không mặc định coi mọi lần sửa nội dung là lỗi.
- `renderVideoCaption()` gán lại `textContent`; timeline `replaceChildren()` mỗi render. Cần đo mutation và phân biệt đổi dữ liệu, đổi cue, xuống dòng, rebuild DOM trước khi kết luận nguyên nhân flicker.
- `frontend/floating.css` đã có `backdrop-filter` trên html/body; `.video-captions p` trong `frontend/live.css` hiện dùng nền đen alpha 0.82, chưa có blur tại vùng chữ trên video.
- `backend/vision/scene_detector.py`: detector histogram + pixel difference; cooldown chưa phải xác nhận frame ổn định sau chuyển cảnh.
- `backend/vision/slide_pipeline.py`: có RapidOCR và cache, lọc score >= 0.6, heuristic tiêu đề có từ khóa NVIDIA/keynote. Chưa nên dùng heuristic thiên về video mẫu làm thuật toán tổng quát.
- `VisualMemoryCache` hiện lưu một slide, chưa có lịch sử timestamp/session, nên không đủ cho OCR bất đồng bộ của live tab.
- Luồng `/live` chưa có endpoint thu frame/OCR slide trực tiếp. Import lớp OCR hoặc test ảnh tĩnh không chứng minh luồng live đã sử dụng OCR.
- `backend/live_pipeline.py` là đường xử lý khác; có chỗ gọi `visual_cache.clear()` dù cache đang đọc chưa định nghĩa `clear`. Không kéo nguyên singleton này vào live tab. Khi tái sử dụng phải sửa/reset rõ ràng và kiểm tra cache/detector cùng vòng đời.
- `requirements.txt` ghim `rapidocr-onnxruntime==1.4.4`. Không lấy API của RapidOCR bản mới áp thẳng vào bản này.
- Compose hiện yêu cầu cả Whisper và NLLB chạy CUDA; runtime có thể fallback. Đo thiết bị thực tế khi khởi động, không dùng lại giả định Whisper CPU từ báo cáo cũ.

Các điểm trên là đọc mã; chưa có phép đo browser chứng minh tỷ lệ flicker hoặc tốc độ OCR trên máy này.

## 3. Quyết định về phụ đề: ưu tiên kết quả mới, không thêm thời gian chờ

### 3.1 Trạng thái hiển thị có phiên bản

1. `RecognitionDraft`: tiếng Anh đang nhận dạng; được sửa, nằm ở vùng nhỏ riêng, mặc định có thể ẩn trong PiP.
2. `TranslationRecord`: bản local/correction và source revision; lưu đầy đủ trong timeline/log.
3. Trạng thái hiển thị: cặp nguồn–đích được chọn theo session, segment và revision, cho phép cập nhật khi có kết quả mới hợp lệ. Không bắt buộc thêm lớp DisplayCue hay viết lại scheduler chỉ để thực hiện yêu cầu này.

Thông tin cần có hoặc ánh xạ được từ cấu trúc hiện tại:

```text
session_id, segment_id, source_revision, translation_revision
source_text, translated_text, provider
audio_start_sec, audio_end_sec
ready_client_ms, shown_client_ms, hidden_client_ms
```

Mỗi lần render đọc một cặp EN–VI nhất quán theo revision. Có thể copy dữ liệu để tránh đọc trạng thái đang thay đổi, nhưng bản copy phải được cập nhật khi có revision hợp lệ mới; không dùng snapshot để khóa nội dung suốt một khoảng thời gian.

### 3.2 Quy tắc cập nhật

- Cập nhật cả cặp EN–VI khi bản dịch mới hợp lệ sẵn sàng; không ghép source revision mới với bản dịch của source revision cũ. Tiếng Anh mới chưa có bản dịch có thể hiện ở dòng đang nghe riêng.
- Giữ cơ chế cập nhật tăng dần hiện tại; không ép chờ đủ câu dài hoặc dấu chấm chỉ để giảm thay chữ. Không thêm hiệu ứng đánh máy làm chậm kết quả đã có.
- Dòng ASR nháp được cập nhật nhưng không làm đổi kích thước vùng bản dịch chính.
- Khi correction đến và vẫn khớp segment/source revision đang hiển thị: được cập nhật nội dung ngay theo cơ chế render hiện có. Không khóa local mới để chờ correction và không cho response local cũ ghi đè correction mới.
- Khi đã chuyển sang segment mới hơn: correction của segment cũ chỉ cập nhật timeline/log; không đưa màn hình quay về câu cũ.
- Không bắt người dùng bật chế độ thử nghiệm mới được sửa chữ đang hiển thị. Thay đổi nội dung để bám lời nói là hành vi được chấp nhận.
- Không dùng việc tiếng Việt có prefix chung để chốt từng từ như ASR; dịch Anh–Việt có thể đổi trật tự từ.

### 3.3 Ngân sách hiển thị: không thêm bộ đệm đọc

- Không triển khai `hold_min_ms = 1200`, công thức thời gian đọc theo độ dài, `max_ready_wait_ms = 3000` hoặc hàng đợi hiển thị hai cue từ bản spec trước.
- Không tăng thời gian giữ khoảng 900 ms hiện có; chưa có bằng chứng cải thiện thì giữ policy hiện tại. Việc giảm/bỏ thời gian giữ cũ là thí nghiệm riêng, không làm đồng thời với tích hợp OCR.
- Không debounce/throttle kết quả dịch mới hàng trăm mili giây để giảm flicker; chỉ tránh cập nhật trùng nội dung hoặc gộp cập nhật trong cùng lượt render mà không đợi timer mới.
- Khi chưa có bản dịch mới, có thể giữ cặp hợp lệ gần nhất theo hành vi hiện tại; khi kết quả mới đến thì không bắt nó chờ đủ thời gian đọc. Không xóa rồi chèn lại cùng một câu.
- Không chia câu thành các trang tự chạy có thời gian chờ. Câu dài dùng vùng hiển thị responsive hoặc lịch sử có thể xem lại; không tự giảm font hay che mất nội dung khỏi log.
- Không tạo hàng đợi phụ đề FIFO chỉ để hiển thị lại mọi kết quả đã quá cũ. Giữ cơ chế ưu tiên bắt kịp hiện có, ghi log mọi đoạn bỏ hiển thị để đo cùng latency.

Chấp nhận nội dung thay đổi nếu đó là cập nhật cần thiết để theo lời nói. Nếu tối ưu không có lợi hoặc tạo cảm giác chậm hơn, rollback riêng phần chống nhảy và giữ renderer hiện tại; tiếp tục các phase nền/OCR.

### 3.4 Layout và DOM

- Cố định vị trí và chiều rộng khung; căn chữ trái, tránh text-align center làm mép chữ dao động khi câu dài/ngắn.
- Dành vùng VI tối thiểu hai dòng, vùng EN riêng; dành trước chiều cao draft hoặc cho người dùng ẩn hẳn, tránh bật/tắt dòng draft làm khung nhảy.
- Không tự đổi font-size dựa theo độ dài câu. Cho người dùng chọn cỡ chữ; kiểm tra PiP nhỏ và fullscreen.
- Chỉ cập nhật textContent khi giá trị thay đổi. Timeline dùng node theo ID và cập nhật node bị đổi, không rebuild cả danh sách mỗi tick.
- Không `transition: all` trên phụ đề; không animation vị trí/chiều cao hoặc fade chặn nội dung mới. Cập nhật chữ trực tiếp, tôn trọng reduced-motion.
- Cả PiP và phụ đề trên video dùng cùng policy hiển thị, tránh hai bộ chọn cho hai câu khác nhau.

## 4. Nền blur: phân biệt hai bề mặt

### 4.1 Phụ đề đè trên video trong cùng trang

Đặt lớp nền bán trong suốt phía sau chữ, `backdrop-filter: blur(8px)` làm giá trị thử đầu, viền nhẹ, chữ sáng và shadow nhỏ. Chỉ blur nền; không dùng `filter: blur()` lên container chứa chữ. Áp dụng cho vùng subtitle, không blur cả video.

Có fallback nền tối nếu không hỗ trợ hoặc ảnh chụp thực tế không đạt độ tương phản. Đánh giá trên slide trắng, slide tối, video chuyển động và fullscreen. Không duyệt bằng việc chỉ nhìn CSS có thuộc tính blur.

### 4.2 Cửa sổ Document PiP

`backdrop-filter` xử lý backdrop trong nội dung trang; không cấp khả năng nhìn xuyên và làm mờ cửa sổ/tab hệ điều hành phía sau PiP. Nền html/body trong suốt cũng không bảo đảm kính mờ xuyên cửa sổ.

Mặc định dùng nền tối dễ đọc. Tùy chọn sau này: vẽ một ảnh nhỏ từ nguồn video đã được người dùng chia sẻ vào nền PiP rồi blur ảnh đó; đây là nền mô phỏng từ nguồn capture, không phải blur desktop thật. Không thêm tùy chọn này vào MVP vì tạo chuyển động thị giác và tăng công việc render.

Nếu yêu cầu cuối cùng là lớp phủ trong suốt trực tiếp trên YouTube ngoài tab ứng dụng, đánh giá extension/desktop overlay ở scope riêng. Không hứa chỉ thêm CSS sẽ làm được.

## 5. OCR: kiến trúc và phạm vi MVP

```text
Tab/video được người dùng chia sẻ
 ├─ audio → ASR/phân đoạn hiện tại → local MT → cập nhật subtitle
 └─ video → lấy frame thưa → crop slide → phát hiện thay đổi
                                 → đợi cảnh ổn định → OCR CPU
                                 → cache slide theo phiên + thời gian
                                         ├─ panel nội dung slide
                                         └─ context selector → hiệu chỉnh tùy chọn
```

MVP: OCR thật đọc chữ slide vào panel kiểm tra, lưu cache đúng thời điểm và không ảnh hưởng đáng kể tốc độ audio/local MT. Sau khi MVP đạt gate mới nối ngữ cảnh vào dịch.

OCR không phải công cụ hiểu toàn bộ biểu đồ. Không suy ra ý nghĩa mũi tên, quan hệ đồ thị, số liệu không đọc được hoặc nội dung hình không có chữ.

## 6. Thu frame đúng nguồn, đúng thời điểm

### 6.1 Nguồn

- Với tab chia sẻ: tái sử dụng video track từ stream `getDisplayMedia()` đã cấp. Không xin share lần hai cho OCR.
- Tạo video element nội bộ `muted`, `playsInline` để đọc frame; không phát lại âm thanh. Dừng video consumer không được gọi stop lên audio track đang dùng.
- Với video NVIDIA trong trang: vẽ frame từ video đang phát. Không đọc toàn file, không nhảy tới tương lai lấy slide.
- Micro-only không có video: hiển thị “OCR cần nguồn hình”; audio/local MT vẫn hoạt động.
- Chặn/chỉ dẫn khi chọn nhầm chính tab ứng dụng để tránh OCR nhận lại phụ đề do ứng dụng tạo.

### 6.2 ROI (vùng slide)

- Cho chọn khung slide trên ảnh preview; lưu ROI dưới dạng tọa độ chuẩn hóa [0,1]. Mặc định toàn frame nếu người dùng chưa chọn, nhưng có trạng thái chưa tối ưu.
- Map ROI theo kích thước video gốc và xử lý letterboxing/object-fit. Trả bbox OCR trong tọa độ crop kèm transform về nguồn.
- ROI version tăng khi crop hoặc nguồn/kích thước thay đổi. Loại kết quả OCR từ ROI version cũ.
- Không mặc định bỏ 20% dưới hình vì có thể mất chữ slide; chỉ loại vùng subtitle/webcam theo crop/mask có cấu hình.

### 6.3 Scheduler frame

- Mục tiêu kiểm tra thay đổi 2 lần/giây; tối đa một upload đang chờ và một frame mới nhất được giữ. Không OCR 30/60 fps.
- `requestVideoFrameCallback` có thể hỗ trợ timestamp frame. Không giả định nó hoặc timer chạy đủ tần suất khi tab ẩn; cần kiểm tra Chrome foreground/background với PiP mở/đóng. Dùng fallback có feature detection nếu cần, đo frame age và báo stale nếu sampling dừng.
- Không chạy vòng lặp bù hàng chục frame sau khi tab được kích hoạt lại; chỉ lấy frame mới nhất.
- Thumbnail phát hiện thay đổi khoảng 320×180; ảnh OCR crop ban đầu giới hạn cạnh dài 1280 px, có thể tăng 1920 khi chữ nhỏ và ngân sách cho phép. Không phóng ảnh nhỏ rồi coi là có thêm chi tiết.
- JPEG chất lượng khởi đầu 0.85; tối đa 2 MiB và 4 megapixel sau decode. Giới hạn pixel phải kiểm tra ở backend trước inference.

## 7. Phát hiện đổi slide và OCR nền

### 7.1 Pipeline trạng thái

```text
NO_FRAME → CANDIDATE → STABILIZING → OCR_PENDING → READY / EMPTY / ERROR
                          ↑ thay frame → cập nhật candidate
```

- Tái sử dụng detector nhưng bổ sung kiểm tra hai mẫu gần nhau đủ giống trước OCR, đợi khởi đầu 500–800 ms sau thay đổi.
- Cooldown không đủ: fade/animation hoặc người thuyết trình đi lại có thể bị đọc như slide mới. So sánh trong ROI; lấy ảnh rõ, hạn chế nhận frame giữa transition.
- Khi xác nhận candidate mới, đánh dấu cache hiện tại cần xác minh ngay; không chờ OCR xong mới biết slide đã đổi.
- Bổ sung bullet trên cùng slide là revision nội dung, không nhất thiết slide mới. Dùng content hash và overlap văn bản để tránh nhân đôi.
- Dedupe ảnh/text đã OCR; một periodic probe tối đa khoảng 10 giây khi frame tiếp tục đến giúp phát hiện chữ nhỏ/bullet không vượt ngưỡng. Tái OCR có ngân sách, không quét liên tục slide đứng yên.
- Người nói xuất hiện toàn màn hình, slide trắng hoặc OCR không có chữ: cập nhật EMPTY cho cảnh đó và dừng cấp ngữ cảnh slide cũ.

### 7.2 Worker

- Giữ RapidOCR phiên bản đã ghim trước, xác minh API và output. Bắt đầu ONNX Runtime CPU, một worker, giới hạn thread để giữ GPU cho ASR/NLLB; đo runtime thực tế.
- Chỉ nạp model một lần cho worker. Startup/warmup OCR là trạng thái riêng, không chặn nút dịch audio.
- Tối đa một job OCR đang chạy, một candidate chờ mới nhất. Job thay thế không được làm lùi slide state.
- Không giữ HTTP request/lock của ASR hoặc local MT để đợi OCR. Không chạy OCR đồng bộ trong handler dịch.
- OCR timeout/decode fail/missing model: báo OCR unavailable, bỏ job đúng ID và tiếp tục dịch audio-only.
- Không kill shared model/thread đang phục vụ audio. Nếu timeout inference không hủy được, cô lập/restart worker OCR rồi backoff.

### 7.3 Kết quả OCR

- Lưu text gốc, score, bbox, thứ tự đọc và thời gian xử lý. Score OCR không phải xác suất chữ đúng đã được hiệu chuẩn.
- Lọc noise, text lặp; giữ nguyên tên riêng và con số gốc để kiểm tra. Không tự dịch rồi thay text OCR nguồn.
- Tiêu đề dựa vào vị trí/kích thước bbox và bố cục, không ưu tiên từ NVIDIA/keynote. Nếu không đủ chắc, để trống tiêu đề.
- Ngưỡng khởi đầu 0.6 cho panel xem thô; ngưỡng 0.85 và ổn định qua quan sát cho entity dùng vào correction. Cần hiệu chỉnh trên tập slide thực tế.

## 8. Cache và đồng bộ audio–slide

Mỗi snapshot bất biến:

```text
session_id, source_epoch, roi_version, frame_id
scene_generation, slide_id, slide_revision
captured_client_ms, audio_cursor_sec_at_capture, source_media_time_sec?
available_client_ms, server_ocr_ms
status, title, lines[{text, score, bbox}], content_hash
```

- Session ID phải duy nhất giữa các tab trình duyệt. Không dùng singleton cache chung cho mọi client.
- Source epoch đổi khi chuyển nguồn, tua video hoặc bắt đầu lại timeline; reset detector/cache/pending jobs.
- Dùng clock đơn điệu của client và audio sample counter để liên hệ frame với segment. Không trừ trực tiếp `performance.now()` client với `time.time()` server.
- `mediaTime` của capture stream không phải timestamp YouTube gốc; ghi rõ là capture-relative và sai số đo. Với video trong trang có thể lấy timeline của chính video.
- Lưu lịch sử giới hạn, khởi đầu 20 snapshot hoặc tối đa 120 giây; giữ bounds dung lượng, TTL thu hồi session. Slide đứng yên không hết hạn chỉ vì lâu nếu có frame heartbeat cùng cảnh; mất heartbeat khoảng 5 giây thì đánh dấu stale và không cấp làm current context.
- Context của một segment chọn theo khoảng audio của segment, không chọn slide mới nhất ở lúc request đến backend.
- Frame dùng cho lượt dịch đầu phải được quan sát không muộn hơn cuối segment và kết quả OCR đã có trước lúc dispatch dịch. Nếu chưa có, dùng audio-only ngay.
- Correction sau đó chỉ được dùng OCR có frame thuộc thời gian thích hợp của segment; OCR hoàn thành muộn không cho phép dùng slide tương lai. Log riêng correction availability.
- Nếu segment băng qua chuyển slide và không xác định được context đáng tin, audio-only; không ghép hai slide như cùng một ngữ cảnh.
- Response OCR cũ sau chuyển slide có thể lưu lịch sử nhưng không ghi đè current state mới hơn. So sánh cả session, source epoch, ROI version, frame ID và generation.

## 9. Contract API đề xuất

Đây là extension, giữ tương thích `/api/live/translate` và trang test hiện có.

### Nạp frame

`POST /api/live/vision/frame`, multipart gồm `metadata` JSON và `image` binary. Metadata chứa session/epoch/ROI/frame/timestamp/transform; không base64 frame trong JSON nếu không cần.

Trả `202` với `{status: "queued", job_id, session_id, source_epoch, frame_id}` hoặc `{status: "unchanged"}` khi có thể xác định sớm. Parse multipart phải có giới hạn byte và parser được hỗ trợ trong runtime; không tự viết split chuỗi tùy tiện. Thêm dependency nếu cần và ghim phiên bản.

### Nhận kết quả

`GET /api/live/vision/result?session_id=...&job_id=...` trả trạng thái pending/ready/empty/error và snapshot đúng job. Poll có giới hạn/backoff, hoặc dùng transport sẵn có nếu project đã có; không thêm WebSocket chỉ cho một job.

### Ghép ngữ cảnh khi dịch

Request dịch có thể thêm `visual_context_id`, source epoch và timestamp segment. Backend tra cache thuộc đúng session và kiểm tra tính hợp lệ, không tin tùy ý title/entities do browser gửi.

Response/log có `visual_context_available`, `visual_context_used`, `visual_context_id`, `reason`, `matched_entities`. Các giá trị này khác nhau: OCR có text không có nghĩa translator dùng text hoặc chất lượng đã tốt hơn.

OCR frame/text là dữ liệu không đáng tin: render textContent; prompt phải coi OCR là dữ liệu trích dẫn, không thực thi chỉ dẫn trong slide. Giới hạn 20 entity và khoảng 1500 ký tự context khởi đầu. Không gửi toàn frame tới Gemini khi chỉ cần OCR text.

## 10. OCR giúp dịch local như thế nào?

### 10.1 Bản local hiện tại

NLLB hiện không có giao diện hiểu prompt/ngữ cảnh slide. Gửi thêm toàn OCR vào `speech_text` sẽ khiến model dịch cả slide và thay đổi nội dung phụ đề. Không làm việc đó, không bật `context_supported=true` chỉ vì OCR đã chạy.

MVP local: OCR hiển thị slide text/thuật ngữ riêng cho người dùng và lưu vào log; bản dịch local vẫn audio-only. Đây là hoàn thành tích hợp đọc slide, chưa phải chứng minh tăng chất lượng dịch.

### 10.2 Nhánh local có thuật ngữ, làm sau MVP

Có thể thử glossary được kiểm duyệt: tên riêng và dạng viết chuẩn từ slide kết hợp danh sách thuật ngữ người dùng chấp nhận. Chỉ match exact hoặc biến thể đã xác nhận; không tự thay số, từ thông thường hoặc tên phát âm khác bằng fuzzy match thiếu bằng chứng.

Giữ transcript gốc và log mọi thay thế. Nếu dùng placeholder để giữ tên qua NLLB, phải test model có bảo toàn placeholder; không giả định. Không suy ra bản dịch tiếng Việt của thuật ngữ chỉ từ chữ tiếng Anh trên slide.

Hotword/prompt cho ASR là thí nghiệm riêng, cần kiểm tra API faster-whisper đang cài và đo false positive/hallucination; không bật chung ở lần đầu tích hợp OCR vì sẽ không phân biệt nguồn cải thiện.

### 10.3 Gemini tùy chọn

Tái sử dụng correction đã có; thêm title/entity phù hợp với câu đang nói. Audio là bằng chứng chính; OCR chỉ hỗ trợ thuật ngữ và phân giải tham chiếu. Không thêm thông tin không được nói, không biến câu “this chart” thành lời mô tả toàn bộ biểu đồ.

Không tăng số request correction vì có mỗi frame mới. Một segment đã có correction đang chạy phải dùng snapshot ngữ cảnh cố định. Correction còn khớp segment/source revision đang xem được cập nhật trên màn hình; nếu người dùng đã xem segment mới hơn thì chỉ cập nhật lịch sử, theo mục 3.

Thiếu API key: OCR + local tiếp tục chạy; không coi cloud là điều kiện để bật OCR.

## 11. Phases và gate

### Phase 0 — Chụp baseline hiện tại, ưu tiên Critical

- Đọc spec trước, kiểm tra những phần đã triển khai; lập bản đồ thay đổi.
- Ghi cấu hình ASR/MT và thiết bị runtime, audio hop, độ trễ local, queue length, số mutation/cue, correction và display skip trên cùng clip.
- Phân loại “chữ nhảy”: bản dịch sửa lại; chuyển câu quá nhanh; wrap/layout; draft; DOM rebuild. Không sửa nhiều tham số cùng lúc.

Gate: có log/replay chuỗi sự kiện subtitle và baseline audio-only. Không cần key để đạt gate này.

### Phase 1 — Giảm rung giao diện không thêm độ trễ, tùy kết quả

- Ưu tiên sửa layout, cập nhật DOM theo ID và bỏ các lần ghi text trùng; không bắt buộc viết lại scheduler.
- Bảo đảm kiểm tra session/segment/source revision để loại phản hồi cũ; vẫn cho cập nhật câu hiện tại khi kết quả hợp lệ mới sẵn sàng.
- Giữ model, audio chunk, phân đoạn và thời điểm phát request như baseline; không dùng đóng băng câu hoặc đợi đọc để xử lý flicker.

Gate: revision hợp lệ của câu đang xem được hiển thị, revision cũ bị bỏ; không segment rollback; 100 lần render cùng nội dung không làm text/layout đổi; không timer giữ chữ hoặc queue đọc mới. So sánh `result_ready → DOM_update` bằng replay cùng lịch sự kiện và đồng hồ giả lập: không thêm thời gian chờ chủ động. Chạy browser thật xác nhận không có hồi quy tốc độ ngoài nhiễu đo. Nếu không đạt, giữ/khôi phục renderer baseline và ghi phase này là deferred; được tiếp tục OCR.

### Phase 2 — Nền và kiểm tra khả năng đọc, mức Easy

- Blur trên vùng video cùng trang, fallback có tương phản.
- PiP nền tối rõ; không quảng bá kính mờ xuyên desktop.
- Kiểm tra fullscreen/PiP nhỏ, slide sáng/tối; chỉ thay style vùng cần thiết.

Gate: screenshot thể hiện chữ sắc nét, nền mờ thật trên video; style không gây thêm layout shift hoặc chặn cập nhật chữ mới. Không yêu cầu loại bỏ mọi lần thay nội dung.

### Phase 3 — Capture frame + ROI + clock, High

- Tái sử dụng video track, chọn ROI, frame sampling/backpressure và source epoch.
- Xây endpoint có giới hạn kích thước, lifecycle session/job.
- Chưa dùng OCR vào dịch; panel hiện preview + timestamp + trạng thái.

Gate: tab ẩn với PiP vẫn thu frame hoặc phát hiện/báo stale đúng; không capture trùng; không đọc frame tương lai; audio không bị phát lại hay dừng do OCR toggle.

### Phase 4 — OCR CPU + slide cache, High

- Tái sử dụng RapidOCR/detector, thêm stabilization, dedupe, title tổng quát, history cache theo session.
- Empty slide và scene change vô hiệu hóa context cũ; phản hồi sai epoch/ROI không ghi đè.
- OCR warmup/failure tách riêng, queue có bounds; bổ sung debug panel OCR.

Gate: đọc chữ thật từ slide; test fade, bullet animation, talking head, slide đứng yên; chỉ một worker OCR; OCR lỗi không làm kẹt audio/MT.

### Phase 5 — Context selector và thuật ngữ/correction, High

- Nối snapshot hợp lệ theo thời gian vào request correction, lọc relevance/confidence và log used vs available.
- Local vẫn dùng được không key; nhánh glossary được kiểm duyệt là flag riêng.
- Không tự append OCR text vào NLLB, không dùng cache tương lai, không chặn bản dịch để đợi OCR; correction tuân theo mục 3.

Gate: tình huống đổi slide khi OCR chậm không ghép sai context; tên/số sai OCR không bị ép vào transcript; OCR prompt injection không được thực thi; correction không kéo màn hình về câu cũ và không trì hoãn local.

### Phase 6 — Đo hồi quy và thí nghiệm NCKH

- Đo cùng nguồn, thiết bị, model, sampling và warmup, lặp >=3 lượt/điều kiện; đảo thứ tự để giảm ảnh hưởng nhiệt/cache.
- Điều kiện A: local không OCR. B: cùng local, OCR chạy/panel bật nhưng không can thiệp MT (đo overhead).
- C: cùng local + glossary đã xác nhận (nếu triển khai). So C với B để biết tác động glossary.
- D/E tùy key: cùng local + cùng Gemini correction, lần lượt không OCR/có OCR. Không kết luận OCR tốt hơn bằng cách so local với Gemini+OCR vì đã đổi cả model.
- Tập tối thiểu để pilot: clip NVIDIA có chuyển slide, clip có chữ nhỏ/bullet animation, clip không có slide; annotator đánh dấu transition, entity và câu có tham chiếu slide. Tách dữ liệu hiệu chỉnh ngưỡng khỏi dữ liệu đánh giá.

Gate vận hành đề xuất: p95 audio-to-first-local khi bật OCR không tăng quá max(200 ms, 10% baseline); không tăng dropped audio trên bài chạy kiểm soát; nếu không đạt, giảm sampling/thread/resolution OCR và đo lại. Đây là ngân sách thiết kế cần báo pass/fail, không phải số đã đo.

Các chỉ số phải báo: ASR/MT latency; display wait; text revisions sau khi lên màn hình; layout jumps; displayed/skipped cue; OCR queue/inference/ready time; transition delay và missed transitions; entity precision/recall; tỷ lệ context sai thời điểm; CPU/GPU/RAM; chất lượng nghĩa/tên/số theo người đánh giá. Không tuyên bố causal accuracy tốt chỉ vì OCR nhận được nhiều chữ.

## 12. Test bắt buộc và các tình huống biên

1. Cùng segment/source revision có bản VI mới hợp lệ sau khi hiển thị: display cập nhật, timeline lưu revision; response lỗi thời hoặc thuộc phiên trước bị bỏ. Khi đã hiển thị segment mới hơn, correction đoạn cũ chỉ vào history.
2. Kết quả 3 đến trước 2: không lùi thứ tự; log bỏ/giữ đúng policy.
3. Câu dài, số dòng thay đổi, draft rỗng/có chữ: không làm khung subtitle nhảy; nội dung đầy đủ còn trong history.
4. Slide A → B trong lúc OCR A đang chạy; kết quả A không làm current quay về A.
5. Phiên thứ hai và ROI mới; không dùng cache/response phiên đầu.
6. Slide không chữ, vùng người nói, ảnh đen/corrupt/quá lớn; không lấy title cũ để dịch.
7. Slide tĩnh 30 giây; OCR dedupe, không nhân job mỗi tick. Chữ bullet mới vẫn được phát hiện qua change/probe.
8. Frame xuất hiện sau cuối lời nói nhưng trả OCR sớm: không dùng vào bản dịch đầu của lời nói trước đó.
9. OCR timeout, tab background/minimize, track ended, stop/start, seek, change source: audio state đúng, worker/job giải phóng.
10. Chrome thật cho capture/PiP/blur; mock ASR/OCR dùng cho state/race test, test OCR thật dùng ảnh có nhãn riêng. Tách hai loại bằng chứng.
11. Không API key: local + OCR phải hoạt động. NLLB input không chứa toàn slide.
12. Trong mode có LLM, slide ghi “ignore instructions…” vẫn chỉ là text slide; không trở thành system instruction.

## 13. File gợi ý và bàn giao

Tái sử dụng: `frontend/live-core.js`, `frontend/live.js`, `frontend/live.css`, `frontend/floating.css`, `backend/server.py`, `backend/vision/scene_detector.py`, `backend/vision/slide_pipeline.py`, `backend/controller/state.py`, `backend/translation/contracts.py`, `backend/translation/live_service.py`.

Module mới chỉ khi cần tách trách nhiệm, ví dụ frame sampler hoặc vision session service. Không bắt buộc thay subtitle scheduler đang chạy; không viết lại toàn frontend, đổi framework hay thêm container OCR trước khi có số đo cho thấy cần.

Bàn giao mỗi phase: file đổi, quyết định, lệnh test và kết quả thực, hạn chế chưa xác nhận, cấu hình rollback. Feature flags độc lập cho OCR, glossary và cloud correction. README giải thích OCR đọc ảnh nguồn đã chia sẻ, source text có thể lưu trong log, frame raw mặc định không lưu lâu dài. Không gửi ảnh lên cloud khi user chỉ chọn local.

Nếu OCR gây hồi quy audio, AI phải sửa nguyên nhân trước khi bật OCR mặc định. Nếu riêng thử nghiệm chống nhảy thất bại, rollback thử nghiệm đó và tiếp tục OCR trên renderer baseline. Không tự đổi số đo, bỏ test hoặc tăng audio buffer để làm OCR có vẻ theo kịp.

## 14. Tài liệu kỹ thuật tham chiếu

- [MDN: backdrop-filter](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/backdrop-filter): blur phần nền trong rendering context và điều kiện transparency/backdrop root.
- [Chrome: Document Picture-in-Picture](https://developer.chrome.com/docs/web-platform/document-picture-in-picture): cửa sổ HTML luôn nổi và yêu cầu mở cửa sổ.
- [MDN: getDisplayMedia](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getDisplayMedia): quyền người dùng và capture video/audio.
- [MDN: requestVideoFrameCallback](https://developer.mozilla.org/en-US/docs/Web/API/HTMLVideoElement/requestVideoFrameCallback): metadata frame, timestamp, không bảo đảm đồng bộ tuyệt đối.
- [RapidOCR chính thức](https://github.com/RapidAI/RapidOCR): đối chiếu API với phiên bản thực tế đã ghim; không tự nâng major version theo ví dụ mới.
