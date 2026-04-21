# TurboGPT CBI Overhaul Plan (Local TTS, No External APIs)

## Scope
This plan delivers a controlled overhaul across three tracks without breaking existing interview workflows:

1. Setup workflow redesign and field aesthetics.
2. Voice input reliability fixes.
3. Migration from browser speech synthesis to fully local open-source TTS backends.

## Non-Negotiables
- No external TTS API calls.
- Incremental changes only; preserve existing CBI behavior.
- Full test traceability by change set in dedicated folders.
- Push only after validation; open PRs against `dev`.

## Local TTS Decision
- Default provider: **Kokoro** (low latency, better interactive flow).
- Optional provider: **Coqui XTTS v2** (higher realism, heavier runtime).
- Architecture supports both via provider abstraction and runtime switching.

## Implementation Phases

### Phase 1: UX + Audio Input Reliability
Changes:
- Refine start/setup screen layout and hierarchy.
- Improve field styling consistency and spacing.
- Harden microphone preflight checks and actionable error states.
- Keep current CBI timeline/resume flow intact.

Validation:
- Frontend lint/test/build.
- CBI interaction tests (start, pause, resume, rewind, voice button behavior).

Traceability artifact folder:
- `test-results/2026-04-21-cbi-overhaul/phase-01-ux-audio-input/`

### Phase 2: Local TTS Provider Architecture
Changes:
- Add backend `TTSService` abstraction with local providers:
  - `kokoro`
  - `xtts`
- Add `/v1/tts/speak` endpoint returning audio bytes.
- Add provider and endpoint path settings via environment variables.
- Keep fallback behavior explicit and local-only (no browser speech synthesis dependency).

Validation:
- Backend unit tests for provider behavior and route.
- Health/availability checks for local TTS runtime connectivity.

Traceability artifact folder:
- `test-results/2026-04-21-cbi-overhaul/phase-02-local-tts-backend/`

### Phase 3: Frontend Playback Migration
Changes:
- Replace browser `speechSynthesis` playback with backend-driven local TTS playback.
- Synchronize active speaker animation with audio start/end.
- Support interruption (pause/stop/rewind cancels queued audio).
- Preserve Panel Audio toggle behavior.

Validation:
- Frontend tests for playback-trigger logic.
- Manual smoke validation sequence:
  - Start interview -> panel speaks.
  - Pause stops playback.
  - Resume restarts correctly.
  - Rewind clears current audio and replays from checkpoint.

Traceability artifact folder:
- `test-results/2026-04-21-cbi-overhaul/phase-03-frontend-local-tts/`

### Phase 4: CI/CD + Evidence Discipline
Changes:
- Ensure pipeline triggers on `dev` and `main` for push/PR.
- Keep validation gate before merge.
- Save test outputs per phase in folderized artifacts.

Validation:
- `make validate`
- `frontend npm run test`
- `backend pytest -q`

Traceability artifact folder:
- `test-results/2026-04-21-cbi-overhaul/phase-04-cicd-traceability/`

## Acceptance Criteria
1. Setup workflow is visually cleaner and less intrusive.
2. Voice input works reliably with clear diagnostics on failure.
3. Panel speech playback is generated from local TTS endpoint(s), not browser speech synthesis.
4. Pause/resume/rewind remain functional with speaker sync.
5. CI checks pass and results are archived in phase-specific evidence folders.

## Delivery Strategy (PRs)
- PR 1: Phase 1 (UX + audio input reliability) + tests + evidence.
- PR 2: Phases 2/3 (local TTS backend + frontend migration) + tests + evidence.
- PR 3: Phase 4 CI and traceability hardening (if additional adjustments needed).
