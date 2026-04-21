# CBI Overhaul Validation Evidence

Date: 2026-04-21

## Change-set traceability
- `phase-01-ux-audio-input/`
  - Scope: setup workflow polish + mic input reliability.
  - Evidence: `summary.md`, `command.log`
- `phase-02-local-tts-backend/`
  - Scope: local TTS abstraction (`kokoro`/`xtts`) + `/v1/tts/speak`.
  - Evidence: `summary.md`, `command.log`
- `phase-03-frontend-local-tts/`
  - Scope: browser speech replacement with backend local TTS playback.
  - Evidence: `summary.md`, `command.log`
- `phase-04-cicd-traceability/`
  - Scope: full `make validate` gate and consolidated release-readiness check.
  - Evidence: `summary.md`, `command.log`

## Acceptance criteria mapping
1. Setup workflow cleaner and less intrusive:
   - Covered by phase 01.
2. Voice input reliability with diagnostics:
   - Covered by phase 01.
3. Panel speech generated from local TTS endpoint:
   - Covered by phases 02 and 03.
4. Pause/resume/rewind compatibility preserved:
   - Covered by phase 03 behavior checks.
5. CI checks pass with archived results:
   - Covered by phase 04.
