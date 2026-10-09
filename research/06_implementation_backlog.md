# Backlog triển khai theo thứ tự phụ thuộc

Ngày: 07/10/2026. Các hạng mục dưới đây **chưa được sửa trong code**. `[ ]` là việc cần làm; không dùng danh sách này để kết luận năng lực đã có.

## P0 — đường dữ liệu đúng và kết quả trung thực

| ID | Việc/file liên quan | Nghiệm thu cụ thể |
|---|---|---|
| B01 | `live_pipeline.py`, `translation/factory.py`: dùng provider interface với TranslationRequest đầy đủ | Provider thật nhận speech/context/OCR; mock được đánh dấu rõ; lỗi tên provider không âm thầm rơi về mock trong benchmark |
| B02 | `local_provider.py`, `gemini_provider.py`: trạng thái provider | Skeleton báo unavailable; thiếu key/HTTP lỗi/timeout có status/error_code; chuỗi tiếng Anh fallback không được tính là dịch thành công |
| B03 | `live_pipeline.py`: bỏ ảnh annotation cố định; lấy frame của video session | Upload hai video khác nhau cho evidence riêng; không có ảnh keynote ở video mới; frame không vượt cutoff |
| B04 | `controller/state.py`: timestamp/source/TTL/clear cho cache | Reset không AttributeError; cache không dùng evidence tương lai/hết hạn/khác session; thứ tự entity ổn định và lưu source |
| B05 | `server.py`, `frontend/app.js`, `index.html`: telemetry thật | Thiếu GPU thì unavailable; bỏ 620/0.02ms/jitter giả trong chỉ số đo; đo ASR batch không lặp lại như latency từng segment |
| B06 | Instrumentation có run/segment/version ID | Một segment truy được input cutoff, evidence, provider, timing và output; ghi tất cả MT calls kể cả phrase/baseline/revision |
| B07 | Reset/re-run/upload và scene detector | Clear cache/history/detector/frontend flags; reject event run cũ; tránh ghi đè và trộn video của session khác |
| B08 | README + config + requirements/lock | Có lệnh chạy/test và biến môi trường mẫu không chứa key; phiên bản dependency/model/prompt được ghi; xác nhận cài sạch trên môi trường thử trước khi gọi tái lập |

Thứ tự vòng đầu: B01/B02 → B03/B04 → B06/B05 → B07/B08. B05 phải xong trước khi trình bày số liệu demo như kết quả nghiên cứu.

## P1 — streaming nhân quả và điều khiển tài nguyên

| ID | Việc | Nghiệm thu |
|---|---|---|
| S01 | Session/job API; worker xử lý; SSE job events | HTTP phục vụ status/video khi AI đang chạy; event có trước hết video; cancel dừng job và giải phóng tài nguyên |
| S02 | Replay media clock, incremental audio buffer/ASR | Thay dữ liệu sau cutoff không thay output trước cutoff; không chạy transcribe toàn 35s trước rồi mới phát event |
| S03 | Frame sampler + scene detector + OCR worker | Queue hữu hạn; không OCR trùng vô hạn; chi phí frame/OCR nền được log |
| S04 | Absolute deadline end-to-end | Budget trừ phần đã tiêu tốn; timeout bao trùm queue/network/retry; connect timeout riêng không được coi là hard deadline 350ms |
| S05 | Policy feature/action trace | Ghi lý do request/skip/reuse; đo acquisition thật; speech feature kết hợp scene/cache/budget |
| S06 | Subtitle state/version và revision contract | Draft/commit rõ; sửa đúng segment ID và version; sau commit xử lý theo quy tắc đã chốt; không chỉ tô nhãn “đã sửa” |
| S07 | UI từ session state | Slide preview/time/entity là event thật; chọn policy tạo run tương ứng; hiện lỗi và export; không lấy EXP-004 làm RAM state của mọi video |
| S08 | Local demo reliability | Upload giới hạn kích thước và kiểm tra định dạng/truncated file; safe path; `textContent` cho text không tin cậy thay innerHTML; seek/reset không trộn event |

Đề xuất bắt đầu bằng chunk replay/retranslation + stable prefix commit đơn giản có quy tắc rõ. Không nhất thiết huấn luyện wait-k để hoàn thành vòng đầu; gọi đúng tên phương pháp triển khai.

## P1 — benchmark và bằng chứng nghiên cứu

- [ ] R01: matrix related work; đọc sâu các bài sát policy/visual context; rà lại DAP trong đề cương.
- [ ] R02: manifest, quyền sử dụng, guideline nhãn, transcript/reference độc lập, split theo nguồn.
- [ ] R03: CLI runner đọc config/manifest; cùng input/provider; không overwrite run; mock và oracle đánh dấu riêng.
- [ ] R04: A1/V1/V3/P chạy được; A0/V2 bổ sung theo nguồn lực; mọi arm có counters và error logs.
- [ ] R05: pilot kiểm tra OCR có lợi thực; tune score/TTL/budget trên dev; khóa config trước test.
- [ ] R06: human evaluation mù, metrics automatic với version/signature, thống kê theo nguồn.
- [ ] R07: ablation, stale/wrong evidence controls, uncertainty và error analysis; xuất source data cho figure.
- [ ] R08: report, reproducibility checklist, demo video, slide và chạy lại trên subset.

## P2 — mở rộng sau bằng chứng lõi

- [ ] Live mic/tab capture: capture timestamp, sample rate/resampling, network jitter/backpressure và kiểm tra riêng.
- [ ] TTS giọng tiêu chuẩn cho committed text; queue playback có giới hạn; latency speech output, drift và segment overlap.
- [ ] VLM cho biểu đồ/demo phi văn bản khi RQ và budget yêu cầu; thêm baseline phù hợp.
- [ ] Website public/multi-user sau khi có yêu cầu triển khai; rà session isolation, upload/API credentials và quyền dùng video trước deployment.

## Kiểm thử cần bổ sung khi thực hiện code

25 test hiện có pass là baseline kỹ thuật. Không cần mở rộng test chỉ để đếm số; ưu tiên regression cho lỗi thay đổi kết luận:

1. Provider spy nhận đúng OCR/context/action; real-provider smoke tách riêng và chỉ chạy khi môi trường đã cấu hình.
2. Không dùng frame tương lai hoặc OCR chưa available; hai session không dùng chung cache/history.
3. Timeout/cancel: không chặn ASR/UI; error/fallback được log và không biến thành output success.
4. Revision cập nhật nội dung đúng câu/version; committed prefix không thay ngoài protocol.
5. Reset/rerun/seek/upload: không AttributeError, không stale scene state/event.
6. Causal replay: event trước EOF; input chưa phát không được ASR/MT truy cập.
7. Runner counters gồm mọi OCR/MT/retry/background cost, không overwrite result; lỗi vẫn nằm trong denominator.

Các test OCR thật và provider thật có thể phụ thuộc model/mạng: phân tách unit/integration và ghi điều kiện bỏ qua, không báo một suite mock-only là xác nhận sản phẩm thật.
