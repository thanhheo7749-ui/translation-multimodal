# Live Subtitles Local-First Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the complete local-first live audio translation pipeline specified in `docs/SPEC_LIVE_SUBTITLES_LOCAL_FIRST.md`, fix all JS/Python regression tests, clean up PiP lifecycle/markup, decouple model routing, and organize the GitHub branch.

**Architecture:** 
1. **Model Routing & Contract:** Split `/api/translation-status` into distinct fields (`local_model`, `gemini_model`, `gemini_configured`). Introduce dedicated `POST /api/live/translate` with explicit operations (`translate_local`, `translate_gemini`, `refine_gemini`). Disable silent distillation logging unless explicitly configured.
2. **Deterministic PiP & Session Pairs:** Standardize PiP DOM (`#en`, `#vi`, `#stop`, `#pip-share`, `#draft-bar`) so both automated test fixtures and users have a clean, non-flickering UI. Retain session/segment IDs to prevent rollback or mismatched pairs.
3. **Unified Speech Segmentation & Bounded Queues:** Reconcile `phraseReady`, `findSentenceBoundary`, and `RollingAudio` in `live-core.js`. Enforce max MT concurrency of 2 via `state.mtQueue`.
4. **Git Branch Cleanup:** Delete stale import branch `import/translation-project-20261009-094312-bff631e4` from GitHub, create/maintain clean branch `feature/live-subtitles-local-first` on GitHub, and update `scripts/publish_project.ps1` with clean branch arguments.

**Tech Stack:** JavaScript (ES6, AudioWorklet, Document PiP), Python 3.11, Faster-Whisper, HuggingFace NLLB-200, Google Gemini API, Docker, Playwright.

**Spec:** `docs/SPEC_LIVE_SUBTITLES_LOCAL_FIRST.md`

## Global Constraints
- Never return English as pseudo-translation when translation fails or key is missing.
- Every segment has monotonic `session_id` and `segment_id`.
- Local NLLB never claims to support previous context.
- Gemini correction never delays local translation in hybrid mode.
- `getDisplayMedia()` must be triggered directly by user gesture in main tab; PiP is view & stop only.
- Never leak API keys to browser, logs, or git commits.
- Concurrency bounded: maximum 1 ASR and 2 MT requests at any time.

---

### Task 1: GitHub Branch Renaming & Publish Script Cleanup

**Files:**
- Modify: `scripts/publish_project.ps1`
- Remote: `https://github.com/thanhheo7749-ui/translation-multimodal.git`

- [ ] **Step 1: Check remote branch status and verify clean delete dry-run**
- [ ] **Step 2: Delete stale branch `import/translation-project-20261009-094312-bff631e4` from GitHub**
- [ ] **Step 3: Create and push clean branch `feature/live-subtitles-local-first` to GitHub**
- [ ] **Step 4: Update `scripts/publish_project.ps1` to accept `-Branch` parameter defaulting to current or feature branch instead of random timestamp GUIDs**

---

### Task 2: Phase 0 — Model Routing, API Status & Validation

**Files:**
- Modify: `backend/translation/live_service.py`
- Modify: `backend/server.py`
- Modify: `backend/translation/contracts.py`
- Test: `tests/test_live_translation_service.py`

- [ ] **Step 1: Update `LiveTranslationService.info()` to separate `local_model`, `gemini_model`, `gemini_configured`**
- [ ] **Step 2: Disallow local model parameter in Gemini requests and vice versa**
- [ ] **Step 3: Support `POST /api/live/translate` endpoint in `backend/server.py` alongside backward-compatible `/api/translate-test`**
- [ ] **Step 4: Restrict distillation logging behind `ENABLE_DISTILLATION_LOG=1`**
- [ ] **Step 5: Run `tests/test_live_translation_service.py` and verify all 22 tests pass**

---

### Task 3: Phase 1 & Phase 3 — Segmentation, RollingAudio & PiP Markup

**Files:**
- Modify: `frontend/live-core.js`
- Modify: `frontend/live.html`
- Modify: `frontend/floating.css`
- Test: `tests/test_floating_subtitles_js.cjs`
- Test: `tests/test_live_audio_js.cjs`

- [ ] **Step 1: Fix `phraseReady()` in `live-core.js` (no immediate 4-word cut, wait for terminal punctuation or age >= 2000ms)**
- [ ] **Step 2: Fix `RollingAudio` constructor default `hopSec: 2.5` to match causal tests and spec**
- [ ] **Step 3: Ensure PiP window creates standard elements (`#en`, `#vi`, `#stop`, `#pip-share`, `#draft-bar`) with 25px font size for `#vi`**
- [ ] **Step 4: Run `node tests/test_floating_subtitles_js.cjs` and `node tests/test_live_audio_js.cjs` and verify they pass**

---

### Task 4: Phase 2 & Phase 4 — Bounded MT Queue, Session Pairing & 3 Clean Modes

**Files:**
- Modify: `frontend/live.js`
- Modify: `frontend/live.html`
- Test: `tests/test_live_pipeline_js.cjs`
- Test: `tests/test_live_audio.py`

- [ ] **Step 1: Enforce bounded MT concurrency (max 2) with `state.mtQueue` and accurate `state.translating` counter**
- [ ] **Step 2: Implement the 3 official spec modes in UI dropdown: `local` (Local NLLB), `hybrid` (Local first + async Gemini refinement), `gemini` (Gemini direct)**
- [ ] **Step 3: Ensure segment pairing matches `session_id` and `segment_id`, preventing rollback or out-of-order replacement**
- [ ] **Step 4: Fix track/AudioContext cleanup on stop/close in `live.js`**
- [ ] **Step 5: Run `node tests/test_live_pipeline_js.cjs` and `docker exec ... python -m unittest tests/test_live_audio.py` and verify they pass**

---

### Task 5: Phase 5 — Full Verification & Docker Smoke Test

**Files:**
- Modify: `README.md`
- Test: All tests in `tests/`

- [ ] **Step 1: Run all JS unit tests (`test_live_audio_js.cjs`, `test_live_pipeline_js.cjs`, `test_floating_subtitles_js.cjs`)**
- [ ] **Step 2: Run all Python unit tests in Docker container**
- [ ] **Step 3: Test live audio playback / video streaming on container `http://localhost:8004/live`**
- [ ] **Step 4: Update `README.md` with accurate mode descriptions and instructions**
- [ ] **Step 5: Publish latest verified code to GitHub branch**
