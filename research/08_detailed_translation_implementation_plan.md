# Kế hoạch triển khai chi tiết: dịch thử → ngữ cảnh OCR → kiểm chứng nghiên cứu

Ngày: 07/10/2026. Bắt đầu từ sự cố website hiển thị nguyên văn tiếng Anh. Lịch dưới đây là ước lượng cho một người, cần điều chỉnh theo kinh phí, gold/reference và hạn bảo vệ.

## 1. Nguyên nhân đã xác nhận

- ASR nhận được câu tiếng Anh; đây không phải bằng chứng engine MT đang chạy tốt.
- Request tới endpoint dịch hiện tại bị `URLError`, nguyên nhân socket `WinError 10013` trong môi trường chạy này.
- `fast_translate` cũ nuốt lỗi và trả source text; UI vẫn gắn nhãn committed/revised. Lỗi kết nối vì thế bị trình bày như dịch thành công.
- Chưa có GEMINI_API_KEY trong môi trường kiểm tra. Qwen cached chỉ có metadata, không có safetensors; torch/transformers/llama_cpp chưa có trong .venv. Chưa có local engine sẵn sàng để thay thế ngay.

Không sửa bằng cách điền bản dịch tay vào output, tắt xác minh TLS hoặc thêm một dictionary câu keynote. Cần kết nối provider thật và lưu trạng thái request.

## 2. Bước đã thực hiện trong đợt này

- Adapter web `backend/translation/live_service.py` có trạng thái ok/error, provider, thời gian request và lỗi rõ ràng. Không trả source text khi mạng/API lỗi. Nếu provider trả nguyên văn thì đánh dấu cần kiểm tra, vì một số tên riêng có thể giữ nguyên hợp lệ.
- Hỗ trợ `google-demo` để kiểm tra dịch văn bản bằng đường gọi hiện có, và `gemini` nhận Fusion Prompt. Google demo không nhận OCR/context và không dùng làm bằng chứng multimodal research.
- Trang `/translation-test` gửi một câu tiếng Anh, hiển thị bản dịch hoặc lỗi; không cần chạy Whisper/OCR trước.
- Website báo “chưa dịch” khi MT thất bại; không gắn flag sửa câu trước như đã sửa thật. Bỏ việc dịch từng nhóm ba từ và giả lập jitter latency.
- Bản dịch thử hiện là sentence-level, xử lý trước 35 giây đầu. Baseline toggle bị vô hiệu hóa vì chưa chạy đối chứng độc lập. OCR ảnh 120s không được đưa vào bản dịch đoạn đầu; cột OCR cũ được đánh dấu là dữ liệu mẫu.
- Script `start_studio.ps1` để người dùng chạy từ PowerShell trên máy, chọn provider và nhập key ẩn nếu dùng Gemini. Script không ghi key ra file.

Những thay đổi này giúp chẩn đoán và thử dịch; chưa hoàn thành pipeline causal streaming hoặc pilot chất lượng. Request thật từ phiên trợ lý vẫn bị chặn; chưa tạo bản dịch tiếng Việt qua provider trong phiên này.

## 3. Giai đoạn 1 — có bản dịch thật để thử ngay (ước lượng 0.5–1 ngày)

1. Chạy server từ PowerShell do người dùng mở trên máy. Giữ nguyên bảo vệ hệ thống, không tắt antivirus/firewall để chữa lỗi theo phỏng đoán.
2. Mở trang `/translation-test`, thử một câu bình thường. `google-demo` không cần key nhưng phụ thuộc endpoint không được cam kết ổn định. Nếu endpoint không dùng được, chọn API chính thức hoặc local engine thật.
3. Với Gemini, cấu hình key trên máy và model có quyền truy cập; thử 3–5 câu: câu đầy đủ, thuật ngữ, câu phụ thuộc tiền ngữ. Một phép thử thành công xác nhận kết nối/output, chưa xác nhận quality research.
4. Khi single-sentence test thành công, chạy video 35s; kiểm tra bản dịch nguyên câu, tỷ lệ lỗi và các request timing.
5. Thử failure: thiếu key, tên model sai, mất mạng. UI phải ghi lỗi, source vẫn ở dòng tiếng Anh; không tính output lỗi như bản dịch thành công.

**Nghiệm thu:** ít nhất một bản dịch thật được nhận từ provider, sau đó video có output Việt; provider/MT status hiển thị đúng; không fallback âm thầm.

Lệnh từ PowerShell tại thư mục dự án:

```powershell
.\start_studio.ps1 -Provider google-demo -Port 8003
```

Hoặc Gemini:

```powershell
.\start_studio.ps1 -Provider gemini -GeminiModel TEN_MODEL_TRONG_API_PROJECT -Port 8003
```

Thay tên model bằng model thực tế. Script mặc định dùng cổng 8003 để tách khỏi server phiên trợ lý. Nếu cổng đã dùng, chọn cổng khác bằng -Port; script không dừng ứng dụng khác. Nếu PowerShell không cho chạy script theo chính sách máy, có thể mở file, thực hiện các lệnh tương ứng trong terminal; không cần thay đổi chính sách toàn hệ thống. Bản cập nhật do trợ lý chạy để xem UI dùng cổng 8002.

## 4. Giai đoạn 2 — pipeline dữ liệu đúng (ước lượng 2–3 ngày)

