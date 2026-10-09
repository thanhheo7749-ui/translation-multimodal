# Project Plan — Adaptive Multimodal Translation

## 1. Tổng quan dự án

### Tên tạm thời

**Adaptive Multimodal Evidence Acquisition for Real-Time Video Translation and Dubbing**

Tên ngắn:

> **Adaptive Multimodal Translation under Real-Time Constraints**

### Ý tưởng cốt lõi

Thay vì xây dựng một hệ thống luôn sử dụng tất cả dữ liệu đa phương thức (audio + video + OCR + vision), hệ thống sẽ **tự quyết định khi nào cần lấy thêm thông tin** để cải thiện bản dịch.

Ví dụ:

- Người nói một câu đơn giản → chỉ cần audio/transcript → dịch ngay.
- Người nói: “Như bạn có thể thấy trên màn hình…” → lấy frame.
- Slide có bảng số liệu → lấy frame + OCR/vision.
- Một câu có từ ngữ mơ hồ → lấy thêm visual/context.
- Hình ảnh không chứa thông tin hữu ích → bỏ qua để giảm latency/cost.

Mục tiêu:

> **Tối đa hóa chất lượng dịch trong khi vẫn đáp ứng giới hạn về latency và chi phí tính toán/API.**

---

## 2. Vấn đề thực tế

Các hệ thống dịch video/livestream hiện nay thường đi theo một trong hai hướng:

### Audio-only

```text
Audio → ASR → Translation → TTS
```

Ưu điểm:

- Nhanh.
- Rẻ.
- Dễ triển khai.

Nhược điểm:

- Không hiểu thông tin xuất hiện trên màn hình.
- Không xử lý tốt các trường hợp phụ thuộc visual context.
- Có thể sai với tên riêng, biểu đồ, text trên màn hình, gesture hoặc ngữ cảnh trực quan.

### Always-multimodal

```text
Audio + Video → Multimodal Model → Translation
```

Ưu điểm:

- Có nhiều context hơn.

Nhược điểm:

- Tốn GPU/API.
- Tăng latency.
- Không phải frame nào cũng có giá trị.
- Trong livestream, việc xử lý liên tục toàn bộ video rất tốn tài nguyên.

### Khoảng trống cần nghiên cứu

Điểm quan trọng không phải là:

> “Làm sao để dùng video để dịch tốt hơn?”

Vấn đề thú vị hơn là:

> **“Khi nào hệ thống nên lấy thêm visual evidence để đáng với latency và chi phí bỏ ra?”**

---

# 3. Research Question

## RQ chính

> Can an adaptive multimodal policy selectively acquire visual and textual evidence only when it is expected to improve real-time translation quality, while satisfying a strict latency and computational budget?

Nói đơn giản:

> Hệ thống có thể tự quyết định **khi nào cần nhìn vào video** để cải thiện bản dịch mà vẫn đảm bảo real-time hay không?

## Sub-RQ

### RQ1 — Khi nào audio-only không đủ?

Xác định những tình huống visual evidence thực sự có giá trị.

Ví dụ:

- Demonstration.
- Gesture.
- Chart.
- Subtitle/text.
- Product information.
- Speaker reference.
- Wordplay.
- Ambiguous expressions.

### RQ2 — Có thể dự đoán khi nào visual evidence hữu ích không?

Input có thể gồm:

- ASR confidence.
- Translation uncertainty.
- Context length.
- Semantic ambiguity.
- Keywords.
- Speaker cues.
- Previous visual evidence.
- Time since last frame acquisition.

Output:

```text
Need Visual Evidence?
YES / NO
```

### RQ3 — Nếu cần visual thì nên lấy loại evidence nào?

Action space:

```text
TRANSLATE_NOW
GET_FRAME
GET_MORE_FRAMES
RUN_OCR
RUN_VISION
GET_MORE_AUDIO_CONTEXT
WAIT_FOR_CONTEXT
STOP
```

### RQ4 — Policy nào tốt nhất?

So sánh:

- Rule-based.
- Score-based.
- LLM-based.
- Learned policy.
- Reinforcement Learning (nếu đủ thời gian).

### RQ5 — Có đạt trade-off Quality / Latency / Cost tốt hơn baseline không?

Đây là câu hỏi quan trọng nhất về mặt nghiên cứu.

---

# 4. Hypotheses

## H1

Không phải mọi speech segment đều cần visual context.

