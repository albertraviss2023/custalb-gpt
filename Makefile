.PHONY: backend-install backend-lint backend-test backend-run frontend-install frontend-lint frontend-test frontend-build validate up down k8s-apply k8s-delete

validate: backend-lint backend-test frontend-lint frontend-build
	@echo "Validation complete."

backend-install:
	cd backend && pip install -r requirements.txt && pip install -e .[dev]

backend-lint:
	cd backend && ruff check app tests

backend-test:
	cd backend && pytest

backend-run:
	cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

frontend-install:
	cd frontend && npm install

frontend-lint:
	cd frontend && npm run lint

frontend-test:
	cd frontend && npm run test

frontend-build:
	cd frontend && npm run build

up:
	docker compose -f infra/docker-compose.yml up --build -d

down:
	docker compose -f infra/docker-compose.yml down

k8s-apply:
	kubectl apply -k infra/k8s

k8s-delete:
	kubectl delete -k infra/k8s