| Hạng mục | Công việc | Nghiệm thu |
|---|---|---|
| Session | Tách video/provider/cache/history/run ID; upload không dùng chung dữ liệu | Hai video liên tiếp không trộn slide/câu |
| Frame | Lấy frame từ video đang xử lý theo cutoff | Không dùng ảnh annotation cố định hoặc frame tương lai |
| OCR cache | Source/video/frame time/available_at/TTL; reset detector/cache | Evidence chỉ dùng sau khi OCR hoàn tất, đúng nguồn và chưa lỗi thời |
| Prompt | Cùng instruction và text context, chỉ thay visual field | Có log prompt hash/evidence IDs, so A/B/C công bằng |
| Provider | Error/timeout/usage/model version; client tái sử dụng khi phù hợp | Không tính thiếu key, source echo hoặc output cắt cụt là success |
| Telemetry | Decode/ASR/OCR/MT/queue/end-to-end clocks riêng | Không dùng 0.02ms lookup để đại diện OCR, không gọi batch ASR là latency chunk |

Ưu tiên hoàn thành text+OCR pipeline offline có log trước khi xây streaming. Với API provider, ngân sách request thử nghiệm có thể rộng hơn target live; báo rõ chế độ.

## 5. Giai đoạn 3 — pilot kiểm tra giả thuyết (ước lượng 3–5 ngày, phụ thuộc người gán nhãn)

- Xác minh 24 candidate đã chuẩn bị trong `data/pilot_abc/source01/review.html`; tám đoạn chạm biên cần kiểm tra trước.
- Bổ sung 2–4 nguồn độc lập để đạt vòng pilot 3–5 video, chọn khoảng 20–30 đoạn có đủ nhóm không cần/có thể hữu ích/gây hiểu sai. Chốt cách chọn trước khi xem output dịch.
- Chạy A: transcript+context; B: thêm chữ slide chuẩn; C: thêm OCR thật. Cùng engine/prompt/context, chỉ thay evidence.
- Viết reference trước khi chạy hoặc trước khi xem output; chấm mù adequacy, thuật ngữ, thiếu ý, thêm ý và sai tham chiếu.
- Tính descriptive paired B−A/C−A/C−B theo nguồn, giữ failures/coverage. Chưa tuyên bố tương đương hoặc hiệu quả khái quát từ một nguồn.

**Quyết định:** B hữu ích nhưng C kém → điều tra OCR/alignment; cả B/C ít hữu ích → đổi nhóm case/prompt hoặc thu hẹp giả thuyết; C hữu ích trên nhóm rõ ràng → tiếp tục thiết kế policy chọn acquisition. Xem `07_pilot_abc_guide.md` để chạy runner.

## 6. Giai đoạn 4 — streaming và policy (ước lượng 1–2 tuần)

- Replay media clock phát audio/frame tăng dần; ASR chỉ đọc input đã có, xuất partial/stable states có mốc thời gian.
- OCR worker/hàng đợi hữu hạn; không chặn audio vô hạn; bỏ/gộp evidence lỗi thời.
- Event stream SSE cho upload/replay; WebSocket nếu truyền audio hai chiều. Frontend cập nhật theo event, không giả lập “đang nghe” từ output đã tính trước.
- Score-based policy dùng visual reference/entity uncertainty/cache age/scene change/remaining budget; tune trên dev, khóa trước test.
- Subtitle nháp/chốt có ID/version. Revision phải thực sự thay nội dung đúng câu và đo flicker; không suy ra đã sửa từ liên từ.
- Baseline: audio-context, frequent OCR, scene-triggered OCR; sau đó thêm fixed sampling nếu nguồn lực cho phép.

**Nghiệm thu:** event xuất trước EOF; không đọc tương lai; lag p50/p95 và miss rate từ trace; mọi OCR/MT/background cost được tính; policy có/không cải thiện đều báo được.

## 7. Giai đoạn 5 — benchmark và hồ sơ nghiên cứu

Thu thập nhiều nguồn với split theo bài nói; khóa reference/config; thực nghiệm và ablation; thống kê theo nguồn độc lập; report có uncertainty và error analysis. Lịch tổng thể tám tuần vẫn nằm ở `04_product_research_roadmap.md`.

Đồng bộ BM03: sửa các cam kết 150 video/chuyên gia/trần cabin/RTF đạt sẵn thành mục tiêu có điều kiện và phạm vi đo rõ. Bản góp ý có nội dung thay thế ở `docs/BM03_NHAN_XET_VA_NOI_DUNG_DE_XUAT_20261007.md`; file BM03 gốc chưa bị chỉnh.

## 8. Những việc cần người dùng cung cấp để kết thúc vòng dịch thử

- Provider sử dụng: Google demo để smoke test văn bản, hoặc Gemini/local thật cho thí nghiệm có context.
- Nếu dùng Gemini: key cấu hình trên máy và model có quyền truy cập, không gửi secret vào chat.
- Mở server từ môi trường mạng cho phép truy cập provider; phiên trợ lý hiện bị socket access denied.
- Transcript/slide/reference được xác minh và thêm nguồn video trước khi đánh giá giả thuyết.

Tài liệu kỹ thuật API đã đối chiếu: [Google generateContent](https://ai.google.dev/api/generate-content). Khả dụng/quota/model cụ thể phải kiểm tra trong project của người dùng; chưa có run API thành công trong phiên này.
