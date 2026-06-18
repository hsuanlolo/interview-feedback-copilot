.PHONY: help dev-backend dev-frontend test lint typecheck eval docker-up docker-down clean

help:
	@echo "Interview Feedback Copilot — development commands"
	@echo ""
	@echo "  make dev-backend     Start FastAPI backend with hot reload"
	@echo "  make dev-frontend    Start Next.js frontend dev server"
	@echo "  make test            Run all backend tests"
	@echo "  make lint            Lint backend with ruff"
	@echo "  make typecheck       TypeScript type-check frontend"
	@echo "  make eval            Run evaluation suite against gold data"
	@echo "  make migrate         Apply Alembic migrations"
	@echo "  make docker-up       Build and start all services in Docker"
	@echo "  make docker-down     Stop all Docker services"
	@echo "  make clean           Remove build artifacts and temp files"

dev-backend:
	cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

dev-frontend:
	cd frontend && npm run dev

test:
	cd backend && python -m pytest app/tests/ -v

lint:
	cd backend && ruff check app/ && ruff format --check app/

typecheck:
	cd frontend && npm run type-check

eval:
	cd backend && python -m app.evals.run_eval --gold-dir ../sample_data/gold

migrate:
	cd backend && alembic upgrade head

docker-up:
	docker compose up --build

docker-down:
	docker compose down

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true
	find . -type f -name "*.pyc" -delete 2>/dev/null; true
	find . -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null; true
	rm -f backend/interview_copilot.db
	cd frontend && rm -rf .next 2>/dev/null; true