Một adaptive policy có thể giảm số lần gọi Vision/OCR/frame mà vẫn giữ hoặc cải thiện translation quality.

## H2

Policy dựa trên uncertainty hoặc expected benefit có thể đạt quality/latency/cost trade-off tốt hơn:

- Audio-only.
- Always-multimodal.
- Fixed frame sampling.
- Existing selective frame selection.

---

# 5. Architecture đề xuất

```text
                    Web Video / Livestream
                              │
                              ▼
                       Audio Capture
                              │
                              ▼
                             ASR
                              │
                              ▼
                  Transcript + Context
                              │
                              ▼
                 Adaptive Policy / Controller
                              │
          ┌───────────────────┼────────────────────┐
          │                   │                    │
          ▼                   ▼                    ▼
   Translate Now          Get Frame            Get More
                                                Context
                              │
                         ┌────┴────┐
                         ▼         ▼
                        OCR      Vision
                         │         │
                         └────┬────┘
                              ▼
                      Multimodal Evidence
                              │
                              ▼
                         Translation
                              │
                              ▼
                 Length / Timestamp Control
                              │
                              ▼
                             TTS
                              │
                              ▼
                       Audio Mixing
                              │
                              ▼
                       Browser Output
```

---

# 6. Điểm mới cần tập trung

Cần phân biệt rõ proposal này với các nghiên cứu về **adaptive frame selection**.

## Existing frame selection

Câu hỏi thường là:

> “Frame nào quan trọng nhất?”

Ví dụ:

```text
Video
 ↓
Frame 1
Frame 2
Frame 3
...
 ↓
Select important frames
```

## Proposal

Câu hỏi là:

> **“Có cần lấy thêm evidence hay không, và nếu cần thì nên lấy loại evidence nào, dựa trên lợi ích kỳ vọng và budget?”**

Ví dụ:

```text
Speech segment
      ↓
Estimate uncertainty
      ↓
Estimate value of evidence
      ↓
Compare against cost
      ↓
┌─────────────────────┐
│ Translate now       │
│ Get frame           │
│ Run OCR             │
│ Run vision          │
│ Get more context    │
└─────────────────────┘
```

Đây là hướng cần kiểm chứng thêm bằng systematic literature review, không nên mặc định tuyên bố là hoàn toàn mới.

---

# 7. Value of Information

Một hướng quan trọng có thể sử dụng:

> **Expected Information Gain / Value of Information**

Ý tưởng:

Nếu lấy một frame tốn 100 ms nhưng khả năng cao giúp giải quyết ambiguity → nên lấy.

Nếu frame gần như không có thông tin mới → không lấy.

Có thể định nghĩa một objective đơn giản:

```text
Utility(action)
=
Expected Translation Gain
-
Latency Cost
-
Compute/API Cost
```

Hoặc:

```text
Score =
α × Expected Quality Improvement
-
β × Latency
-
γ × Cost
```

Policy chọn action có utility cao nhất.

---

# 8. Các test case quan trọng

## Case 1 — Audio sufficient

```text
Speaker:
"Today we will discuss machine learning."
```

Không cần visual.

Expected:

```text
TRANSLATE_NOW
```

---

## Case 2 — Visual reference

```text
Speaker:
"As you can see here..."
```

Hệ thống nên lấy frame.

```text
GET_FRAME
```

---

## Case 3 — Chart

```text
Speaker:
"Revenue increased by 40 percent..."
```

Nếu con số nằm trên slide:

```text
GET_FRAME
→ OCR / Vision
```

---

## Case 4 — Small text

Video hiển thị một đoạn text nhỏ.

```text
GET_FRAME
→ OCR
```

---

## Case 5 — Demonstration

Người nói đang hướng dẫn cách sử dụng một phần mềm.

Audio-only có thể không đủ.

```text
GET_FRAME
→ Vision
```

---

## Case 6 — Ambiguous phrase

Một câu có nhiều cách dịch.

```text
Translation uncertainty ↑
        ↓
Acquire visual evidence
        ↓
Better translation
```

---

## Case 7 — No useful visual information

Camera chỉ quay mặt người nói và background không thay đổi.

Policy nên:

```text
SKIP VISUAL
```

---

## Case 8 — Fast livestream

Latency trở thành constraint chính.

Policy phải ưu tiên:

```text
Quality
   ↓
Latency constraint
   ↓
Cost constraint
```

Không thể chờ Vision quá lâu để dịch một câu đã sắp kết thúc.

---

