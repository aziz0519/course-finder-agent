.DEFAULT_GOAL := help
PY := uv run python

.PHONY: help sync validate validate-strict ingest test lint fmt typecheck check ui infra-synth images e2e-up e2e e2e-down ci-scope clean

help:  ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

sync:  ## Create the virtual environment and install all dependencies
	uv sync --all-groups

validate:  ## Validate the supplied datasets (pending inputs are tolerated)
	$(PY) scripts/validate_datasets.py

validate-strict:  ## Validate the datasets and fail when any input is still missing
	$(PY) scripts/validate_datasets.py --require-complete

ingest:  ## Ingest all five PDFs with checksum-bound QA and local retrieval activation
	$(PY) scripts/ingest_datasets.py

test:  ## Run the test suite
	uv run pytest

lint:  ## Lint without modifying files
	uv run ruff check .

fmt:  ## Format and auto-fix
	uv run ruff format .
	uv run ruff check --fix .

typecheck:  ## Static type check
	uv run mypy

check: lint typecheck test  ## Everything CI will run

ui:  ## Run the Gradio UI (start the API first)
	uv run python -m ui.app

infra-synth:  ## Locally synthesize CDK templates; performs no AWS calls
	uv run python -m infra.app

images:  ## Build the API, UI, and worker container images (no push)
	docker compose build

e2e-up:  ## Build and start API/UI containers, then wait for the UI
	docker compose up -d --build
	bash scripts/wait_for_ui.sh

e2e:  ## Run browser E2E against an already-running UI
	uv run pytest e2e -q

e2e-down:  ## Stop containers and remove their local volumes
	docker compose down -v

ci-scope:  ## Verify the workflow contains no AWS/ECR deployment steps
	bash scripts/check_ci_scope.sh

clean:  ## Remove local caches and derived artefacts
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find data/processed -mindepth 1 ! -name .gitkeep -delete
