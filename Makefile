.DEFAULT_GOAL := help
.PHONY: help install run migrate makemigrations test lint fmt collectstatic shell hooks hooks-run docker-build docker-run clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

install: ## Create venv + install deps (uv sync)
	uv sync

run: ## Run the dev server (LLM_PROVIDER=fake works with no key)
	uv run python manage.py runserver

migrate: ## Apply database migrations
	uv run python manage.py migrate

makemigrations: ## Generate migrations for the brief app
	uv run python manage.py makemigrations brief

test: ## Run the test + eval suite (offline, no API key)
	uv run python manage.py test --settings=briefgen.settings_test

lint: ## Lint with ruff
	uv run ruff check .

fmt: ## Format with ruff
	uv run ruff format .

hooks: ## Install the git pre-commit hooks
	uv run pre-commit install

hooks-run: ## Run all pre-commit hooks against every file
	uv run pre-commit run --all-files

collectstatic: ## Collect static files
	uv run python manage.py collectstatic --noinput

shell: ## Open a Django shell
	uv run python manage.py shell

docker-build: ## Build the production image
	docker build -t collabstr-brief .

docker-run: ## Run the production image on :8000
	docker run --rm --name collabstr-brief -p 8000:8000 --env-file .env collabstr-brief

clean: ## Remove venv, caches, sqlite db, collected static
	rm -rf .venv staticfiles db.sqlite3
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
