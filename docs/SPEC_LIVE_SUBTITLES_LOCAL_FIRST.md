# Đặc tả triển khai: Phụ đề dịch trực tiếp local-first

> Yêu cầu mới nhất của người dùng: ưu tiên phụ đề bám sát lời nói. Đọc [SPEC_STABLE_SUBTITLES_AND_LIVE_SLIDE_OCR.md](SPEC_STABLE_SUBTITLES_AND_LIVE_SLIDE_OCR.md) bản đã sửa. Không đóng băng câu, tăng thời gian giữ, tạo hàng đợi đọc hay làm chậm phân đoạn đang hoạt động để giảm chữ nhảy. Cho cập nhật kết quả mới hợp lệ của câu đang xem; kết quả câu cũ không kéo màn hình lùi lại. Nếu tối ưu chống nhảy làm chậm thì giữ hành vi hiện tại và tiếp tục OCR. Quyết định mới này ưu tiên các khuyến nghị khác trong spec.

**Trạng thái:** Tài liệu yêu cầu triển khai  
**Phạm vi:** Ứng dụng dịch Anh–Việt đang có trong repository này  
**Ưu tiên:** Critical → High → Medium → hoàn thiện  
**Nguồn yêu cầu:** Nhu cầu người dùng và đánh giá code hiện tại. Đây là đặc tả hành vi; AI triển khai phải kiểm tra mã thực tế trước khi sửa vì repository có thể đã thay đổi.

## 1. Mục tiêu sản phẩm

Người dùng chia sẻ âm thanh của một tab đang phát video hoặc hội thoại. Ứng dụng thu âm liên tục, nhận dạng lời nói tiếng Anh, dịch sang tiếng Việt và hiển thị hai nội dung cùng đoạn trong trang chính lẫn cửa sổ nổi Picture-in-Picture (PiP). Người dùng có thể chuyển sang tab nguồn hoặc tab khác mà vẫn đọc được phụ đề.

Ở chế độ kết hợp, bản dịch local là kết quả đầu tiên. Nếu Gemini đã được cấu hình, Gemini hiệu chỉnh câu đã chốt trong nền bằng câu gốc, bản dịch local và ngữ cảnh trước đó. Gemini không được chặn bản dịch local. Kết quả trả về muộn không được thay nhầm câu, đưa giao diện lùi về transcript cũ, hoặc tạo nhiều lần đổi chữ gây nhấp nháy.

Đặc tả này không yêu cầu OCR, dịch hình ảnh, lồng tiếng, tự động điều khiển video bên ngoài, hay bảo đảm dịch đồng thời từng từ. Hệ thống dịch theo cụm lời nói có ranh giới hợp lý; dòng nhận dạng nháp có thể cập nhật nhanh hơn bản dịch.

## 2. Nguyên tắc bắt buộc

1. **Không tạo bản dịch giả.** Provider lỗi, thiếu model hoặc thiếu khóa phải được thể hiện là lỗi/trạng thái chưa sẵn sàng; không dùng lại tiếng Anh như bản dịch.
2. **Một đoạn có định danh ổn định.** Mọi transcript, bản dịch local, hiệu chỉnh Gemini và cập nhật UI phải gắn với cùng `session_id` và `segment_id`.
3. **Local không giả vờ hiểu ngữ cảnh.** NLLB hiện chỉ dịch câu được gửi vào model. Chỉ quảng bá khả năng dùng ngữ cảnh cho provider thực sự nhận và sử dụng ngữ cảnh.
4. **Không để Gemini quyết định độ trễ của kết quả đầu tiên ở chế độ kết hợp.** Bản local được hiển thị độc lập.
5. **Không kích hoạt quyền thu âm từ luồng nền.** `getDisplayMedia()` phải được gọi do thao tác trực tiếp của người dùng trong trang chính. PiP dùng để theo dõi và dừng phiên.
6. **Không gửi API key đến trình duyệt.** Khóa chỉ nằm ở môi trường backend; không ghi khóa, header xác thực, hoặc URL có bí mật vào log.
7. **Không tuyên bố đã kiểm chứng độ chính xác nếu chỉ chạy mock hoặc fixture.** Phân biệt browser integration test, test logic, benchmark văn bản, và đánh giá ASR/bản dịch thật.

