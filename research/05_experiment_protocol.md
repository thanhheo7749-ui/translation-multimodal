# Protocol đề xuất: chất lượng – độ trễ – chi phí

Ngày: 07/10/2026. **Chưa có dữ liệu benchmark theo protocol này.** Cỡ mẫu, số run và ngân sách dưới đây là đề xuất; chốt sau pilot, trước test. Protocol áp dụng cho phụ đề video có slide Anh–Việt.

## 1. Giả thuyết và endpoint

- H1: dùng OCR đúng thời điểm có thể cải thiện độ đúng thuật ngữ/tham chiếu ở nhóm visual-useful so với audio có cùng text context.
- H2: selective OCR có thể giảm acquisition/cost so với OCR thường xuyên và scene-triggered OCR, trong biên chất lượng chấp nhận được.
- H3 phụ: deadline/TTL giảm deadline misses và sử dụng ngữ cảnh lỗi thời, nhưng có thể bỏ evidence hữu ích.

Endpoint chất lượng chính đề xuất: điểm adequacy do người đánh giá song ngữ chấm mù trên output cuối, thang 1–5 với guideline/anchor examples. Nếu không có người đánh giá phù hợp, coi nghiên cứu là pilot và nêu giới hạn; không thay human evaluation bằng nhãn `visual_grounded`.

Endpoint tài nguyên chính: số OCR inference mỗi phút video, kèm tổng thời gian OCR. Endpoint độ trễ chính: p95 lag từ cuối input unit được định nghĩa đến commit phụ đề. Báo first-draft lag riêng. Không gộp ba endpoint thành một score tùy ý sau khi thấy kết quả.

Biên chất lượng để kết luận “giữ chất lượng” phải được giảng viên/nhóm chốt từ mức sai khác có ý nghĩa thực tế sau pilot và trước test. Không có khác biệt có ý nghĩa thống kê chưa đủ chứng minh tương đương/non-inferiority. Nếu chưa chốt biên thì chỉ mô tả chênh lệch với interval, không kết luận giữ chất lượng.

## 2. Dữ liệu và annotation

Pilot đề xuất 40–60 segment từ 5–8 nguồn; benchmark tiếp theo đề xuất 200–300 segment từ 15–25 nguồn nếu thời gian/quyền sử dụng cho phép. Đây là mục tiêu thực hành, không phải power calculation hay bảo đảm đủ precision. Tăng nguồn độc lập sau pilot nếu interval còn quá rộng.

Lấy nhóm video: slide nhiều chữ/thuật ngữ; slide hoặc biểu đồ cần tham chiếu; slide nhiễu/animation; talking head ít visual value. Không chọn chỉ những câu keyword trigger đang xử lý tốt. Giữ đoạn liền mạch khi kiểm tra context/revision; không đưa isolated clips mất tiền ngữ rồi chấm anaphora như trong bài giảng đầy đủ.

Manifest đề xuất (schema, không phải mẫu dữ liệu thực):

```json
{
  "segment_id": "source01_seg001",
  "video_id": "source01",
  "source_group": "lecture01",
  "split": "test",
  "start_sec": 10.0,
  "end_sec": 16.0,
  "transcript_gold": "...",
  "translation_reference": "...",
  "visual_need": "useful",
  "visual_type": "slide_text",
  "reference_frame_time_sec": 12.0,
  "terms_to_preserve": [],
  "annotation_version": "v1",
  "rights_status": "to_be_verified"
}
```

Mọi dataset row cần nguồn, quyền dùng/chia sẻ, cách chọn segment, người gán nhãn (ID nội bộ), disagreement/adjudication và lý do loại nếu có. Reference được dịch/kiểm tra độc lập với output của các arm, có đủ ngữ cảnh video đúng thời điểm. Không dùng output proposed làm reference.

Visual need gồm `not_needed`, `useful`, `misleading`, `uncertain`; visual type gồm none/text/chart/demo. OCR không hiểu quan hệ trong chart chỉ nhờ đọc chữ: ghi rõ ca vượt năng lực, tránh gán “đã hiểu biểu đồ”. Đề xuất hai người gán nhãn độc lập trên subset và adjudication; báo số mẫu thực tế, mức đồng thuận và định nghĩa từng nhãn.

Split đề xuất khoảng 60/20/20 theo **source_group**; tất cả clip cùng bài nói nằm cùng split. Nếu cùng diễn giả/series có nội dung lặp, nhóm chúng khi split hoặc ghi rõ nguy cơ leakage. Điều chỉnh tỷ lệ theo số nguồn và độ phủ nhóm, rồi khóa manifest hash trước benchmark. Train chỉ cần khi học policy; rule/score dùng dev để tune và test để đánh giá.

## 3. Các arm và đối chứng công bằng

