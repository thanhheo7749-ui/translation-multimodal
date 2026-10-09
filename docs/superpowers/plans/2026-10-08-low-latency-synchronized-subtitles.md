# Low-Latency Synchronized Subtitles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Keep each measured change separate; do not infer successful browser playback from unit tests.

**Goal:** Phụ đề Anh–Việt dễ đọc, ít sửa chữ và gần thời điểm lời nói người xem nghe được; đo rõ chất lượng, độ trễ và nội dung bị mất.

**Architecture:** Thu âm, ASR, dịch và trình phát hoạt động độc lập, trao đổi đoạn có session ID và timestamp nguồn. Hai chế độ: phát sát nguồn với phụ đề có độ trễ; hoặc trì hoãn đồng thời hình và tiếng để có thời gian chuẩn bị phụ đề khớp trình phát. Model local là ứng viên cần đo, không mặc định là lời giải.

**Tech Stack:** JavaScript/AudioWorklet, Python HTTP backend, faster-whisper, Gemini Lite; NLLB/PyTorch CUDA cho phép so sánh đã chuẩn bị. Không thêm OCR vào đường xử lý thời gian thực trước khi kiểm chứng nền audio.

---

## 1. Trả lời câu hỏi khả thi

Có thể tạo trải nghiệm phụ đề xuất hiện dần và bám gần lời nói. Không thể bảo đảm đồng thời **không trễ, luôn đúng nghĩa và không sửa chữ** cho mọi câu chưa nói xong. Máy cần nghe đủ âm thanh; tiếng Việt có thể cần thông tin hoặc trật tự khác tiếng Anh. Dự đoán phần chưa nói có thể nhanh nhưng có nguy cơ sai. Không dùng dự đoán như transcript chắc chắn.