## 3. Quy trình sử dụng mong muốn

1. Người dùng mở trang `/live` trên Chrome hoặc trình duyệt hỗ trợ Document Picture-in-Picture.
2. Trang báo trạng thái model/provider và chỉ cho bắt đầu khi thành phần cần thiết đã sẵn sàng.
3. Người dùng bấm **Chia sẻ âm thanh tab**, chọn đúng tab phát video và bật tùy chọn chia sẻ âm thanh tab trong hộp thoại trình duyệt.
4. Khi âm thanh đã được nhận, người dùng bấm **Mở phụ đề nổi**. Cửa sổ PiP được tạo trực tiếp từ thao tác người dùng.
5. Người dùng chuyển sang tab nguồn hoặc tab khác. PiP tiếp tục hiển thị câu tiếng Anh gần nhất và bản tiếng Việt tương ứng; dòng nháp nhận dạng có thể hiện riêng.
6. Người dùng có thể dừng thu từ trang chính hoặc PiP. Đóng PiP không được âm thầm làm sai trạng thái phiên. Nếu trình duyệt thực tế dừng capture khi đóng PiP, giao diện phải báo chính xác và cho mở lại.
7. Hộp chọn nguồn chỉ mở từ thao tác người dùng rõ ràng. Không tự chọn tab, không tự bật âm thanh, không khởi tạo capture khi tải trang.

`Chia sẻ âm thanh tab` và `Mở phụ đề nổi` là hai thao tác riêng để đáp ứng yêu cầu user-activation của trình duyệt. Không gộp hai API cần user gesture vào một thao tác nếu điều đó làm một trong hai API thất bại.

## 4. Mô hình dữ liệu phiên và đoạn

Mỗi phiên thu có `session_id` duy nhất, tăng/đổi khi bắt đầu phiên mới. `segment_id` tăng đơn điệu trong phiên. Một hàng đoạn tối thiểu gồm:

```text
session_id
segment_id
start_audio_sec, end_audio_sec
source_text
source_draft
local_translation
final_translation
translation_provider
status
asr_latency_ms, local_latency_ms, correction_latency_ms
received_at, displayed_at
```

Tên trường thực tế có thể khác, nhưng ý nghĩa phải tương đương. Không dùng chỉ số mảng hoặc nội dung transcript để định danh vì hàng có thể được cập nhật và phản hồi dịch có thể đến sai thứ tự.

### Trạng thái đoạn đề xuất

```text
listening_draft
  → source_final
  → local_pending
  → local_ready
  → correction_pending       (chỉ chế độ Local + Gemini)
  → corrected                (nếu Gemini trả kết quả hợp lệ)
```

Nhánh lỗi:

```text
source_final → local_error
correction_pending → local_ready  (giữ bản local nếu Gemini lỗi hoặc hết hạn)
gemini_only → translation_error   (không có bản local để dự phòng nếu chưa được yêu cầu)
```

Lỗi hiệu chỉnh không xóa hoặc thay bản local. Kết thúc phiên không được nhận kết quả của phiên trước. Hủy hoặc bỏ qua kết quả sai phiên ở frontend; nếu có thể, hủy request HTTP khi người dùng dừng phiên, nhưng correctness không được phụ thuộc vào hủy thành công.

## 5. Phân đoạn lời nói và quản lý transcript

### 5.1 Tách nháp khỏi đoạn đã chốt

- ASR rolling snapshot tiếp tục cập nhật dòng `source_draft`.
- Giữ cơ chế phân đoạn/dịch tăng dần hiện tại đang theo kịp lời nói. Bản final gắn với cụm đã chốt; không ép mọi cập nhật phải đợi final chỉ để giảm số lần đổi chữ.
- Không dùng điều kiện “đủ 3 từ” làm điều kiện duy nhất để chốt và dịch một câu.
- Bản dịch nháp nếu đang được dùng vẫn được cập nhật theo tiến độ, có nhãn và ghép đúng source revision; phản hồi nháp cũ không ghi đè bản final mới.

