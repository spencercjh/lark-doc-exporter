.PHONY: fmt lint test test-public-doc-e2e build ci

fmt:
	uv run ruff format .

lint:
	uv run ruff format --check .
	uv run ruff check .

test:
	uv run pytest -q -m "not e2e_public_doc"

test-public-doc-e2e:
	uv run pytest tests/test_public_doc_e2e.py -q -m e2e_public_doc

build:
	uv build

ci: lint test build
