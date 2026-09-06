# 提 PR 前必须全绿(02 §11.5:make check = 完整 PR CI 等价物)。
.PHONY: check test

check:
	uv run ruff check .
	uv run lint-imports
	uv run python scripts/budget.py
	uv run python scripts/check_infra_keywords.py
	uv run python scripts/check_test_imports.py
	uv run pytest

test:
	uv run pytest
