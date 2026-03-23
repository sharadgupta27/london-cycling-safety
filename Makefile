# ============================================================
# London Cycling Safety – Makefile
# ============================================================
# Requirements: make (Git for Windows ships bash + make, or use
#               nmake / MinGW make on Windows).
#
# Usage:
#   make install             Install runtime + dev dependencies (requires uv)
#   make lint                Check code style with ruff
#   make format              Auto-format with black + isort
#   make format-check        Dry-run format check (CI-safe)
#   make test                Run the full pytest suite
#   make test-cov            Run tests with coverage report
#   make type-check          Run mypy type checker
#   make pipeline            Run full pipeline locally (DuckDB)
#   make pipeline-prod       Run full pipeline against BigQuery
#   make schedule            Start weekly BigQuery scheduler
#   make clean               Remove generated caches and build artefacts
#   make all                 lint + format-check + test (useful for CI)
# ============================================================

PYTHON     ?= python
UV         ?= uv
SRC_DIRS   := ingestion transforms dashboard run_pipeline.py
TEST_DIR   := tests
LINE_LEN   := 100

.PHONY: all install lint format format-check test test-cov type-check clean \
        pipeline pipeline-prod pipeline-prod-no-ingest schedule

# ────────────────────────────────────────────────────────────
# Default target
# ────────────────────────────────────────────────────────────
all: lint format-check test

# ────────────────────────────────────────────────────────────
# Install
# ────────────────────────────────────────────────────────────
install:
	$(UV) pip install -r requirements.txt
	$(UV) pip install -r requirements-dev.txt

# ────────────────────────────────────────────────────────────
# Lint  (ruff – fast, replaces flake8 + pyupgrade + isort checks)
# ────────────────────────────────────────────────────────────
lint:
	$(PYTHON) -m ruff check $(SRC_DIRS) $(TEST_DIR)

# ────────────────────────────────────────────────────────────
# Format  (black for style, isort for import order)
# ────────────────────────────────────────────────────────────
format:
	$(PYTHON) -m black --line-length $(LINE_LEN) $(SRC_DIRS) $(TEST_DIR)
	$(PYTHON) -m isort --profile black --line-length $(LINE_LEN) $(SRC_DIRS) $(TEST_DIR)

# ────────────────────────────────────────────────────────────
# Format-check  (CI-safe dry-run, exits non-zero on diff)
# ────────────────────────────────────────────────────────────
format-check:
	$(PYTHON) -m black --check --line-length $(LINE_LEN) $(SRC_DIRS) $(TEST_DIR)
	$(PYTHON) -m isort --check-only --profile black --line-length $(LINE_LEN) $(SRC_DIRS) $(TEST_DIR)

# ────────────────────────────────────────────────────────────
# Tests
# ────────────────────────────────────────────────────────────
test:
	$(PYTHON) -m pytest $(TEST_DIR) -v --tb=short

test-cov:
	$(PYTHON) -m pytest $(TEST_DIR) \
		--cov=ingestion \
		--cov=transforms \
		--cov=dashboard \
		--cov=run_pipeline \
		--cov-report=term-missing \
		--cov-report=html:htmlcov \
		--tb=short

# ────────────────────────────────────────────────────────────
# Type checking
# ────────────────────────────────────────────────────────────
type-check:
	$(PYTHON) -m mypy $(SRC_DIRS) --ignore-missing-imports --python-version 3.11

# ────────────────────────────────────────────────────────────
# Clean
# ────────────────────────────────────────────────────────────
clean:
	find . -type d -name "__pycache__"  -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache"   -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache"   -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "htmlcov"       -exec rm -rf {} + 2>/dev/null || true
	find . -name  ".coverage"            -delete 2>/dev/null || true
	find . -name  "*.pyc"                -delete 2>/dev/null || true

# ────────────────────────────────────────────────────────────
# Pipeline  (orchestration/pipeline.py)
# ────────────────────────────────────────────────────────────
pipeline:
	$(PYTHON) orchestration/pipeline.py

pipeline-prod:
	$(PYTHON) orchestration/pipeline.py --target prod

pipeline-prod-no-ingest:
	$(PYTHON) orchestration/pipeline.py --target prod --skip-ingest

schedule:
	$(PYTHON) orchestration/schedule_pipeline.py --target prod
