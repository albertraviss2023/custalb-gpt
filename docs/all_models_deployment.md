# All Models Deployment Guide

This guide covers deployment and validation for all model profiles defined in `config/model_profiles.yaml`.

## 1. Model Inventory

| Profile ID | Runtime Ref | Tier | Deployment Status in Current Stack |
|---|---|---|---|
| `gemma4_e4b_16bit` | `google/gemma-4-E4B-it` | `balanced_quality` | Requires non-Ollama runtime or a ref change |
| `gemma4_e4b_8bit` | `gemma4:e4b` | `default` | Supported now (Ollama) |
| `gemma4_26b_a4b_4bit` | `gemma4:26b` | `deep_quality` | Supported now (Ollama) |
| Bootstrap helper model | `gemma4:e2b` | n/a | Optional helper / fast fallback |

## 2. Prerequisites

- Docker Desktop running (Linux containers mode)
- NVIDIA driver + CUDA stack available on host
- Repo path: `d:\projects\custom assistant\custalb-gpt`

## 3. Start the Stack

```powershell
cd "d:\projects\custom assistant\custalb-gpt"
docker compose -f infra/docker-compose.yml up --build -d
docker compose -f infra/docker-compose.yml ps
```

Expected services: `goi-ollama`, `goi-api`, `goi-ui` in `Up` state.

## 4. Pull All Ollama-Backed Models

Run pulls one at a time:

```powershell
docker exec goi-ollama ollama pull gemma4:e2b
docker exec goi-ollama ollama pull gemma4:e4b
docker exec goi-ollama ollama pull gemma4:26b
docker exec goi-ollama ollama list
```

Expected in `ollama list`:

- `gemma4:e2b`
- `gemma4:e4b`
- `gemma4:26b`

## 5. Validate API, UI, and Model Routing

Health and model registry:

```powershell
curl.exe -s http://localhost:8000/health
curl.exe -s http://localhost:8000/v1/models
```

Per-profile inference tests:

```powershell
$tmp = Join-Path $env:TEMP "goi-chat-test.json"

@'
{
  "model": "gemma4_e4b_8bit",
  "messages": [{"role":"user","content":"Reply with: e4b ok"}],
  "stream": false
}
'@ | Set-Content -LiteralPath $tmp -Encoding UTF8
curl.exe -s -i -H "Content-Type: application/json" --data-binary "@$tmp" http://localhost:8000/v1/chat/completions

@'
{
  "model": "gemma4_26b_a4b_4bit",
  "messages": [{"role":"user","content":"Reply with: 26b ok"}],
  "stream": false
}
'@ | Set-Content -LiteralPath $tmp -Encoding UTF8
curl.exe -s -i -H "Content-Type: application/json" --data-binary "@$tmp" http://localhost:8000/v1/chat/completions
```

UI check:

- Open `http://localhost:3000`
- Confirm chat works and model selector can switch models per chat

## 6. 16-bit Profile Note (`gemma4_e4b_16bit`)

Current profile config uses:

- `model_ref: google/gemma-4-E4B-it`

Your running backend currently calls Ollama (`/api/chat`). Ollama expects tags like `gemma4:e4b`, so this 16-bit profile will not resolve unless you do one of these:

1. Keep Ollama-only runtime and change `model_ref` to an Ollama-available tag.
2. Add a second inference backend that can serve `google/gemma-4-E4B-it` directly.

If you stay Ollama-only, update `config/model_profiles.yaml` before testing that profile.

## 7. Troubleshooting

- `502 model not found`: model was not pulled into Ollama yet.
- Slow first response: model still loading/warming.
- GPU memory pressure: prefer `gemma4:e4b` or `gemma4:e2b` for routine use.
- Check runtime logs:

```powershell
docker logs goi-ollama --tail 200
docker logs goi-api --tail 200
```

## 8. Shutdown

```powershell
docker compose -f infra/docker-compose.yml down
```

