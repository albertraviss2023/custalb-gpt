# Backend Service

FastAPI orchestration service for local Gemma 4 inference.

## Key Responsibilities

- OpenAI-compatible chat API (`/v1/chat/completions`)
- Model selection and registry APIs (`/v1/models`, `/v1/model-selection`)
- Chat persistence (SQLite)
- Model fallback handling (OOM/timeout)

## Run Locally

```bash
pip install -r requirements.txt
pip install -e .[dev]
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Environment

Copy `.env.example` to `.env` and adjust values.