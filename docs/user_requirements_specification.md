# User Requirements Specification

Version: 1.1  
Date: April 6, 2026  
Project: Personal GOI (Gemma 4 Local Assistant)

## 1. Vision

Build a private, local-first personal assistant that feels like a commercial GPT product, runs on a Zenbiok Pro Duo laptop, works offline by default, and can be deployed with Docker or Kubernetes.

## 2. Goals and Non-Goals

## 2.1 Goals

- Deliver a useful local assistant with a polished chat UI (MVP).
- Support offline operation for core chat and project workflows.
- Keep cloud usage optional to reduce recurring API costs.
- Provide a clean path to Docker and Kubernetes deployment.
- Implement production-grade CI/CD and automation from MVP.
- Enable future model adaptation to your own projects (Phase 2).

## 2.2 Non-Goals (Phase 1)

- Full model retraining from scratch.
- Multi-user enterprise RBAC platform.
- Large-scale cloud-only serving.

## 3. Primary User Stories

## 3.1 MVP Stories

- As the primary user, I can open a modern web UI and chat with my assistant naturally.
- As the primary user, I can run the assistant fully locally on my laptop.
- As the primary user, I can launch the full stack with Docker Compose.
- As the primary user, I can keep conversations local and private.

## 3.2 Post-MVP Stories

- As the primary user, I can switch between quality and speed model modes.
- As the primary user, I can load project context from local folders.
- As the primary user, I can deploy the same stack on Kubernetes.

## 3.3 Phase 2 Stories

- As the primary user, I can fine-tune/adapt the base model on my own coding/project datasets.
- As the primary user, I can run a customized coding assistant aligned to my workflow.

## 4. Functional Requirements

## 4.1 Core Assistant

- The system shall provide multi-turn chat with session history.
- The system shall support streaming responses.
- The system shall expose an OpenAI-compatible API for interoperability.
- The system shall support system prompts and reusable prompt templates.
- The system shall support per-chat model selection and per-request model override.

## 4.2 Model Runtime

- The system shall support Gemma 4 local inference.
- The system shall provide selectable profiles for `E4B 16-bit`, `E4B 8-bit`, and `26B A4B 4-bit`.
- The system shall allow model files to be loaded from local storage.
- The system shall support runtime model switching from the UI without restarting services.
- The system shall gracefully fallback on OOM/timeout and report fallback metadata.

## 4.3 UI/UX

- The UI shall provide a responsive chat experience for desktop and laptop.
- The UI shall show clear generation states (thinking, streaming, done, error).
- The UI shall support conversation list, rename, delete, and pin.
- The UI shall support branding and theme customization.
- The UI shall include a model selector that can switch between configured local model profiles.

## 4.4 Offline and Privacy

- Core inference shall work with no internet connection.
- Conversation data shall be stored locally by default.
- Remote telemetry shall be disabled by default.

## 4.5 Deployment

- The system shall include Dockerfiles for backend and frontend.
- The system shall include Docker Compose for single-command local launch.
- The system shall include Kubernetes manifests (or Helm) for cluster deployment.

## 4.6 API and Inference Serving

- The backend shall expose OpenAI-compatible endpoints for model listing and chat completions.
- The backend shall expose model-selection endpoints for global and per-chat selection.
- The backend shall provide streaming and non-streaming chat completion modes.
- The backend shall persist chat threads and message history in local storage.

## 4.7 Security

- Localhost-only mode shall be the default in Phase 1.
- Optional API key protection shall be available for non-localhost access.
- Tool execution capabilities (Phase 1.5+) shall require explicit allowlists.

## 4.8 DevEx, Automation, and CI/CD

- The repository shall use a professional monorepo structure with backend, frontend, infra, and docs separation.
- CI shall run linting, tests, and build validation for backend and frontend on every pull request.
- CI shall validate container builds for API and UI.
- CD workflow shall support automated deployment to a target Kubernetes environment via secrets/config.
- Developer automation shall include makefile/scripts for setup, run, test, and release tasks.

## 5. Non-Functional Requirements

## 5.1 Performance Targets (Laptop Baseline)

- First token target: <= 7 seconds on `E4B 8-bit`, <= 12 seconds on `E4B 16-bit`.
- Sustained generation target: >= 4 tokens/sec on `E4B 8-bit`, >= 2 tokens/sec on `E4B 16-bit`.
- Deep mode target: `26B A4B 4-bit` optimized for quality, not latency; no strict TPS target for MVP.
- UI interaction latency target: <= 150 ms for local actions.

## 5.2 Reliability

- Service startup success rate target: >= 95% across local restarts.
- Graceful degradation when GPU memory is insufficient (automatic fallback path).

## 5.3 Maintainability

- Modular services with clear API contracts.
- Reproducible local environment via Compose.
- Documentation must be sufficient for reinstall from scratch.
- CI/CD definitions must be version-controlled and reproducible.

## 6. Constraints

- Hardware ceiling: single 8 GB VRAM GPU and 32 GB RAM.
- Must prioritize local/offline value before any cloud dependency.
- Phase 2 (fine-tuning) begins only after assistant + UI are useful daily.

## 7. Assumptions

- NVIDIA drivers and CUDA runtime are available on host.
- Model weights can be downloaded once, then reused offline.
- User is the only primary operator in early phases.

## 8. Acceptance Criteria

## 8.1 MVP Acceptance

- User can launch stack with one command (`docker compose up`).
- User can chat from browser and receive streamed responses.
- Inference runs locally with Gemma 4 using selectable profiles (`E4B 16-bit`, `E4B 8-bit`, `26B 4-bit`).
- Conversation history persists locally across restarts.
- User can change active model from the UI selector for new and existing chats.
- CI pipeline passes for lint, tests, and image build checks.
- Kubernetes manifests deploy successfully to a namespace with healthy pods.

## 8.2 Phase 1 Completion Gate

- Assistant is used productively for at least two recurring workflows.
- UI is stable and user-friendly for daily use.
- Docker path is stable; Kubernetes path is validated.

## 8.3 Phase 2 Entry Gate

- Quality baseline and workflow value are documented.
- Training data sources and licensing are confirmed.
- Evaluation harness is in place before any fine-tuning run.