| ID | Thiết lập | Mục đích |
|---|---|---|
| A0 | Audio-only isolated, không OCR | Baseline chẩn đoán, không phải phép so sánh công bằng duy nhất |
| A1 | Audio + cùng cleaning/text context/revision setting, không OCR | Baseline chính để cô lập đóng góp visual |
| V1 | OCR mọi frame được sample ở cùng cadence, dùng cache causal | Đối chứng thường xuyên; “always” trong phạm vi sampled frames, không phải mọi frame 30 fps |
| V2 | OCR chu kỳ cố định, không theo lời nói | So sánh fixed schedule; chu kỳ tune trên dev |
| V3 | OCR khi scene đổi + cache/TTL | Baseline mạnh sát kiến trúc hiện có |
| P | Scene signal + speech need + cache age + remaining deadline → selective acquisition/use | Chính sách đề xuất |

Nếu thời gian thiếu, giữ A1/V1/V3/P; A0/V2 làm bổ sung. Một arm prior-work tái hiện chỉ được gọi là reproduction nếu đúng paper/protocol; policy tự viết theo ý tưởng paper phải gọi “inspired baseline”.

Tất cả arm dùng cùng video split, ASR transcript/chunk boundaries, provider/model version, prompt chung ngoài trường visual, decoding settings, cleaning/context/revision và phần cứng. Khác biệt do prompt length là một phần cost cần ghi. Cố định output alignment theo segment ID; không so baseline phrase output với proposed sentence output bằng cách ghép tùy ý.

Tách hai vòng: **gold transcript → MT** để cô lập tác động evidence; **ASR thật → MT** để đo pipeline. Gold transcript chỉ cung cấp theo prefix/thời điểm cho phép trong replay, không cho đọc câu chưa kết thúc trước giờ. Transcript ASR dùng chung giữa các arm ở vòng cô lập; vòng toàn pipeline phải có trace và lịch chạy tương đương.

## 4. Logging và định nghĩa độ trễ

Ghi media time và monotonic wall time riêng. Backend dùng một đồng hồ monotonic; browser đo render bằng clock của browser. Khi tính xuyên client/server cần ánh xạ/synchronization và sai số; không trừ hai epoch khác nhau rồi gọi ms chính xác.

Các trường tối thiểu: `run_id`, `session_id`, `video_id`, `segment_id`, `version`, `policy`, `provider`, `model`, `prompt_hash`, `config_hash`, `event_type`, `media_time`, `wall_time`, `status`, `error_code`, `input_cutoff`, `evidence_ids`.

Các mốc sự kiện: input/chunk available, ASR start/end, policy decision, OCR requested/start/end, translation start/end, draft/commit emitted, browser rendered. Cache entry ghi frame_time, acquired_at/available_at, source/video/session, confidence và expires_at.

- **ASR processing:** infer end − infer start; decode và capture wait báo riêng.
- **OCR processing:** OCR end − OCR start; acquisition/queue wait/retrieval riêng.
- **MT processing:** response end − request start; token counts, retries và timeout riêng.
- **First-draft lag:** draft rendered − wall time ánh xạ của source cutoff tương ứng.
- **Commit lag:** final version rendered − source cutoff đã chốt trong protocol. Báo thêm từ segment end khi cần so giữa các câu.
- **Input wait:** source cutoff − thời điểm bắt đầu segment; để câu 10 giây không bị trình bày thành latency 350 ms mà bỏ qua chờ lời nói.
- **RTF:** thời gian xử lý / thời lượng input; báo offline throughput riêng với causal replay wall duration. Replay 1× tự nó không chứng minh compute RTF=1 hay đạt lag target.
- **Deadline miss:** output không commit trước deadline tuyệt đối, hoặc timeout/failure tương ứng. Báo tỷ lệ trên mọi segment đủ điều kiện; không loại timeout khỏi denominator.

Warm-up/cold-start báo riêng. Đề xuất ba lượt lặp đo timing cho mỗi cấu hình sau warm-up, thứ tự arm đổi/cân bằng qua lượt; lặp kỹ thuật không làm tăng số nguồn độc lập. Nếu API nondeterministic, lưu output/response metadata từng run; chốt run/aggregation để chấm trước khi xem điểm. Không chọn run đẹp nhất.

## 5. Metrics bổ sung