### 5.2 Quy tắc ranh giới

Tái sử dụng và thống nhất một thuật toán phân đoạn trong `frontend/live-core.js`. Mốc khởi đầu để hiệu chỉnh, không phải chân lý ngôn ngữ:

- Chốt tại dấu kết câu `.`, `?`, `!` khi từ đó đã ổn định qua ASR.
- Cho phép chốt tại khoảng ngừng âm thanh đủ rõ sau một cụm có độ dài tối thiểu; ngưỡng hiện có khoảng 0,55–0,8 giây có thể giữ làm cấu hình ban đầu.
- Dấu phẩy/chấm phẩy chỉ là ranh giới mềm sau cụm đủ dài; không tách những từ nối còn dang dở như `and`, `because`, `the`, `to` ở cuối đoạn.
- Giữ giới hạn độ dài tối đa để tránh đợi vô hạn. Giới hạn hiện có 22 từ có thể dùng làm mức khởi đầu và phải ghi nhận khi bị kích hoạt.
- Khi dừng phiên, chốt phần cuối còn lại nếu có nội dung đủ dùng; không làm mất transcript cuối chỉ vì chưa có dấu câu.

Không để `phraseReady()`, `findSentenceBoundary()`, timer UI và logic `activeRow` đưa ra các quyết định mâu thuẫn. Chỉ giữ một đường quyết định chốt đoạn; xóa code chết hoặc viết test chứng minh helper thực sự được gọi.

### 5.3 Phản hồi ASR chồng lấn

Tiếp tục kiểm tra các từ đã ổn định để không nhân đôi từ qua các rolling snapshot. Một từ chỉ được chuyển sang `source_final` một lần. Khi ASR sửa phần nháp, chỉ sửa nháp chưa chốt; không âm thầm viết lại các đoạn đã dịch nếu không có cơ chế sửa phiên riêng.

## 6. Chế độ dịch và định tuyến model

Chỉ cung cấp ba chế độ sản phẩm rõ ràng:

### A. Local

- Dùng NLLB local.
- Không cần API key hoặc mạng sau khi model đã có trong cache.
- Giữ luồng dịch tăng dần/đoạn đã chốt hiện tại. Nếu có bản nháp, đánh dấu rõ; không thêm giới hạn tần suất hiển thị khiến kết quả đã sẵn sàng phải chờ.
- Gửi duy nhất câu nguồn đến local model hiện tại; không ghi rằng local đã dùng `previous_context`.

### B. Local trước + Gemini hiệu chỉnh

- Bản local là kết quả đầu tiên.
- Khi câu đã chốt, gửi một yêu cầu Gemini hiệu chỉnh ở nền, không chờ request này mới hiển thị local.
- Gemini nhận câu nguồn, bản dịch local ban đầu và ngữ cảnh từ một số đoạn đã chốt trước đó. Prompt phải yêu cầu giữ nguyên ý, tên riêng và con số; không thêm thông tin; trả một bản tiếng Việt ngắn gọn.
- Nếu Gemini trả kết quả hợp lệ trong giới hạn thời gian cập nhật, thay bản dịch của đúng `segment_id`; nếu lỗi, timeout, thiếu key hoặc kết quả rỗng, giữ nguyên bản local.
- Không gửi Gemini cho mọi snapshot nháp. Chỉ gửi tối đa một lần hiệu chỉnh cho mỗi đoạn chốt, trừ thao tác retry tường minh.
- Ghi nhận riêng provider và thời gian local/correction để đánh giá tỷ lệ cải thiện và độ trễ.

### C. Gemini

- Dùng Gemini làm provider dịch chính cho đoạn đã chốt.
- Không được tuyên bố có fallback local nếu chưa thực sự gọi local khi Gemini lỗi.
- Thiếu key/model/quota phải hiện lỗi cụ thể, không trả nguồn tiếng Anh như thể đã dịch.

### 6.1 Model và provider configuration

