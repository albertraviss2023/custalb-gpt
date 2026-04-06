# Testing, CI/CD, and Scaling

Version: 1.0
Date: April 6, 2026

## 1. Testing Strategy

## 1.1 Backend Tests

Current coverage includes:

- Model registry config loading
- Chat service fallback on OOM behavior

Run:

```bash
cd backend
pytest
```

## 1.2 Frontend Validation

Current checks:

- TypeScript build
- ESLint rules

Run:

```bash
cd frontend
npm run lint
npm run build
```

## 1.3 Compose and Kubernetes Validation

Compose syntax check:

```bash
docker compose -f infra/docker-compose.yml config
```

Kubernetes manifest render check:

```bash
kubectl kustomize infra/k8s
```

## 1.4 Recommended Next Test Additions

- API integration tests for chat endpoints
- Streaming contract tests (SSE chunk semantics)
- UI e2e tests with Playwright
- load/perf tests per model profile

## 2. CI Pipeline

Workflow:

- `.github/workflows/ci.yml`

Jobs:

- `backend`: install + lint + test
- `frontend`: install + lint + build
- `docker-build`: build API and UI images

Trigger:

- pull requests
- push to `main`

## 3. CD Pipeline

Workflow:

- `.github/workflows/cd.yml`

Stages:

1. Build and push images to GHCR
2. Apply Kubernetes manifests

Required secrets:

- `GHCR_USERNAME`
- `GHCR_TOKEN`
- `KUBE_CONFIG_BASE64`

## 4. Operational Scaling Plan

## 4.1 Vertical Scaling (first path)

- Increase GPU VRAM / system RAM
- Move default from E4B 8-bit to higher quality profiles
- Expand context limits cautiously

## 4.2 Horizontal Scaling (Kubernetes)

- Scale UI and API replicas independently
- Keep Ollama as singleton unless using model-sharded design
- Add API load balancing via service + ingress

## 4.3 Data and State Scaling

- Replace SQLite with Postgres for multi-user/high-concurrency
- Add object storage for export/history backups
- Keep model cache on persistent volumes

## 4.4 Observability Scaling

Recommended additions for iteration 2+:

- Prometheus metrics endpoint from API
- Structured logs shipped to Loki/Elastic
- Grafana dashboards for latency, token throughput, error rates

## 5. Production Readiness Checklist

- CI green on all jobs
- Images reproducibly built
- Kubernetes manifests validated
- Health endpoints monitored
- rollback procedure documented
- model fallback behavior verified