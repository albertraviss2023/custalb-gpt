# Setup and Deployment Guide

## 1. Local Development

Prerequisites:

- Docker + Docker Compose
- NVIDIA drivers + NVIDIA Container Toolkit
- Optional: Python 3.12 and Node 22 for native development

Start full stack:

```bash
docker compose -f infra/docker-compose.yml up --build -d
```

Bootstrap models:

```powershell
$env:HF_TOKEN="hf_xxx"
./scripts/bootstrap-models.ps1
# Optional single-model pull:
./scripts/bootstrap-models.ps1 -Model "Qwen/Qwen2.5-14B-Instruct"
```

Notes:

- `HF_TOKEN` (or `HUGGINGFACE_HUB_TOKEN`) is required for gated Hugging Face models such as Gemma 4.
- Ensure the token account has accepted access for `google/gemma-4-E4B-it`.

Open UI:

- `http://localhost:3000`

API:

- `http://localhost:8000`

## 2. Native Backend Development

```bash
cd backend
pip install -r requirements.txt
pip install -e .[dev]
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## 3. Native Frontend Development

```bash
cd frontend
npm install
npm run dev
```

Vite proxy forwards `/api/*` to `http://localhost:8000/*`.

## 4. Kubernetes Deployment

Apply manifests:

```bash
kubectl apply -k infra/k8s
```

Optional model preload job:

```bash
kubectl create job --from=job/goi-model-loader goi-model-loader-manual -n personal-goi
```

## 5. CI/CD

- `CI` workflow runs lint/tests/build checks on push and pull requests.
- `CD` workflow can build/push GHCR images and apply Kubernetes manifests when required secrets are configured:
- `GHCR_USERNAME`
- `GHCR_TOKEN`
- `KUBE_CONFIG_BASE64`