- Backend là nguồn quyết định tên Gemini model. Frontend không được gán tên model local vào trường Gemini.
- API trạng thái nên trả các trường tách biệt như `provider`, `local_model`, `gemini_model`, `gemini_configured`, `context_supported`.
- Frontend chỉ gửi tên model nếu tính năng thật sự cần chọn model; mặc định để backend dùng cấu hình server.
- Local request không nhận tên Gemini; Gemini request không nhận tên NLLB.
- Nếu thiếu Gemini key, chế độ Gemini bị vô hiệu hóa hoặc cảnh báo trước khi thu âm; chế độ Local vẫn dùng được.
- Đổi model/provider cần có kiểm tra đầu vào ở backend và thông báo lỗi không chứa bí mật.

### 6.2 API contract

Ưu tiên tạo endpoint chuyên cho pipeline trực tiếp, ví dụ `POST /api/live/translate`, thay vì tiếp tục mở rộng tên endpoint thử nghiệm `/api/translate-test`. Nếu giữ endpoint cũ để tương thích trang test, endpoint cũ phải gọi lại cùng service và cùng validation.

Request đề xuất:

```json
{
  "request_id": "session-uuid:segment-12:local",
  "session_id": "session-uuid",
  "segment_id": 12,
  "operation": "translate_local",
  "text": "Finalized English sentence.",
  "previous_context": "Earlier finalized source text.",
  "initial_translation": "Bản dịch local ban đầu."
}
```

`operation` chỉ nhận các giá trị được backend cho phép, ví dụ `translate_local`, `translate_gemini`, `refine_gemini`. `previous_context` và `initial_translation` chỉ dùng ở operation hỗ trợ chúng. Phản hồi phải có `status`, `request_id`, `segment_id`, `provider`, `model` không nhạy cảm, `translated_text`, `latency_ms`, `context_supported`, và `error_code`/`message` nếu lỗi. Không bao giờ trả API key.

## 7. Chính sách cập nhật giao diện, ghép cặp và chống nhấp nháy

### 7.1 Trang chính

- Nhật ký đầy đủ có thể giữ nhiều đoạn, trạng thái, provider và thời gian.
- Vùng “đang nghe” hiển thị transcript nháp.
- Vùng kết quả hiện tại phải ghép `source_text` và `final_translation` của cùng một `segment_id`.
- Khi câu mới đang dịch, giữ cặp hoàn chỉnh gần nhất cho đến khi câu mới có bản local hoặc trạng thái lỗi rõ ràng.

### 7.2 Cửa sổ PiP

PiP ưu tiên đọc nhanh, không sao chép toàn bộ dashboard. Nội dung mặc định:

1. Câu tiếng Anh đang nghe hoặc đoạn nguồn mới nhất.
2. Bản dịch tiếng Việt của chính đoạn đó.
3. Một dòng nháp nhận dạng nhỏ, có nhãn “Đang nghe”, nếu có transcript chưa chốt.
4. Nút dừng thu và nút quay lại trang chính.

Có thể giữ lịch sử ngắn nếu nó không làm giảm diện tích dòng hiện tại; không đưa metrics, log debug, stack trace hoặc thông tin API vào PiP. Cập nhật DOM bằng `textContent` cho mọi transcript/bản dịch. Chỉ tạo cấu trúc HTML tĩnh trong code.

### 7.3 Chính sách kết quả đến muộn

- Chỉ nhận phản hồi nếu `session_id` còn hiện hành và `segment_id` tồn tại.
- Không chuyển từ đoạn N sang N−1 do phản hồi trễ.
- Gemini chỉ được hiệu chỉnh đúng đoạn đã gửi, không làm thay đổi `source_text`.
- Cập nhật cặp nguồn–đích khi có kết quả mới hợp lệ; không thêm thời gian giữ cố định hoặc hàng đợi để người xem đọc đủ câu cũ. Tránh mutation trùng, layout shift và phản hồi sai thứ tự.
- Giữ hành vi streaming/hiển thị hiện tại nếu đang theo kịp; không thêm hiệu ứng đánh máy hoặc gom kết quả bằng timer làm chậm bản dịch đã có. Kết quả chưa hoàn tất phải được đánh dấu là nháp.