# 9. Dataset / Benchmark

Có thể xây dựng benchmark riêng.

## Giai đoạn đầu

Khoảng:

```text
200–500 video clips
```

Mỗi clip có:

- Audio.
- Transcript.
- Source sentence.
- Reference translation.
- Timestamp.
- Frame candidates.
- OCR text nếu có.
- Annotation về visual necessity.

## Annotation

Mỗi segment có thể gắn:

```text
visual_required = true / false
visual_type =
    none
    text
    chart
    object
    gesture
    scene
    speaker
    context
```

Có thể thêm:

```text
ambiguity_level = 0–3
visual_value = 0–3
```

---

# 10. Baseline Matrix

| Baseline | Visual | Adaptive | Latency | Cost |
|---|---:|---:|---:|---:|
| Audio-only | ❌ | ❌ | Low | Low |
| Always Multimodal | ✅ | ❌ | High | High |
| Fixed Frame Sampling | ✅ | ❌ | Medium | Medium |
| Existing Selective Frame | ✅ | Partially | Medium | Medium |
| Proposed Policy | Adaptive | ✅ | Target | Target |

Baseline cuối cùng phải được điều chỉnh sau literature review để đảm bảo so sánh công bằng với prior work.

---

# 11. Metrics

## Translation Quality

Có thể sử dụng:

- COMET.
- BLEU.
- chrF.

COMET có thể là metric chính, BLEU/chrF dùng bổ sung.

## Latency

Đo:

```text
ASR latency
Translation latency
Vision/OCR latency
TTS latency
End-to-end latency
```

## Real-time Factor

Đánh giá hệ thống có thực sự chạy nhanh hơn tốc độ video hay không.

## Resource / Cost

Đo:

```text
Number of frames accessed
Number of OCR calls
Number of Vision calls
Number of tokens
Audio duration processed
GPU time
API cost
```

## Adaptive efficiency

Một metric đáng nghiên cứu:

```text
Visual Evidence Value
=
Quality(with evidence)
-
Quality(without evidence)
```

Sau đó so sánh với:

```text
Evidence acquisition cost
```

Mục tiêu là tìm được evidence có **high value / low cost**.

---

# 12. Dubbing

Dubbing là phần product rất hấp dẫn nhưng **không nên là novelty chính**.

Pipeline:

```text
ASR
 ↓
Translation
 ↓
Length-aware Translation
 ↓
TTS
 ↓
Timing Alignment
 ↓
Audio Mixing
```

## Vấn đề

Bản dịch có thể dài hơn hoặc ngắn hơn câu gốc.

Ví dụ:

```text
Original: 3.2 sec
Translation: 4.8 sec
```

Nếu đọc nguyên văn:

```text
TTS overlaps next sentence
```

Cần:

- Timestamp-aware TTS.
- Length-aware translation.
- Speech rate adjustment.
- Mild time stretching.
- Segment scheduling.

---

# 13. Audio Mixing

Nếu phát TTS trực tiếp trên video:

```text
Original Audio
        +
Translated Voice
        ↓
     Overlap
```

Không tốt.

## Level 1 — Audio ducking

Giảm âm lượng audio gốc khi TTS phát.

```text
Original ────────╲____╱────────
TTS              ────────
```

Dễ triển khai.

## Level 2 — Speech separation

Tách:

```text
Original Audio
 ├── Speech
 ├── Music
 └── SFX
```

Sau đó:

```text
Remove/reduce Speech
+
Keep Music/SFX
+
Translated Voice
```

Chất lượng tốt hơn nhưng phức tạp hơn.

## Level 3 — Voice cloning / voice preservation

Có thể nghiên cứu sau.

Không nên đưa vào core thesis ban đầu.

---

# 14. Browser Extension

Product layer có thể là Chrome Extension.

Architecture:

```text
Browser Tab
     │
     ▼
Audio Capture
     │
     ▼
ASR
     │
     ▼
Adaptive Translation Engine
     │
 ┌───┴──────────┐
 │              │
Subtitle       TTS
 │              │
 └──────┬───────┘
        ▼
Browser Output
```

Có thể hỗ trợ:

- Live subtitles.
- Original + translated subtitle.
- Live translation.
- Optional dubbing.
- Translation history.

## Nhưng

Không nên bắt đầu thesis từ browser extension.

Nên:

```text
Research algorithm
       ↓
Offline benchmark
       ↓
Prototype
       ↓
Browser integration
```