| Nhóm | Metrics | Cách dùng |
|---|---|---|
| Translation | COMET checkpoint được kiểm tra, chrF, corpus BLEU với signature/version | Metric tự động bổ sung; cùng preprocessing, output cuối, reference cố định |
| Human | Adequacy; lỗi thuật ngữ, thiếu ý, thêm ý, sai tham chiếu | Chấm mù model/policy; thứ tự output xáo trộn; rubric chung |
| ASR | WER trên transcript gold; lỗi thuật ngữ | Tách lỗi ASR khỏi lỗi dịch/OCR |
| Visual | OCR calls/min, CER trên subset text có gold, stale evidence usage, useful acquisitions | Một scene đúng chưa đồng nghĩa một bản dịch đúng |
| Latency | p50/p95 first draft/commit, miss rate, input wait, queue age | Báo cả distribution và mẫu bị timeout |
| Resources | OCR compute time, frame decode/sample time, CPU/RAM, peak VRAM, MT calls/tokens, revision calls | Tính cả worker nền và mọi retry; query RAM cache không đại diện acquisition cost |
| Stability | Revision count, edit distance giữa versions, thời gian ổn định | Định nghĩa tokenization/normalization; không so nhiều lần render cùng version |

API cost chỉ tính tiền khi có pricing snapshot/date và token usage thật. Nếu thiếu usage/pricing thì báo calls/tokens hoặc “unknown”, không dựng USD. Số CPU time/VRAM phải ghi cách đo và overhead monitor.

Average Lagging theo [STACL](https://aclanthology.org/P19-1289/) và giao thức [SimulEval](https://aclanthology.org/2020.emnlp-demos.19/) chỉ bổ sung khi đã định nghĩa read/write stream và alignment phù hợp. Với output có revision, phải báo revision/stability riêng; không gọi random phrase replay là simultaneous evaluation. [COMET](https://aclanthology.org/2020.emnlp-main.213/) hỗ trợ đánh giá MT học từ human judgments, nhưng không thay rubric riêng cho OCR-grounded Anh–Việt.

## 6. Ablation và negative controls

Đề xuất các so sánh phụ trên tập đã khóa: P không OCR; P không text context; P không cleaning; P không revision; P không TTL; P không deadline gating. Chỉ thay một thành phần mỗi lần. Nếu chạy ít mẫu hơn do chi phí phải công bố subset và cách chọn trước.

Controls: OCR đúng; OCR của slide sai nhưng đã xuất hiện trước đó; evidence rỗng; evidence nhiễu trong nhóm misleading. Negative control đo grounding, không nhằm đòi model luôn bị evidence sai làm hỏng.

Oracle dùng nhãn visual_need và evidence tốt nhất có thể được chạy **offline**, chỉ để chẩn đoán upper bound. Không tính oracle dùng tương lai thành baseline causal/live. Thêm regression test: evidence frame 120s không được dùng cho segment 0–35s và evidence OCR chưa hoàn tất không được đọc.

## 7. Thống kê và báo cáo

Đơn vị độc lập mặc định là nguồn/bài nói (`source_group`); segment là đơn vị con, repeated timing runs là lặp kỹ thuật. Báo cả số nguồn, video, segment và run thực tế. 300 câu từ một keynote không phải 300 nguồn độc lập.

Phân tích paired vì các arm cùng xử lý một input. Đề xuất paired cluster bootstrap theo source_group với confidence interval 95% cho chênh lệch chất lượng/tài nguyên, sau khi xác nhận đủ số cụm và cấu trúc nguồn; ghi seed/số resample thực tế lúc chạy. Nếu nguồn ít, ưu tiên bảng per-source và interval mô tả thận trọng, không ép một test không phù hợp.

Chốt primary comparisons trước test: P vs A1 cho chất lượng nhóm visual-useful; P vs V3 và V1 cho resource/quality trade-off toàn tập. Nếu dùng nhiều kiểm định, xác định family và correction (ví dụ Holm) trước khi chạy; subgroup/ablation ghi exploratory. Không kết luận nhóm này tốt hơn nhóm kia chỉ vì một nhóm có p-value nhỏ và nhóm kia không.

Quality báo macro per-source và micro per-segment với lý do weighting. Resource báo per-video-minute và total. Timeout output phải có quy tắc: nếu fallback có bản dịch thì chấm bản người dùng thực nhận; nếu không có output thì tính failure và báo quality có điều kiện kèm tỷ lệ coverage. Giữ lỗi trong latency/miss/cost; không im lặng bỏ dòng lỗi.

## 8. Artifact và tiêu chí kết thúc

Thư mục run đề xuất: `experiments/runs/<run_id>/` gồm config.json, manifest hash, environment.txt, events.jsonl, outputs.jsonl, failures.jsonl, metrics.json và human_scores.csv. Đây là cấu trúc cần triển khai, chưa có runner tạo tự động.

Đủ để báo cáo khi: dữ liệu test khóa trước tuning; output do provider thật; trace causal hợp lệ; baseline công bằng; không thiếu log lỗi; metrics có định nghĩa/version; kết luận có interval và giới hạn. Nếu chỉ pilot, ghi đúng là pilot. Lập luận có thể hoàn chỉnh ngay cả khi P không thắng, miễn dữ liệu và phương pháp đáng tin.
