# Tool Stack

Version: 1.1  
Date: April 6, 2026

## 1. Architecture Strategy

Use a layered stack that ships fast for MVP, keeps everything local-first, and can graduate to Kubernetes without rework.

Inference serving decision:

- Use `Ollama` as the primary LLM serving engine for Gemma 4 profile management and quantized runtime compatibility.
- Build a dedicated `FastAPI orchestration server` on top for product APIs, chat persistence, model routing/fallback, auth, and UI integration.
- Result: no need to implement a custom low-level CUDA inference engine; we implement a professional application inference gateway instead.

## 2. Recommended Stack by Layer

| Layer | Primary Choice | Why This Choice | Alternatives |
|---|---|---|---|
| Model Runtime | Ollama (Gemma 4 tags) | Fastest path to local serving, easy model switching, OpenAI-compatible endpoint support | llama.cpp direct, vLLM |
| LLM Model | Gemma 4 E4B 16-bit + E4B 8-bit + 26B A4B 4-bit | Matches required model selector profiles for this MVP | E2B fast mode as optional future profile |
| API Orchestration | FastAPI + Uvicorn | Lightweight Python API layer, tool routing, session logic | Node/Express, Go |
| Frontend UI | React + TypeScript + Vite | Fast, lightweight, and easy to containerize for local-first deployments | Next.js, Open WebUI |
| Persistence | SQLite (metadata) + local files (exports/config) | Local, simple backup, zero external dependency | Postgres (if multi-user later) |
| Retrieval (Iteration 3) | Chroma or FAISS | Local vector retrieval for project context | Qdrant local, LanceDB |
| Deployment (Local) | Docker Compose | One-command startup and reproducible local runs | Native scripts |
| Deployment (Cluster) | Kubernetes + Helm | Clean promotion path from local to cluster | Raw manifests only |
| Observability | Prometheus + Grafana + Loki (Iteration 4) | Useful local ops visibility without SaaS lock-in | OpenTelemetry collector only |
| Testing/Quality | pytest, ruff, mypy, vitest, playwright | End-to-end quality for backend, UI, and chat flows | minimal smoke tests |

## 3. Runtime Profiles

## 3.1 Profile A - E4B 8-bit (default)

- Model: `gemma4:e4b`
- Use case: best daily balance on this hardware
- Tradeoff: slightly lower fidelity than BF16

## 3.2 Profile B - E4B 16-bit

- Model: `google/gemma-4-E4B-it` (BF16 runtime profile)
- Use case: fidelity-sensitive responses
- Tradeoff: heavier memory pressure and more offload

## 3.3 Profile C - 26B A4B 4-bit (deep mode)

- Model: `gemma4:26b` (hybrid RAM+VRAM)
- Use case: harder reasoning/coding prompts where quality matters more than speed
- Tradeoff: significantly higher latency; requires tighter context presets

## 4. Container and Deployment Topology

## 4.1 Docker Compose Services

- `llm-runtime` (Ollama or equivalent)
- `api` (FastAPI orchestration)
- `ui` (React frontend)
- `vector-db` (optional in Iteration 3)

## 4.2 Kubernetes Workloads

- `Deployment`: `llm-runtime`, `api`, `ui`
- `Service`: internal APIs and UI exposure
- `Ingress`: local network access with optional auth
- `PersistentVolumeClaim`: model cache and conversation store

## 4.3 Model Registry and Switching

- `config/model_profiles.yaml` as source of truth for UI-selectable models.
- Backend `ModelManager` component for load/unload, fallback, and health state.
- API endpoints: `GET /v1/models`, `GET/POST /v1/model-selection`.

## 5. Developer Tooling

- Python: `uv`, `pip-tools`, `ruff`, `pytest`
- Frontend: `pnpm`, `eslint`, `prettier`, `vitest`, `playwright`
- CI: GitHub Actions for lint, tests, image build checks
- Security baseline: `trivy` image scan and dependency checks

## 6. Why This Stack Fits Your Goal

- Minimizes cloud API spend by keeping inference local.
- Ships quickly in Iteration 1 without locking architecture.
- Leaves a clean path for Phase 2 fine-tuning and coding-tool specialization.
- Supports both Docker-only and Kubernetes deployment targets.