Lý do:

Browser có nhiều vấn đề engineering:

- DRM.
- Cross-origin.
- Codec.
- MSE.
- Audio capture.
- Permission.
- Website-specific behavior.

---

# 15. Prior Research cần kiểm tra

Đây là phần rất quan trọng.

Các hướng đã có nghiên cứu mạnh:

### Visual Context for Simultaneous Translation

Đã có nghiên cứu cho thấy visual context có thể cải thiện simultaneous translation.

=> Không thể claim:

> "Using visual information for translation is novel."

### Adaptive Frame Selection

Đã có nhiều nghiên cứu về:

- Adaptive keyframe sampling.
- Query-aware frame selection.
- Flexible frame selection.
- RL-based frame selection.
- Visual token compression.

=> Không nên chọn:

> "Adaptive frame selection for video translation"

làm novelty duy nhất.

### Real-time Speech Translation

Đã có nhiều nghiên cứu về:

- Wait-k.
- Adaptive policies.
- Streaming multimodal models.
- Context management.
- Simultaneous interpretation.

=> Không thể claim:

> "Adaptive real-time translation is novel."

### Video Dubbing

Đã có:

- STT.
- MT.
- TTS.
- Voice cloning.
- Lip sync.
- Length-aware dubbing.

=> Không nên claim:

> "AI video dubbing is novel."

---

# 16. Research Gap tiềm năng

Hướng đáng kiểm chứng:

> **Adaptive Multimodal Evidence Acquisition for Real-Time Translation under Latency and Cost Constraints**

Tức là:

```text
Translation
     +
Multimodal evidence
     +
Adaptive decision making
     +
Real-time constraints
     +
Cost awareness
```

Điểm cần chứng minh bằng literature review:

> Existing works có thể giải quyết từng phần riêng lẻ, nhưng liệu đã có một framework/policy thống nhất quyết định **khi nào cần acquire thêm evidence và evidence nào đáng lấy** cho real-time video translation dưới budget hay chưa?

Nếu systematic review cho thấy đã có work gần như giống hệt → phải pivot.

Nếu chưa có → đây có thể là research gap tốt.

---

# 17. Research Methodology

## Phase 1 — Literature Review

Tìm khoảng:

```text
20–30 papers
```

Nhóm:

1. Speech Translation.
2. Simultaneous Translation.
3. Visual Context Translation.
4. Video Understanding.
5. Adaptive Frame Selection.
6. Active Perception.
7. Multimodal Agents.
8. Real-time Translation.
9. Video Dubbing.
10. Audio Separation.

Mỗi paper ghi:

```text
Problem
Method
Dataset
Metrics
Strength
Limitation
Overlap
Potential gap
```

---

# 18. Phase 2 — Benchmark

Xây dựng dataset nhỏ:

```text
200–500 segments
```

Phân loại:

```text
Audio sufficient
Visual useful
Visual necessary
OCR necessary
Vision necessary
Context necessary
```

---

# 19. Phase 3 — Baseline

Implement:

### Baseline A

Audio-only.

### Baseline B

Always multimodal.

### Baseline C

Fixed frame sampling.

### Baseline D

Existing selective frame method.

### Baseline E

Rule-based adaptive policy.

---

# 20. Phase 4 — Proposed Method

Bắt đầu đơn giản.

Ví dụ:

```text
Input:
ASR confidence
Translation confidence
Context
Keywords
Previous evidence
Latency budget
Cost budget
```

Tính:

```text
Evidence Value Score
```

Sau đó:

```text
if score < threshold:
    TRANSLATE_NOW

elif OCR likely useful:
    RUN_OCR

elif visual context likely useful:
    GET_FRAME + VISION

else:
    GET_MORE_CONTEXT
```

Sau khi baseline hoạt động mới cân nhắc:

- LLM policy.
- Learned policy.
- RL policy.

---

# 21. Phase 5 — Dubbing Prototype

Sau khi translation pipeline ổn:

```text
Translation
 ↓
Length-aware TTS
 ↓
Timing Alignment
 ↓
Audio Mixing
```

Mục tiêu ban đầu:

> Dubbing có thể chạy gần real-time và không bị overlap nghiêm trọng.

Lip-sync realtime để **future work**.

---

# 22. Phase 6 — Browser Prototype

Cuối cùng mới xây:

```text
Chrome Extension
```

Có:

- Capture tab.
- Subtitle overlay.
- Translation.
- Optional dubbing.
- Latency monitoring.

