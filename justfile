set shell := ["bash", "-cu"]

default: test

lint:
    uv run ruff check src tests
    uv run ruff format --check src tests

types:
    uv run mypy src/

test:
    uv run pytest tests/unit tests/integration tests/conformance -q

leaks:
    uv run pytest tests/leaks -v

demo:
    uv run chancel demo --no-llm

mutate:
    uv run mutmut run

docs:
    uv run --group docs mkdocs build --strict

all: lint types test leaks demo
