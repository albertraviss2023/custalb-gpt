# Repository Guide

Version: 1.0
Date: April 6, 2026

This document is the single-entry orientation for this repository.

## 1. What This Project Is

`Personal GOI` is a local-first personal GPT platform that runs Gemma 4 models on your own machine (Zenbiok Pro Duo, 32GB RAM, RTX 3070 Ti 8GB), with:

- Multi-model selector in the UI
- Local inference serving via Ollama
- FastAPI orchestration API (OpenAI-compatible)
- React chat interface
- Docker + Kubernetes deployment paths
- CI/CD automation

## 2. Core Runtime Architecture

Request flow:

1. User sends prompt from the React UI.
2. UI calls `POST /v1/chat/completions` on FastAPI.
3. FastAPI `ChatService` resolves selected model profile.
4. Service calls Ollama `/api/chat` for token generation.
5. Tokens stream back to UI via SSE.
6. Chat + messages persist in SQLite.

Key behavior:

- Per-chat model selection
- Per-request model override
- OOM/timeout fallback chain
- Streaming and non-streaming responses

## 3. Model Serving and Switching

Model profiles are defined in:

- `config/model_profiles.yaml`

Current selector profiles:

- `gemma4_e4b_16bit`
- `gemma4_e4b_8bit` (default)
- `gemma4_26b_a4b_4bit`

Switching is exposed via:

- `GET /v1/models`
- `GET /v1/model-selection`
- `POST /v1/model-selection`

## 4. Directory Map

- `backend/`: FastAPI inference gateway and persistence
- `frontend/`: React + Vite UI
- `config/`: model registry and runtime policy
- `infra/docker/`: production Dockerfiles
- `infra/docker-compose.yml`: full local stack orchestration
- `infra/k8s/`: Kubernetes manifests and model-loader job
- `.github/workflows/`: CI and CD workflows
- `scripts/`: local automation scripts
- `docs/`: product, architecture, API, and operations documentation

## 5. Important Existing Docs

- `docs/user_requirements_specification.md`
- `docs/development_plan.md`
- `docs/tool_stack.md`
- `docs/model_selection.md`
- `docs/model_selector_pipeline.md`
- `docs/api_reference.md`
- `docs/setup_and_deployment_guide.md`

## 6. Operational Summary

- Inference engine: `Ollama`
- API gateway: `FastAPI`
- Persistence: `SQLite`
- Frontend: `React + Vite`
- Local deployment: `Docker Compose`
- Cluster deployment: `Kubernetes (kustomize)`
- Automation: `GitHub Actions CI/CD`