# Adaptive Controller & Translation Subsystems Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and verify the core `backend/translation/` and `backend/controller/` subsystems to replace the mock Google Translate scraper with a scientific, contextual multimodal translation pipeline.

**Architecture:** Pluggable Factory Pattern for Translation Engine (supporting Gemini API, Local Qwen2.5, and Mock provider) combined with an asynchronous Adaptive Policy Controller executing rule-based grounding, entity indexing, and sliding window revision.

**Tech Stack:** Python 3.11, Asyncio, Dataclasses, HTTPX (REST API), PyTest / Unittest.

**Spec:** [docs/superpowers/specs/2026-10-04-translation-and-controller-design.md](file:///C:/TepD/HUTECH/NCKH/translation_modal/docs/superpowers/specs/2026-10-04-translation-and-controller-design.md)

## Global Constraints
- Target Hardware: RTX 3050 Laptop (6GB VRAM, CUDA 12.x/13.x).
- Maximum Controller logic latency budget: $\le 10\text{ms}$ on CPU.
- Maximum Translation latency budget: $\le 350\text{ms}$ for live streaming.
- Disfluency deduplication must execute before translation.
- Preserve technical entities (e.g., OPENSHELL, DeepSeek, Qwen) in Vietnamese output.

---

### Task 1: Data Contracts and Translation Models

**Files:**
- Create: `backend/translation/contracts.py`
- Create: `backend/translation/prompt_builder.py`
- Test: `tests/test_translation_contracts.py`

**Interfaces:**
- Produces: `TranslationRequest`, `TranslationResponse`, `PromptBuilder.build_fusion_prompt()`

- [x] **Step 1: Write the failing test for contracts and prompt builder**
Create `tests/test_translation_contracts.py` testing dataclass creation and prompt construction with/without visual entities.

- [x] **Step 2: Run test to confirm it fails**
Run `.\.venv\Scripts\python.exe -m unittest tests/test_translation_contracts.py`.

- [x] **Step 3: Implement `backend/translation/contracts.py` and `prompt_builder.py`**
Implement the dataclasses and the prompt builder function.

- [x] **Step 4: Run test to confirm it passes**
Run `.\.venv\Scripts\python.exe -m unittest tests/test_translation_contracts.py`.

---

### Task 2: Translation Providers and Factory

**Files:**
- Create: `backend/translation/base.py`
- Create: `backend/translation/mock_provider.py`
- Create: `backend/translation/gemini_provider.py`
- Create: `backend/translation/factory.py`
- Create: `backend/translation/__init__.py`
- Test: `tests/test_translation_providers.py`

**Interfaces:**
- Consumes: `TranslationRequest`, `TranslationResponse`, `PromptBuilder` from Task 1.
- Produces: `get_translator(provider_type: str) -> BaseTranslator`

- [x] **Step 1: Write the failing test for translation providers**
Create `tests/test_translation_providers.py` testing mock translation, fallback behavior, and factory instantiation.

- [x] **Step 2: Run test to confirm failure**
Run `.\.venv\Scripts\python.exe -m unittest tests/test_translation_providers.py`.

- [x] **Step 3: Implement base, mock, gemini provider, and factory**
Implement `BaseTranslator`, `MockTranslator`, `GeminiTranslator` (using `httpx`), and `get_translator()`.

- [x] **Step 4: Run test to confirm passing**
Run `.\.venv\Scripts\python.exe -m unittest tests/test_translation_providers.py`.

---

### Task 3: Adaptive Policy Controller State & Decision Engine

**Files:**
- Create: `backend/controller/state.py`
- Create: `backend/controller/policy.py`
- Create: `backend/controller/__init__.py`
- Test: `tests/test_adaptive_controller.py`

**Interfaces:**
- Consumes: `ASRSegment`, `TranslationRequest` from `backend/translation/contracts.py`.
- Produces: `AdaptiveController.process_segment(segment: ASRSegment) -> tuple[TranslationRequest, ControllerMetadata]`

- [x] **Step 1: Write the failing test for Adaptive Controller**
Create `tests/test_adaptive_controller.py` testing:
1. Speech disfluency deduplication (`many of you many of you` -> `many of you`).
2. Deictic trigger detection (`this`, `that`, `table`, `slide`).
3. Slide entity keyword matching with in-memory cache.
4. Dangling connector / pronoun detection triggering `REVISE_PREVIOUS`.

- [x] **Step 2: Run test to confirm failure**
Run `.\.venv\Scripts\python.exe -m unittest tests/test_adaptive_controller.py`.

- [x] **Step 3: Implement `backend/controller/state.py` and `backend/controller/policy.py`**
Implement the sliding window history, RAM visual memory cache, and adaptive decision rules.

- [x] **Step 4: Run test to confirm passing**
Run `.\.venv\Scripts\python.exe -m unittest tests/test_adaptive_controller.py`.

---

### Task 4: End-to-End Pipeline Integration & Benchmark Verification

**Files:**
- Create: `experiments/exp006_integrated_translation_pipeline.py`
- Test: `tests/test_e2e_pipeline.py`

**Interfaces:**
- Integrates: `AdaptiveController` + `TranslationEngine` on real keynote segments from EXP-002 and slide entities from EXP-004.

- [x] **Step 1: Write test for end-to-end integration**
Create `tests/test_e2e_pipeline.py` that processes the 5 keynote sentences and verifies:
- Provisional draft translation for early segments.
- Contextual revision for Sentence 3 & 4.
- Visual grounding preservation for Sentence 6 (`OPENSHELL`).
- End-to-end controller latency $< 5\text{ms}$.

- [x] **Step 2: Run test to confirm execution and pass**
Run `.\.venv\Scripts\python.exe -m unittest tests/test_e2e_pipeline.py`.

- [x] **Step 3: Implement runnable experiment script `experiments/exp006_integrated_translation_pipeline.py`**
Create a standalone CLI runner that can run with either `--provider mock` or `--provider gemini` and exports structured benchmark results to `experiments/results_exp006.json`.

- [x] **Step 4: Execute EXP-006 and log results to `research/03_experiment_log.md`**
Run `exp006_integrated_translation_pipeline.py` and record the latency and accuracy metrics into `research/03_experiment_log.md`.