Chép tiếng Anh đang nói và dịch sang tiếng Việt là hai mục tiêu khác nhau. Không có ánh xạ một-một giữa âm tiết tiếng Anh và chữ tiếng Việt; đơn vị đồng bộ hợp lý là **cụm nghĩa ngắn**, không phải từng chuyển động môi hoặc từng token model. STACL nghiên cứu chính đánh đổi này; kết quả của bài không phải số đo cho cặp Anh–Việt trên máy hiện tại. [STACL, ACL 2019](https://aclanthology.org/P19-1289/).

## 2. Bằng chứng hiện tại và những gì chưa biết

| Quan sát | Bằng chứng | Hệ quả cho kế hoạch |
|---|---|---|
| Cắt cố định 2,5 giây từng gây mất từ ở biên | `research/13_live_asr_segmentation_fix.md` | Không quay lại chia những khối rời chỉ để giảm con số latency |
| ASR hiện cập nhật trên audio chồng nhau; chốt tiền tố trùng hai lần | `frontend/live-core.js`, `frontend/live.js` | Kiểm tra tác dụng và lỗi thực tế, không coi đã tương đương bản Whisper-Streaming đã được đánh giá |
| Riêng 20 request Gemini lịch sử có median 2,335 s, max 8,086 s | `research/16_caption_visibility_and_parallel_mt.md` | Mục tiêu tổng trễ dưới 1 s không phù hợp cấu hình API đã đo |
| Hai request MT song song xong trong 2,172 s ở một phép thử | `experiments/runtime_logs/parallel_mt_smoke.json` | Giảm chờ nối tiếp, không chứng minh một câu dịch nhanh hơn hoặc toàn pipeline đã theo kịp |
| Ẩn phụ đề muộn tạo khoảng trống; giữ câu cũ tạo lệch cảnh | Lịch sử các bản 15–16 và phản hồi người dùng | Tách chính sách đọc phụ đề khỏi cơ chế đồng bộ AV |
| NLLB chưa có phép chạy local thành công | `research/17_local_vs_gemini_status.md` | Chạy benchmark trước khi chọn engine |
| Chỉ số `lagMs` hiện bắt đầu tại gói cuối snapshot ASR | `frontend/live.js` | Chưa đo đủ thời gian chờ nghe, chốt câu và trễ từ lời nói tới mắt người xem |

Các lần sửa trước đã đổi nhiều tham số nhưng chưa có một phiên Chrome đủ event trace và transcript chuẩn. Ưu tiên đầu tiên là đo đúng; không tiếp tục tăng/giảm thời gian giữ chữ để tuyên bố đã giảm độ trễ.

## 3. Hai chế độ sản phẩm

### A. Phát sát nguồn

- Người xem nghe âm thanh gốc ngay khi nguồn phát.
- ASR có nháp và phần chốt; chỉ phần đủ tin cậy mới đi vào bản dịch chính.
- Phụ đề xuất hiện theo cụm khi sẵn sàng; có độ trễ thực và không hứa khớp từng âm tiết.
- Dùng cho micro và tab ngoài mà ứng dụng không điều khiển được việc phát.

### B. Ưu tiên đồng bộ — đề xuất cho video NVIDIA trong ứng dụng

- Đầu vào vẫn chạy theo thời gian thực; bộ xử lý chỉ được dùng audio đã đến.
- Trình phát người xem nhìn **và âm thanh người xem nghe** chậm hơn đầu vào một khoảng D.
- Phụ đề được xếp theo timestamp và trình chiếu trên video đã trì hoãn. Không phát cả âm thanh nguồn và âm thanh trì hoãn gây tiếng đôi.
- Đây là thêm trễ so với nguồn để giảm lệch giữa chữ và lời nói người xem cảm nhận, không phải giảm thời gian tính toán.
- Thử D = 2, 4, 6 giây trên tập phát triển rồi chọn bằng số đo. Không tuyên bố một giá trị đủ cho mọi request hoặc mọi câu.
- Nguồn YouTube ở tab khác vẫn tự phát tiếng: chỉ có thể cung cấp chế độ B nếu đưa nguồn qua trình phát của ứng dụng hoặc người dùng tắt tiếng nguồn và nghe đầu ra trì hoãn. Overlay trên tab ngoài không tự trì hoãn được âm thanh nguồn.

**Ví dụ có cùng đồng hồ:** đầu vào nói một cụm từ giây 10 đến 12; bản dịch sẵn sàng giây 13. Với D = 3 giây, người xem nghe cụm ở giây 13–15 và phụ đề có thể xuất hiện ngay đầu cụm. Họ đang xem chậm nguồn 3 giây. Nếu bản dịch chỉ sẵn sàng giây 16 thì vẫn bị trễ; cần ghi nhận, không che kết quả.

Nếu muốn phụ đề của cả cụm sẵn sàng từ **đầu** cụm, phải đo thời gian từ đầu cụm đến khi dịch sẵn sàng. Chỉ lấy latency tính từ cuối cụm để chọn D sẽ thiếu chính thời lượng cụm.

## 4. Mục tiêu nghiệm thu dự kiến

Các ngưỡng dưới đây là **mục tiêu kỹ thuật để thử**, không phải thành tích đã có hoặc chuẩn bắt buộc.

| Chỉ số | Mục tiêu thử trên tập phát triển | Cách xử lý nếu không đạt |
|---|---|---|
| Trễ tới bản dịch đầu tiên, chế độ A, tính từ cuối cụm chuẩn | median ≤ 2 s; p95 ≤ 4 s | Đổi cấu hình/model sau benchmark; công bố số thực tế nếu chưa đạt |
| Chế độ B | ≥ 95% cụm có bản dịch sẵn lúc cụm bắt đầu phát cho người xem với D đã chọn | Tăng D có thông báo hoặc đánh dấu muộn; không tự đổi tốc độ/nhảy hình |
| Lệch lịch hiển thị so với cue trong chế độ B khi đã sẵn sàng | p95 sai số tuyệt đối ≤ 250 ms | Kiểm tra đồng hồ, player, tab nền và bộ lập lịch; đây không phải độ đúng timestamp ASR |
| Chữ đã chốt bị sửa/xóa | 0 trong chế độ ổn định | Kiểm tra state machine; đo riêng lỗi nghĩa bị chốt quá sớm |
| Phản hồi cũ làm quay về cue cũ | 0 | Chặn theo session/version và ghi số cue không được hiển thị |
| Cụm bị bỏ âm thầm | 0 | Mọi overflow, lỗi hoặc deadline miss phải có log |
| Chất lượng | Báo WER, lỗi xóa từ, lỗi nghĩa và thuật ngữ; không chấp nhận nhanh nhờ mất câu | Duyệt mẫu trước khi khóa biên chất lượng để nghiệm thu |

Không coi chữ đứng yên nhưng sai nghĩa là thành công. Không coi xóa hết phụ đề muộn là giảm latency. Không coi số lần lặp một video là số nguồn độc lập.

## 5. File và trách nhiệm

| File | Vai trò trong kế hoạch |
|---|---|
| `frontend/live.js` | Kết nối stage, ghi event, chọn chế độ và reset session |
| `frontend/live-core.js` | Buffer audio, xác nhận phần ổn định; giữ test chống mất/lặp từ |
| `frontend/pcm-worklet.js` | Thu PCM và số thứ tự mẫu; không chạy model ở audio callback |
| `frontend/caption-timing.js` — mới | Hợp đồng clock, event trace và tính chỉ số nguồn/hiển thị |
| `frontend/subtitle-scheduler.js` — mới | Hàng đợi cue, timestamp, thời gian đọc, chống phản hồi cũ |
| `frontend/delayed-playback.js` — mới, chỉ sau cổng đo lường | Đồng hồ đầu vào và trình phát AV trì hoãn của video nội bộ |
| `frontend/live.html`, `frontend/live.css` | Hai chế độ, phụ đề hai dòng, nhãn trễ và trạng thái chờ |
| `backend/asr/whisper_engine.py` | Lựa chọn CPU/GPU và thông số ASR sau phép đo riêng |
| `backend/server.py` | Trả stage timing và phục vụ asset mới; không gắn khóa API vào log |
| `experiments/compare_local_translation.py` | So sánh MT local/API đã có; giữ nguyên input giữa các model |
| `experiments/subtitle_eval.py` — mới | Tổng hợp trace với nhãn chuẩn và coverage; không loại lỗi khỏi mẫu số |

Không dùng `backend/translation/local_provider.py` hiện tại làm bằng chứng tốc độ: đây còn là skeleton. Không tự tải/cài lại model nếu phép thử local chưa hoàn thành.

## 6. Thứ tự công việc và cổng quyết định

### Task 1 — Ghi một phiên có thể truy vết, trước khi tối ưu tiếp

**Files:** tạo `frontend/caption-timing.js`, `tests/test_caption_timing_js.cjs`; chỉnh điểm gọi trong `frontend/live.js`, xuất trace cùng log phiên.

- [ ] Viết test cho mốc nguồn, thời điểm có kết quả và thời điểm chữ thực sự được chọn để hiển thị. Có ca request trả sớm nhưng cue đang chờ hiển thị.
- [ ] Chạy `node tests/test_caption_timing_js.cjs`; xác nhận test chưa có implementation bị fail trước khi thêm helper.
- [ ] Dùng hợp đồng tính toán tối thiểu sau, mọi giá trị đều theo **giây trên cùng đồng hồ client**:

```javascript
function measureCue({sourceStart, sourceEnd, readyAt, shownAt, viewerDelay}) {
  if (![sourceStart, sourceEnd, readyAt, shownAt, viewerDelay].every(Number.isFinite))
    throw new Error('Missing cue clock');
  if (sourceEnd < sourceStart || shownAt < readyAt || viewerDelay < 0)
    throw new Error('Invalid cue order');
  return {
    readyFromStart: readyAt - sourceStart,
    readyFromEnd: readyAt - sourceEnd,
    displayFromEnd: shownAt - sourceEnd,
    visibleStartOffset: shownAt - (sourceStart + viewerDelay)
  };
}
```

Test lõi, trong module CommonJS của file test:

```javascript
const assert = require('node:assert/strict');
const {measureCue} = require('../frontend/caption-timing.js');
assert.deepEqual(measureCue({sourceStart:10,sourceEnd:12,readyAt:13,shownAt:13,viewerDelay:3}), {
  readyFromStart:3,readyFromEnd:1,displayFromEnd:1,visibleStartOffset:0
});
assert.equal(measureCue({sourceStart:10,sourceEnd:12,readyAt:13,shownAt:15,viewerDelay:3}).visibleStartOffset,2);
assert.throws(()=>measureCue({sourceStart:10,sourceEnd:12,readyAt:13,shownAt:11,viewerDelay:0}));
```

- [ ] Ghi các event: `audio_received`, `asr_requested`, `asr_returned`, `source_committed`, `mt_requested`, `mt_returned`, `cue_selected`, `cue_hidden`, `cue_skipped`. Mỗi event có `sessionId`, `segmentId`, `version`, `clientNowMs`, `sourceStart`, `sourceEnd`, `reason` khi lỗi/bỏ.
- [ ] Đổi tên `displayedAt` hiện tại thành `translationReadyAt` ở điểm nhận response; chỉ ghi `shownAt` khi presenter chọn cue mới. Ghi thời điểm DOM cập nhật/requestAnimationFrame là phép xấp xỉ hiển thị, không tự coi là thời điểm photon/âm thanh tới người xem.
- [ ] Giữ duration backend từ `perf_counter` riêng; không trừ trực tiếp nó với `performance.now()` của browser. Khi pause, seek, đổi tốc độ hoặc đổi nguồn, lập epoch mới cho ánh xạ media time.
- [ ] Chạy NVIDIA 3 phút ở Chrome, tốc độ 1×, xuất log. Gán mốc thủ công tối thiểu 30 cụm trong cùng đoạn; kiểm tra trực tiếp audio/video gốc thay vì dùng timestamp Whisper làm ground truth.
- [ ] Cổng hoàn thành: có thể giải thích một cue chậm bao nhiêu ở từng stage và cue nào chưa hiện. Nếu không ánh xạ được clock, sửa phép đo trước; không thay model để che thiếu số liệu.

### Task 2 — So model trên dữ liệu đã cố định

**Files:** `experiments/compare_local_translation.py`, `experiments/local_comparison_cases.json`; output dưới `experiments/local_comparison/`.

- [ ] Chạy launcher đã có: `./run_local_comparison.cmd`. Nếu không tải được, lưu trạng thái blocked và tiếp tục task đo/UI không phụ thuộc local; không báo đã chạy GPU.
- [ ] Kiểm tra `results.json`: tên model, device, revision, thời gian tải/nạp, warmup, mỗi bản dịch, lỗi, GPU peak. Xác nhận local thực sự là CUDA nếu so cấu hình GPU.
- [ ] Bắt đầu với sáu câu đã có để xác nhận chạy được; sau đó đo lại tập cụm ngắn từ trace Task 1, không chỉ câu đầy đủ thuận lợi cho NLLB.
- [ ] Chạy ba lượt cùng input, xáo trộn thứ tự như runner hiện có. Đọc bản dịch và đánh dấu lỗi nghĩa/thuật ngữ trước khi chọn cấu hình nhanh nhất.
- [ ] Cổng lựa chọn: model được giữ nếu giảm thời gian xử lý nhưng không đổi tốc độ lấy dữ liệu, không âm thầm mất cụm và không tăng lỗi nghĩa nghiêm trọng trên các câu đã duyệt. Nếu NLLB không đạt, giữ Gemini làm đối chứng và thử model local khác trong phép thử riêng.

NLLB là model dịch câu, không tự trở thành simultaneous MT khi nạp local. Thử cắt cụm và chốt bản dịch vẫn là một phần riêng. Không so hai provider với prompt/context khác nhau rồi quy toàn bộ chênh lệch cho model.

### Task 3 — Tối ưu nhận dạng mà không làm mất lời nói

**Files:** `frontend/live-core.js`, `frontend/live.js`, `backend/asr/whisper_engine.py`; tests `tests/test_live_audio_js.cjs`, `tests/test_live_pipeline_js.cjs`, `tests/test_live_audio.py`.

- [ ] Lưu cấu hình baseline hiện tại: hop 1,5 s, window tối đa 12 s, beam 5, CPU int8, tiền tố đồng thuận hai lần.
- [ ] Thử hop 1,0 s và 0,75 s riêng từng lượt; không đổi beam cùng lúc. Nếu thời gian ASR dài hơn chu kỳ lặp và queue tăng, không giảm hop tiếp.
- [ ] Thử CPU/GPU ở cấu hình đã chọn; chạy cùng MT để đo tranh chấp VRAM và thời gian thực, không suy từ benchmark ASR chạy riêng.
- [ ] Kiểm tra lời lặp có chủ ý, nói nhanh không nghỉ, tên riêng, số, tiếng vỗ tay, pause/seek và phần câu cuối. Ví dụ bắt buộc: `many of you, many of you` không bị dedup thành một lần.
- [ ] Mỗi thay đổi có test lỗi riêng trước khi sửa. Chạy `node tests/test_live_audio_js.cjs`, `node tests/test_live_pipeline_js.cjs`, `./.venv/Scripts/python.exe -m unittest tests.test_live_audio`.
- [ ] Cổng hoàn thành: queue không tăng kéo dài trong đoạn 3 phút và WER/lỗi xóa từ không xấu đi so với baseline đã đo. Nếu không đạt, đánh giá backend ASR streaming khác trong một nhánh nghiên cứu riêng; không hứa đổi thư viện sẽ tự giải quyết.

### Task 4 — Chốt cụm nghĩa và trình bày ổn định

**Files:** tạo `frontend/subtitle-scheduler.js`, `tests/test_subtitle_scheduler_js.cjs`; nối từ `frontend/live.js`; trình bày ở `frontend/live.html` và `frontend/live.css`.

- [ ] Cue có hợp đồng thống nhất: `{sessionId, segmentId, version, sourceStart, sourceEnd, text, status, translationReadyAt}`; status chỉ `draft`, `committed`, `failed`. Chuỗi đã committed không bị thay tại chỗ trong chế độ ổn định.
- [ ] Giữ dịch theo cụm ngắn có nghĩa; thử khoảng 3–7 từ làm tín hiệu phụ, không dùng đúng số từ làm luật cắt tuyệt đối. So lỗi câu cụt trong đánh giá Task 2.
- [ ] Viết ca test: bản nháp có sửa phần đuôi; phần committed không đổi; response ID cũ không quay ngược; response thiếu được đếm; chuyển session loại hết cue cũ.
- [ ] Giữ vùng hai dòng cố định. Ngắt ở khoảng trắng/cụm nghĩa, không chạy hiệu ứng gõ từng ký tự, không thay câu đang đọc bằng thông báo “Đang dịch”. Thử thời gian đọc theo chiều dài: `Math.min(6, Math.max(1.2, text.length / 15))` giây là cấu hình ban đầu để đánh giá, không coi là chuẩn đọc tiếng Việt.
- [ ] Nếu text dài hơn sức chứa hai dòng, tách thành cue kế tiếp có log; không CSS-clamp làm mất chữ rồi báo đã hiển thị hết. Khi live bắt kịp bằng cách bỏ cue, tăng bộ đếm `not_presented` riêng với `asr_dropped`.
- [ ] Đo xóa token đã hiển thị, số lần thay cả vùng chữ, coverage thực sự được trình chiếu và thời gian có chữ để đọc. Tách việc cue kết thúc bình thường khỏi sửa/xóa bản dịch trong cùng cue. Flicker/erasure là một trục đánh giá riêng trong nghiên cứu retranslation. [EACL 2023](https://aclanthology.org/2023.eacl-main.270/).
- [ ] Cổng hoàn thành: ca phản hồi đảo thứ tự, timeout và câu dài đạt kiểm tra; có video ghi màn hình để xác nhận đọc được. Unit test không thay thế đánh giá hình ảnh/âm thanh.

### Task 5 — Bộ đệm AV và lịch phụ đề theo thời gian nguồn

**Files:** tạo `frontend/delayed-playback.js`, `tests/test_delayed_playback_js.cjs`; chỉnh `frontend/live.js`, `frontend/live.html`, `frontend/subtitle-scheduler.js`.

Đây là thay đổi kiến trúc có điều kiện: chỉ triển khai sau khi Task 1 đo đúng clock và Task 4 có cue ổn định. Thiết kế tập trung video NVIDIA trong ứng dụng; không tự sửa nguồn phát ở tab ngoài.

- [ ] Tách `ingestCursor` và `presentationCursor`. Âm thanh đưa vào ASR chỉ tới `ingestCursor`, tiến tối đa theo tốc độ thời gian thực; trình phát AV dùng `presentationCursor = ingestCursor - D` sau giai đoạn nạp đệm. Pause thì dừng cả hai đồng hồ; seek tạo session mới và nạp lại D. Kết thúc nguồn phải xả phần trình phát còn D giây.
- [ ] Cấm giải mã gửi cả file tới ASR trước khi nguồn đến. Dù browser tải sẵn tệp vào cache, watermark xác định mẫu được phép xử lý, không phải khả năng đọc tệp trên ổ cứng.
- [ ] Chỉ đường trình phát trì hoãn được phát tiếng tới loa. Đầu vào xử lý không phát tiếng; chạy kiểm tra không có âm thanh đôi, không chỉ nhìn hai thanh `currentTime`.
- [ ] Bộ lập lịch cue dùng **presentation media time**, không dùng thời điểm request vừa trả về. Cue chỉ hiện khi tới khoảng thời gian nguồn tương ứng trên trình phát.
- [ ] Các assertion bắt buộc cho bài kiểm tra clocks:

```javascript
const assert = require('node:assert/strict');
const ingest = 14, delay = 4, presentation = Math.max(0, ingest-delay);
assert.equal(presentation,10);
const cue = {sourceStart:10,sourceEnd:12,readyAt:13};
assert.ok(cue.readyAt <= 14); // Kịp đầu cụm khi người xem bắt đầu nghe ở wall time 14.
assert.ok(presentation >= cue.sourceStart && presentation < cue.sourceEnd);
const latestAllowedAudioSample = Math.floor(ingest*16000);
assert.equal(latestAllowedAudioSample,224000); // Không gửi mẫu > watermark này.
```

- [ ] Chạy D = 2, 4, 6 s riêng, không tự tăng giảm D giữa câu gây giật. Chọn D dựa trên phân phối `readyFromStart`, không chỉ `readyFromEnd`; báo cả tỷ lệ deadline miss và số giây chậm nguồn.
- [ ] Khi cue muộn hơn trình phát: log `deadline_missed`; không tua giật để đuổi theo. Hiển thị tình trạng chậm trong panel và giữ bản dịch ở lịch sử. So sánh phương án này với chế độ A vốn vẫn cho đọc chữ muộn kèm nhãn.
- [ ] Cổng hoàn thành: ghi được một phiên mà AV vẫn khớp nhau, caption theo presentation time, D được hiển thị cho người dùng, pause/seek/end không để sót tiếng hoặc cue phiên cũ. Nếu mọi D thử đều không đủ, công bố giới hạn thay vì gọi là “đồng bộ”.

### Task 6 — Nghiệm thu trải nghiệm và báo cáo nghiên cứu

**Files:** tạo `experiments/subtitle_eval.py`, `research/18_subtitle_latency_evaluation.md`; giữ trace thô theo run ID.

- [ ] Dùng NVIDIA làm tập phát triển; bổ sung tối thiểu ba video độc lập chưa dùng để chỉnh tham số. Chốt thông số trước khi chạy tập kiểm tra; transcript chuẩn và mốc cụm cần được người duyệt.
- [ ] So ba cấu hình: baseline hiện tại; pipeline tối ưu phát sát nguồn; cùng pipeline tối ưu với AV trì hoãn. Giữ cùng source, ASR/MT và chất lượng âm thanh khi cô lập tác dụng của bộ đệm.
- [ ] Báo median/p95 ready-lag và display-lag, D so với nguồn, sai số lịch hiển thị, WER/lỗi xóa, lỗi nghĩa/thuật ngữ, erasure, độ phủ và deadline miss. Không loại mất câu khỏi mẫu số; request lỗi không có latency thành công nhưng phải báo riêng.
- [ ] Cho người xem đọc cùng đoạn bằng các cấu hình theo thứ tự đảo, ghi mức dễ đọc, cảm giác lệch và mất nội dung. Đây là thăm dò UX, chưa coi là nghiên cứu người dùng đủ lực thống kê.
- [ ] Chạy regression đã có và kiểm tra browser thực; lưu version model, phần cứng, cấu hình, snapshot code, trạng thái mạng. Commit từng thay đổi khi thực hiện trong Git checkout; nếu workspace không có Git thì lưu bản chụp cùng run, không tạo lịch sử giả.
- [ ] Chỉ chọn cấu hình khi có bằng chứng chất lượng–latency–độ ổn định cùng đạt mục tiêu đã chốt. Nếu không đạt, báo kết quả âm và giới hạn phần cứng/engine.

## 7. Mốc triển khai dự kiến

Ước lượng cho một người, sau khi có dữ liệu/model; không bao gồm thời gian tải model hoặc chờ người duyệt transcript:

1. **1 ngày:** Task 1, tạo một trace đáng tin và phát lại được lỗi.
2. **1–2 ngày:** Task 2–3, chọn cấu hình có số đo thay cho phỏng đoán local/API.
3. **1 ngày:** Task 4, cue ổn định, đọc được và đếm đúng nội dung chưa hiện.
4. **1–2 ngày:** Task 5 cho video trong ứng dụng, nếu các cổng trước đã đạt.
5. **1–2 ngày:** Task 6, chạy tập kiểm tra và báo cáo trade-off.

Thứ tự ưu tiên cho nhu cầu người dùng: **đo đúng → chọn engine đủ nhanh → cue ổn định → chế độ AV trì hoãn để khớp hình/tiếng/chữ**. Không hứa model local tự đạt “đọc tới đâu dịch đúng ngay tới đó”.

## 8. Nguồn và tự kiểm tra kế hoạch

- [Whisper-Streaming, 2023](https://aclanthology.org/2023.ijcnlp-demo.3/): xác nhận tiền tố qua nhiều lần nhận dạng là một hướng có cơ sở; số đo của bài không dùng làm số đo của bản custom trong dự án.
- [STACL, 2019](https://aclanthology.org/P19-1289/): dịch trước khi kết thúc câu có đánh đổi ngữ cảnh/trật tự từ/latency; không phải cứ cắt câu rồi dùng model dịch offline là tương đương wait-k đã huấn luyện.
- [From Delay to Display, 2021](https://aclanthology.org/2021.mtsummit-asltrw.4/): phụ đề đọc được cần đánh giá cách trình bày cùng chất lượng dịch, không chỉ tốc độ engine.
- [Self-training Reduces Flicker, 2023](https://aclanthology.org/2023.eacl-main.270/): độ ổn định retranslation cần đo riêng; không viện dẫn để khẳng định cơ chế hiện tại đã tối ưu.

Tự kiểm tra: yêu cầu tốc độ được nối Task 1–3; bám lời nói Task 5; ít flicker Task 4; không dịch trước Task 5 watermark; so local/API Task 2; kiểm chứng Task 6. Mọi ngưỡng và thời gian triển khai là đề xuất. Kế hoạch chưa được triển khai trong lượt lập kế hoạch này; không có số đo local mới.
