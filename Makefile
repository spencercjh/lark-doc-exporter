.PHONY: fmt lint test build ci

fmt:
	uv run ruff format .

lint:
	uv run ruff format --check .
	uv run ruff check .

test:
	uv run pytest -q

build:
	uv build

ci: lint test build
