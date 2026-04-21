# Project State Snapshot - April 10, 2026

## Metadata
- Date: 2026-04-10
- Git HEAD (short): `c3eef3f`
- Workspace: `d:\projects\custom assistant\custalb-gpt`

## Current Product Direction
TurboGPT local assistant with:
- Dual inference stack support (vLLM + Ollama variants in broader repo)
- Chat memory management (context ceiling, auto compaction, inheritance)
- CBI (Competency Based Interview) simulation add-on with panel controls

## Implemented (Current State)
### CBI simulation
- Role/org/session configuration UI
- Panel demographics drawer (show/hide)
- Per-panelist:
  - name
  - role/title
  - nationality
  - gender
  - accent preference
- Difficulty modes: `medium`, `high`
- Session controls: start/pause/end
- Custom session duration (`5-180` minutes)
- Camera support:
  - start/stop
  - auto-start option
  - floating dock
  - drag + resize
  - detach/attach via Picture-in-Picture when supported
- Voice simulation:
  - TTS per panelist with nationality/accent/gender-aware selection
  - mic voice input mode with silence auto-send behavior

### Memory management
- Context ceiling and pressure telemetry in UI
- Automatic context compaction (trigger near 98% pressure)
- Manual selective forget workflow:
  - choose old turns
  - compact into summary (do not fully lose context)

### UX additions
- Left sidebar width is resizable
- Chat history date filters
- Message actions (thumbs, copy, regenerate)
- Inherited chat creation from summary

## Reliability Fixes Added
- `handleSend` now has streaming timeout guard (`45s`) to prevent stuck "Thinking..." state
- Timeout abort unblocks UI (voice controls become usable again)
- Better user error when selected model is unavailable

## Tests / Verification Status
### Frontend
- `npm run test -- --run` passes
  - includes:
    - `App.route.test.tsx`
    - `App.cbi.test.tsx` (CBI workflow checks)
- `npm run build` passes

### Backend
- Container compile smoke passes:
  - `python -m compileall app`
- Note: local/container `pytest` tooling was unavailable in prior runs in this environment image, so full backend unit execution was not consistently runnable from current shell.

## Known Follow-ups
- Expand CBI E2E tests for:
  - camera dock drag/detach interactions
  - voice input path in browser-like test harness
  - timeout/fallback inference path assertions
- Add structured post-interview multimodal scoring pipeline (requested):
  - periodic camera frame snapshots during session
  - sampled audio clips (compressed intervals, not full recording)
  - report on posture/positioning, tone, enthusiasm, authority signals

## Quick Resume Checklist
1. Bring stack up:
   - `docker compose -f infra/docker-compose.yml up -d --build`
2. Open UI and verify CBI mode controls
3. Validate model availability before interview start
4. Run frontend verification:
   - `cd frontend && npm run test -- --run && npm run build`
5. For backend smoke in container:
   - `docker compose -f infra/docker-compose.yml run --rm api sh -lc "python -m compileall app"`

## Important Files (Most Relevant)
- `frontend/src/App.tsx`
- `frontend/src/styles.css`
- `frontend/src/api.ts`
- `frontend/src/types.ts`
- `backend/app/services/chat_service.py`
- `backend/app/api/routes/chats.py`
- `backend/app/models/schemas.py`