## 8. PiP, quyền trình duyệt và vòng đời capture

- Kiểm tra `documentPictureInPicture` và hỗ trợ `getDisplayMedia` trước khi bật nút.
- `getDisplayMedia()` phải được gọi trực tiếp trong handler thao tác người dùng ở trang chính.
- Sau khi chọn nguồn, kiểm tra có audio track; nếu không, dừng stream vừa mở và báo người dùng chọn tab cùng bật chia sẻ âm thanh.
- Luồng capture, AudioContext, worklet và ASR thuộc cửa sổ trang chính; PiP chỉ quan sát state và gửi lệnh dừng về trang chính.
- Đóng/mở PiP không được tạo thêm AudioContext hoặc capture thứ hai.
- Bắt sự kiện `ended` của audio track và đồng bộ trạng thái UI.
- Khi đóng trang chính, dừng track và đóng AudioContext. Khi dừng thủ công, flush phần âm thanh cuối, chốt ASR cuối trong giới hạn thời gian rồi giải phóng tài nguyên.
- Nếu trình duyệt không hỗ trợ Document PiP, thông báo rõ popup thường không bảo đảm luôn nổi; không quảng bá fallback như PiP thật.

## 9. Hàng đợi, concurrency và lỗi

- Chỉ có tối đa một tác vụ ASR đang chạy cho phiên nếu engine hiện tại không hỗ trợ song song an toàn.
- Giữ chính sách ưu tiên snapshot mới nhất cho ASR rolling, nhưng phải đảm bảo snapshot mới thực sự chứa vùng lời chưa xử lý; nếu không, ghi nhận đoạn bị mất và không giả vờ đã nhận dạng đủ.
- Local model có lock GPU hiện tại; giới hạn tác vụ local đồng thời ở frontend/backend để tránh tạo backlog vô ích.
- Gemini correction có concurrency limit và bounded queue; bỏ qua correction quá cũ khi nó không còn giá trị hiển thị.
- Không dùng biến boolean `translating` đơn lẻ nếu nhiều request có thể chạy cùng lúc; dùng bộ đếm hoặc tập request ID để trạng thái “đang dịch” đúng.
- Lỗi một provider không làm kẹt `isTranslating`, hàng đợi hoặc nút dừng.
- Lỗi trả cho người dùng bằng thông báo ngắn; log nội bộ chỉ chứa loại lỗi, mã HTTP, phase và request ID đã khử bí mật.

## 10. Logging, quyền riêng tư và dữ liệu nghiên cứu

- Không log API key, Authorization header, URL có key hoặc toàn bộ môi trường tiến trình.
- Log dịch có thể chứa transcript/bản dịch; tài liệu phải nói rõ vị trí và cách xóa.
- Không lưu bản dịch Gemini làm dữ liệu distillation/training một cách âm thầm. Mặc định tắt hoặc yêu cầu cờ cấu hình rõ ràng; chỉ lưu dữ liệu cần thiết, có thể truy nguồn bằng request ID và không có bí mật.
- Export phiên phải phân biệt draft/final, provider, model, latency và dropped segment; không đưa credential.
- Benchmark ghi dữ liệu thô tách theo run, model, cấu hình, lỗi và thời điểm; không ghi khóa vào JSON/CSV/Markdown.

## 11. Kiểm thử và tiêu chí nghiệm thu

Không coi một test mock là bằng chứng về chất lượng dịch thật. Chạy các tầng sau theo thứ tự.

### 11.1 Unit tests JavaScript

Kiểm tra:

- phân đoạn tại dấu câu, khoảng ngừng, connector chưa hoàn chỉnh, giới hạn độ dài và flush cuối phiên;
- stable words không nhân đôi qua rolling ASR;
- draft không bị nhầm thành final;
- ghép tiếng Anh–tiếng Việt cùng segment;
- kết quả trễ không rollback về đoạn cũ;
- kết quả phiên cũ bị bỏ qua;
- trạng thái hàng đợi/concurrency về đúng sau success, error, timeout.

### 11.2 Backend tests

Kiểm tra:

