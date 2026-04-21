# How-To Guide

Version: 1.0
Date: April 6, 2026

This is the practical runbook for developing, running, and operating the tool.

## 1. Local Full-Stack Startup (Recommended)

```bash
docker compose -f infra/docker-compose.yml up --build -d
```

Then preload models:

```powershell
$env:HF_TOKEN="hf_xxx"
./scripts/bootstrap-models.ps1
# Optional single-model pull:
./scripts/bootstrap-models.ps1 -Model "deepseek-ai/DeepSeek-R1-Distill-Qwen-14B"
```

Open:

- UI: `http://localhost:3000`
- API: `http://localhost:8000`

## 2. Model Switching in UI

- Open or create a chat.
- Use top-right model selector.
- Choose one profile:
  - `Gemma 4 E4B 8-bit`
  - `Gemma 4 E4B 16-bit`
  - `Gemma 4 26B A4B 4-bit`
- Next user turn uses selected model.

## 3. Native Backend + Frontend Dev

Backend:

```bash
cd backend
pip install -r requirements.txt
pip install -e .[dev]
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

## 4. API Usage Examples

List models:

```bash
curl http://localhost:8000/v1/models
```

Set default model:

```bash
curl -X POST http://localhost:8000/v1/model-selection \
  -H "Content-Type: application/json" \
  -d '{"model_id":"gemma4_e4b_8bit"}'
```

Non-stream chat completion:

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"gemma4_26b_a4b_4bit","stream":false,"messages":[{"role":"user","content":"Summarize this architecture."}]}'
```

## 5. Docker Operations

Start:

```bash
docker compose -f infra/docker-compose.yml up -d
```

Stop:

```bash
docker compose -f infra/docker-compose.yml down
```

Logs:

```bash
docker compose -f infra/docker-compose.yml logs -f api
```

## 6. Kubernetes Deployment

Apply:

```bash
kubectl apply -k infra/k8s
```

Verify:

```bash
kubectl get pods -n personal-goi
kubectl get svc -n personal-goi
```

## 7. Troubleshooting Quick Checks

- API health: `GET /health`
- vLLM readiness: verify `goi-vllm-gemma` / `goi-vllm-deepseek` containers are healthy
- Missing model: set `HF_TOKEN`, confirm access to gated models, then run bootstrap again
- Slow responses: switch to E4B 8-bit or reduce context size

## 8. Security Mode

To enable API key protection:

- Set `GOI_API_KEY` in backend environment.
- Call API with `Authorization: Bearer <key>`.

To enable chat encryption at rest:

- Set `GOI_CHAT_ENCRYPTION_ENABLED=true`.
- Generate a Fernet key and set `GOI_CHAT_ENCRYPTION_KEY`.
- Example key generation:
  - `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
- Keep the same key for existing encrypted chats; changing it without migration makes old chats undecryptable.
