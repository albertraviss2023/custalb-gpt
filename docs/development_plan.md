# Development Plan (4 Iterations)

Version: 1.1  
Date: April 6, 2026

Principle: Iteration 1 is a complete, usable MVP with production-grade engineering foundations (inference serving, API, UI, Docker/K8s, CI/CD). Phase 2 fine-tuning starts only after Phase 1 value is proven.

## Iteration 1 - MVP Build (Now)

Duration target: 2-4 weeks

Objective:

- Deliver a fully working local assistant stack that is deployable, testable, and automation-ready.

Scope:

- Inference serving tool: Ollama runtime for Gemma 4 profiles.
- Backend orchestration API (FastAPI) with OpenAI-compatible chat endpoints.
- Chat and conversation APIs with SQLite persistence.
- UI with model selector (`E4B 16-bit`, `E4B 8-bit`, `26B A4B 4-bit`) and streaming chat.
- Runtime model switching + fallback behavior (OOM/timeout handling).
- Dockerfiles for backend/frontend and Compose for full local stack.
- Kubernetes manifests for runtime, API, and UI.
- CI pipeline for lint/tests/build/container validation.
- CD scaffold for automated deployment to Kubernetes.

Deliverables:

- `backend/` production-oriented API service
- `frontend/` polished MVP UI
- `config/model_profiles.yaml` model registry
- `infra/docker-compose.yml` and `infra/k8s/` manifests
- `.github/workflows/` CI/CD workflows
- `scripts/` automation scripts for run/test/release

Exit criteria:

- `docker compose up` launches full system end-to-end.
- Model selector works without service restarts.
- Chat streaming works and history persists.
- CI is green on lint/tests/build checks.
- Kubernetes deployment artifacts are valid and deployable.

## Iteration 2 - Reliability and UX Hardening

Duration target: 2-3 weeks

Objective:

- Increase operational reliability and user experience quality.

Scope:

- Enhanced retry/fallback controls and richer failure metadata.
- Better session UX (search, export/import, pinned conversations).
- API auth modes, rate limiting, and stricter input validation.
- Observability baseline: metrics, structured logs, basic dashboards.
- Performance tuning for context size and model load/unload behavior.

Deliverables:

- Reliability and security hardening package
- Dashboard and health diagnostics package
- Updated runbook and SRE-style troubleshooting guide

Exit criteria:

- Stable 7-day local usage without critical incidents.
- Security and reliability checks pass in CI.

## Iteration 3 - Coding Workflow Features (Phase 1 Extension)

Duration target: 3-4 weeks

Objective:

- Make assistant materially useful for coding/project workflows.

Scope:

- Local RAG ingestion for docs/repos.
- Project-aware context selection in UI.
- Safe local tool connectors (filesystem read/search, optional command tools).
- Prompt presets for architecture, debugging, and code review.
- Kubernetes deployment maturity (Helm overlays, environment profiles).

Deliverables:

- RAG module and indexing pipeline
- Tooling connector module with permissions
- Enhanced deployment profiles (dev/stage/prod)

Exit criteria:

- Reliable project-grounded responses in real workflows.
- Deployment profiles validated via CI automation.

## Iteration 4 - Phase 2 (Model Adaptation and Production Operations)

Duration target: 4-6 weeks

Objective:

- Add model adaptation and mature operations for long-term usage.

Scope:

- LoRA/QLoRA adaptation pipeline.
- Evaluation harness with quality regression gates.
- Model registry/versioning and rollout/rollback strategy.
- Advanced observability and backup/restore automation.
- Controlled release pipeline for adapted model versions.

Deliverables:

- `finetune/` training and evaluation workflow
- versioned model release process
- operations handbook for rollback and disaster recovery

Exit criteria:

- Adapted model exceeds base on defined task benchmarks.
- Rollback path is tested and documented.
- Local-first behavior remains intact.

## Cross-Iteration Quality Gates

- Offline usability never regresses.
- Docker/Kubernetes paths stay reproducible.
- API contracts remain backward-compatible or versioned.
- CI/CD remains green and enforces quality checks.