- local request chỉ gọi local và bỏ qua Gemini model;
- Gemini/refine dùng model Gemini từ cấu hình backend, không nhận tên NLLB;
- thiếu key, model không hợp lệ, HTTP 429, timeout, response rỗng và response chưa hoàn tất;
- Gemini lỗi trong chế độ kết hợp vẫn trả/giữ bản local;
- không response hoặc log nào chứa API key;
- context được truyền cho Gemini và được báo không hỗ trợ với local.

### 11.3 Chrome browser integration

Dùng Chrome thật với tab fixture phát âm tổng hợp; không dùng âm thanh hoặc tab cá nhân. Mock có chủ đích các API ASR/dịch khi kiểm tra UI. Xác nhận:

- nút chia sẻ mở hộp chọn và thu đúng một audio track;
- PiP thật mở từ thao tác người dùng;
- PiP hiển thị đúng các vùng DOM đã đặc tả;
- chuyển tab không làm PiP biến mất;
- đoạn mới cập nhật đúng cặp tiếng Anh–Việt;
- dừng, đóng và mở lại PiP không để lại track/context hoặc tạo capture trùng;
- lỗi provider không làm hỏng UI và không in page error.

### 11.4 Kiểm tra chạy thật và đánh giá nghiên cứu

- Chạy Docker trên GPU hỗ trợ, chờ warmup hoàn tất rồi thử video NVIDIA và một tab ngoài.
- Đo riêng: thời gian nhận dạng, thời gian bản local, thời gian Gemini correction, độ trễ từ cuối câu nói đến bản đầu tiên, p50/p95, số lần đổi subtitle và số đoạn bỏ qua.
- Tạo một tập câu có transcript tham chiếu đã được người kiểm tra sửa. Đánh giá ASR và chất lượng dịch theo cùng câu cho Local, Gemini và Local + Gemini.
- Có chấm độ đúng nghĩa/ngữ cảnh của người đánh giá; không dùng latency thấp để suy ra bản dịch tốt.
- Ghi rõ benchmark văn bản không phải benchmark đầu-cuối audio-to-subtitle.

## 12. Kế hoạch triển khai theo phase

### Phase 0 — Sửa định tuyến model/provider (Critical)

1. Tách `local_model` và `gemini_model` trong API trạng thái/cấu hình.
2. Bỏ việc gửi model local trong request Gemini và model Gemini trong request local.
3. Thêm validation và thông báo khi Gemini chưa cấu hình.
4. Thêm backend regression tests cho các trường hợp trên.

**Gate:** local và Gemini được định tuyến đúng; lỗi cấu hình được báo rõ; không có credential trong browser/log.

### Phase 1 — Thống nhất luồng capture và PiP (Critical)

1. Chốt workflow hai thao tác: chia sẻ tab ở trang chính, mở PiP riêng.
2. Chốt markup tối giản cho PiP và sửa test theo đúng markup/workflow.
3. Giữ capture/audio pipeline ở trang chính; PiP chỉ đọc state và gửi lệnh dừng.
4. Kiểm tra track lifecycle, đóng/mở PiP, browser fallback.

**Gate:** Chrome browser integration pass với synthetic audio fixture; không chờ selector không tồn tại.

### Phase 2 — Local-first và hiệu chỉnh bất đồng bộ (Critical)

1. Chuẩn hóa ba mode: Local, Local + Gemini correction, Gemini.
2. Hiển thị local ngay khi có kết quả.
3. Gửi correction cho từng câu final tối đa một lần, có concurrency limit.
4. Ghép phản hồi theo session/segment ID; bỏ response cũ; giữ local khi correction lỗi.
5. Hiển thị provider và trạng thái ngắn gọn trên timeline.

**Gate:** mô phỏng Gemini chậm/lỗi; local vẫn lên UI trước và không có rollback/đoạn ghép sai.

### Phase 3 — Ranh giới câu, ngữ cảnh và ổn định phụ đề (High)

