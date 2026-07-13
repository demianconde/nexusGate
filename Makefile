.PHONY: install dev up down logs migrate revision lint test fmt

install:
	pip install -r requirements-dev.txt

dev:
	uvicorn app.main:app --reload --port 8000

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f api

migrate:
	alembic upgrade head

revision:
	alembic revision --autogenerate -m "$(m)"

lint:
	ruff check .

fmt:
	ruff check --fix .

test:
	pytest -q
