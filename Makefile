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
#
# Docker shortcuts:
#   make dev-up              Build image + start all dev services (DuckDB)
#   make dev-run             Run the pipeline once in dev Docker stack
#   make dev-down            Stop and remove dev containers
#   make prod-up             Build image + start all prod services (BigQuery)
#   make prod-run            Run the pipeline once in prod Docker stack
#   make prod-down           Stop and remove prod containers
#   make docker-build        Build (or rebuild) the Python image only
#   make docker-logs         Tail logs for all running services
#
# Airflow shortcuts:
#   make airflow-up          Build Airflow image + start webserver + scheduler
#   make airflow-down        Stop and remove Airflow containers
#   make airflow-logs        Tail Airflow logs
# ============================================================

PYTHON     ?= python
UV         ?= uv
SRC_DIRS   := ingestion transforms dashboard run_pipeline.py
TEST_DIR   := tests
LINE_LEN   := 100

# Docker Compose file pairs
DC_BASE    := docker-compose.yml
DC_DEV     := docker-compose.dev.yml
DC_PROD    := docker-compose.prod.yml
DC_DEV_CMD := docker compose -f $(DC_BASE) -f $(DC_DEV)
DC_PROD_CMD:= docker compose -f $(DC_BASE) -f $(DC_PROD)

.PHONY: all install lint format format-check test test-cov type-check clean \
        pipeline pipeline-prod pipeline-prod-no-ingest schedule \
        dev-up dev-run dev-down prod-up prod-run prod-down \
        docker-build docker-logs \
        airflow-up airflow-down airflow-logs

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

# ────────────────────────────────────────────────────────────
# Docker – Development stack (DuckDB, no GCP credentials needed)
# ────────────────────────────────────────────────────────────
dev-up:
	$(DC_DEV_CMD) up -d --build
	@echo "  [OK] Dev stack is up."
	@echo "  Streamlit Dashboard  -->  http://localhost:8501"
	@echo "  Airflow UI (if running) --> http://localhost:8080  (run: make airflow-up)"

dev-run:
	$(DC_DEV_CMD) run --rm pipeline

dev-down:
	$(DC_DEV_CMD) down

# ────────────────────────────────────────────────────────────
# Docker – Production stack (BigQuery)
# ────────────────────────────────────────────────────────────
prod-up:
	$(DC_PROD_CMD) up -d --build
	@echo "  [OK] Production stack is up."
	@echo "  Streamlit Dashboard  -->  http://localhost:8501"
	@echo "  Airflow UI (if running) --> http://localhost:8080  (run: make airflow-up)"

prod-run:
	$(DC_PROD_CMD) run --rm --build pipeline

prod-down:
	$(DC_PROD_CMD) down

# ────────────────────────────────────────────────────────────
# Docker – Utilities
# ────────────────────────────────────────────────────────────
docker-build:
	docker build -t london-cycling-safety:latest .

docker-logs:
	$(DC_DEV_CMD) logs -f

# ────────────────────────────────────────────────────────────
# Airflow – Orchestration stack (webserver + scheduler)
# UI: http://localhost:8080  (admin / admin)
# ────────────────────────────────────────────────────────────
airflow-up:
	docker build -t london-cycling-airflow:latest -f Dockerfile.airflow .
	docker compose -f airflow/docker-compose.yml up -d
	@echo "  [OK] Airflow stack is up."
	@echo "  Airflow UI  -->  http://localhost:8080  (admin / admin)"

# Wait a moment for the init service to finish, then show status
airflow-init:
	docker compose -f airflow/docker-compose.yml run --rm airflow-init

airflow-down:
	docker compose -f airflow/docker-compose.yml down

airflow-logs:
	docker compose -f airflow/docker-compose.yml logs -f
