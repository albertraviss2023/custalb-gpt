# Personal GOI (Gemma 4 Local Assistant)

Production-oriented local-first assistant stack with:

- Gemma 4 multi-model runtime switching (`E4B 16-bit`, `E4B 8-bit`, `26B A4B 4-bit`)
- OpenAI-compatible backend API with streaming chat
- Modern chat UI with per-chat model selector
- Docker Compose for local deployment
- Kubernetes manifests and CI/CD workflows

## Hardware Target


- Zenbiok Pro Duo
- 32 GB RAM
- NVIDIA RTX 3070 Ti (8 GB VRAM)his feature here for the competency based interview coach add on, reviw and implement it: 

## Project Structure

- `backend/` FastAPI orchestration and inference gateway
- `frontend/` React + Vite chat client
- `config/model_profiles.yaml` model registry and fallback policy
- `infra/docker/` Dockerfiles and nginx config
- `infra/docker-compose.yml` local full-stack orchestration
- `infra/k8s/` Kubernetes manifests
- `.github/workflows/` CI/CD automation
- `docs/` requirements, architecture, API, and deployment docs

## Quick Start

```bash
docker compose -f infra/docker-compose.yml up --build -d
```

Model bootstrap:

```powershell
# Required for gated Hugging Face models (Gemma):
$env:HF_TOKEN="hf_xxx"
./scripts/bootstrap-models.ps1
# Or a single model only:
./scripts/bootstrap-models.ps1 -Model "google/gemma-4-E4B-it"
```

Endpoints:

- UI: `http://localhost:3000`
- API: `http://localhost:8000`
- Health: `http://localhost:8000/health`

## Model Profiles

Configured in `config/model_profiles.yaml`:

- `gemma4_e4b_16bit`
- `gemma4_e4b_8bit` (default)
- `gemma4_26b_a4b_4bit` (deep/slow mode)

UI model selector supports per-chat model switching without restarting services.

## CI/CD

- `CI`: lint, tests, frontend build, and container build validation.
- `CD`: optional GHCR image publishing and Kubernetes deploy automation.

## Core Docs

- `docs/README.md`
- `docs/repository_guide.md`
- `docs/implementation_stages_log.md`
- `docs/how_to_guide.md`
- `docs/user_requirements_specification.md`
- `docs/development_plan.md`
- `docs/architecture_overview.md`
- `docs/model_selector_pipeline.md`
- `docs/api_reference.md`
- `docs/setup_and_deployment_guide.md`
- `docs/testing_cicd_scaling.md`
- `docs/evaluation_and_finetuning.md`