1. Dùng một thuật toán duy nhất để chốt câu.
2. Tách draft ASR khỏi nguồn final và bản dịch chính.
3. Dùng context chỉ với provider hỗ trợ; prompt correction bảo toàn ý, tên riêng và con số.
4. Giữ cặp hoàn chỉnh gần nhất trong lúc câu kế tiếp chờ dịch.
5. Đo flicker và điều chỉnh ngưỡng dựa trên video thực tế.

**Gate:** unit tests ranh giới và ghép cặp pass; không dịch theo từng mảnh ba từ ở vùng final.

### Phase 4 — Xử lý hàng đợi, lỗi và tài nguyên (High)

1. Sửa tracking số request đang chạy và bounded queues.
2. Đảm bảo stop/flush/error luôn giải phóng track, node và AudioContext.
3. Xử lý lỗi ASR, local, Gemini, network timeout và track ended.
4. Bổ sung logging đã khử bí mật và chính sách lưu dữ liệu minh bạch.

**Gate:** stress/error tests không làm treo nút dừng, rò tài nguyên hoặc kẹt trạng thái.

### Phase 5 — Đánh giá và tài liệu (Medium/hoàn thiện)

1. Cập nhật README theo đúng workflow và provider mode.
2. Chạy test Python/JS/browser và Docker smoke test phù hợp.
3. Chuẩn bị tập câu tham chiếu cho NVIDIA video.
4. So sánh tốc độ, độ ổn định và chất lượng Local/Gemini/Hybrid.
5. Ghi hạn chế: context local, môi trường GPU, cold start, lỗi/quota API và giới hạn browser PiP.

**Gate:** có báo cáo tách biệt độ trễ ASR, độ trễ dịch, độ trễ đầu-cuối và chất lượng bản dịch.

## 13. File dự kiến cần xem/sửa

AI triển khai phải xác minh đường dẫn và trách nhiệm hiện tại trước khi sửa; danh sách dưới đây là điểm bắt đầu:

- `frontend/live.js`: điều phối phiên, ASR/MT requests, translation mode, cặp transcript, PiP.
- `frontend/live-core.js`: segmentation, stable words, presenter/queue helpers.
- `frontend/live.html`, `frontend/live.css`, `frontend/floating.css`: controls và UI.
- `backend/server.py`: API status, validation và routing.
- `backend/translation/live_service.py`, `backend/translation/local_provider.py`, `backend/translation/nllb_engine.py`: provider behavior/context.
- `compose.yaml`, `studio.cmd`, `README.md`: cấu hình, khởi động và tài liệu.
- `tests/test_live_audio_js.cjs`, `tests/test_live_pipeline_js.cjs`, `tests/test_floating_subtitles_js.cjs`, `tests/browser_floating_subtitles.py`, backend translation tests.

Không xóa dữ liệu model, video, kết quả benchmark hoặc tài liệu nghiên cứu để làm cho test/build gọn hơn. Không commit/push/deploy nếu người dùng chưa yêu cầu.

## 14. Chỉ dẫn cho AI triển khai

1. Đọc file spec này và kiểm tra trạng thái repository trước khi sửa; nếu code đã khác, đối chiếu hành vi hiện tại với yêu cầu thay vì áp dụng máy móc số dòng.
2. Triển khai từng phase theo phụ thuộc thực tế. Riêng thử nghiệm chống nhảy: nếu làm chậm thì rollback và ghi deferred, được tiếp tục các phase nền/OCR trên renderer hiện tại theo spec bổ sung. Các gate về tính đúng, bảo mật khóa và hồi quy audio vẫn phải đạt.
3. Trước mỗi phase, nêu file và hành vi sẽ thay đổi. Sau phase, tóm tắt thay đổi, lệnh kiểm tra và kết quả thực tế.
4. Bổ sung hoặc sửa test có giá trị cho hành vi mới; không sửa test chỉ để che lỗi sản phẩm.
5. Không tuyên bố đã kiểm chứng bằng Chrome thật, GPU thật hoặc dịch thật nếu chỉ chạy mock.
6. Nếu yêu cầu trong spec mâu thuẫn với giới hạn browser/provider hoặc code mới, ghi rõ bằng chứng và chọn phương án bảo toàn mục tiêu người dùng, không tự bỏ chức năng cốt lõi.