---

# 23. Roadmap dự kiến

## Tháng 1

Literature review.

Output:

```text
20–30 papers
Research Gap Matrix
Problem Definition
```

## Tháng 2

Dataset + benchmark.

Output:

```text
200–500 clips
Annotation
Evaluation pipeline
```

## Tháng 3

Baseline.

Output:

```text
Audio-only
Always-multimodal
Fixed sampling
Selective sampling
```

## Tháng 4–5

Adaptive policy.

Output:

```text
Rule-based policy
Evidence scoring
Budget-aware controller
```

## Tháng 6

Advanced policy.

Nếu cần:

```text
LLM policy
Learning
RL
```

## Tháng 7

Dubbing.

## Tháng 8

Browser prototype.

## Tháng 9–10

Experiments.

## Tháng 11–12

Paper + thesis.

---

# 24. Rủi ro

## Risk 1 — Research gap không đủ mới

Đây là rủi ro lớn nhất.

Solution:

> Literature review trước khi commit topic.

---

## Risk 2 — Scope quá lớn

Không làm tất cả cùng lúc.

Priority:

```text
1. Adaptive evidence acquisition
2. Translation
3. Evaluation
4. Dubbing
5. Browser extension
```

---

## Risk 3 — Vision model quá chậm

Có thể làm policy theo tầng:

```text
Cheap check
    ↓
OCR
    ↓
Vision
```

Chỉ gọi model nặng khi cần.

---

## Risk 4 — Browser integration khó

Không bắt đầu từ browser.

Research trước → prototype sau.

---

## Risk 5 — Dubbing chất lượng thấp

Dubbing không phải research core.

Nếu không đủ thời gian:

> Chỉ demo subtitle + TTS.

---

# 25. Tiêu chí thành công

Dự án được coi là thành công nếu chứng minh được:

### Research

Adaptive policy:

- Giảm visual/OCR/Vision calls.
- Không làm translation quality giảm đáng kể.
- Hoặc cải thiện quality trong cùng budget.
- Giảm latency/cost so với always-multimodal.

### System

Có prototype:

```text
Video
 ↓
ASR
 ↓
Adaptive Evidence
 ↓
Translation
 ↓
Subtitle
```

### Product

Có thể mở rộng thành:

```text
Chrome Extension
+
Live Translation
+
Dubbing
```

---

# 26. Core Contribution dự kiến

Nếu kết quả nghiên cứu thuận lợi, contribution có thể là:

### Contribution 1

Một **adaptive multimodal evidence acquisition policy** cho real-time translation.

### Contribution 2

Một framework đánh giá:

```text
Quality
vs
Latency
vs
Cost
```

### Contribution 3

Một benchmark cho các tình huống visual evidence trong video translation.

### Contribution 4

Prototype real-time translation/dubbing.

---

# 27. Tư duy quan trọng nhất

Không nên bắt đầu với:

> "Tôi muốn làm một app dịch video."

Mà nên bắt đầu với:

> **"Tôi muốn nghiên cứu cách hệ thống quyết định lượng thông tin cần quan sát để dịch tốt nhất trong điều kiện real-time."**

Sau đó app chỉ là:

```text
Research
   ↓
Algorithm
   ↓
System
   ↓
Product
```

Đây là cách biến một product idea thành một đề tài nghiên cứu có chiều sâu hơn.

---

# 28. Next Action

Việc tiếp theo nên làm là xây dựng:

## Research Landscape / Research Gap Matrix 2024–2026

Khoảng 20–30 paper/product, chia thành:

1. Speech Translation
2. Visual Context Translation
3. Video Understanding
4. Adaptive Frame Selection
5. Active Perception / Multimodal Agents
6. Real-time Translation
7. Dubbing
8. Audio Separation

Mỗi entry:

```text
Paper / Product
Year
Problem
Method
Dataset
Metrics
Strength
Limitation
Overlap with our idea
Novelty:
🔴 Already done
🟡 Partially explored
🟢 Potential gap
```

**Không được cố ép kết luận rằng đề tài mới.**

Nếu research landscape cho thấy ý tưởng đã được làm gần như đầy đủ, cần pivot sang một research question khác trước khi bắt đầu implementation.

---

# 29. Working Title

> **Adaptive Multimodal Evidence Acquisition for Real-Time Video Translation under Latency and Cost Constraints**

Tên này chỉ là working title và sẽ được chốt lại sau literature review.
