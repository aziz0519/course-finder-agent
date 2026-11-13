.DEFAULT_GOAL := help
PY := uv run python

.PHONY: help sync validate validate-strict test lint fmt typecheck check clean

help:  ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

sync:  ## Create the virtual environment and install all dependencies
	uv sync --all-groups

validate:  ## Validate the supplied datasets (pending inputs are tolerated)
	$(PY) scripts/validate_datasets.py

validate-strict:  ## Validate the datasets and fail when any input is still missing
	$(PY) scripts/validate_datasets.py --require-complete

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

clean:  ## Remove local caches and derived artefacts
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find data/processed -mindepth 1 ! -name .gitkeep -delete
