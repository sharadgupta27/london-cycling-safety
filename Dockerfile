# ==============================================================================
# London Cycling Safety – unified Python container image
# ==============================================================================
# This single image is used for BOTH the pipeline runner and Streamlit dashboard.
# The active service (pipeline vs dashboard) is selected via the CMD in each
# docker-compose override file.
#
# Build context: project root
# ==============================================================================

FROM python:3.11-slim

# ── System dependencies ────────────────────────────────────────────────────
# libgdal-dev + gdal-bin : GeoPandas raster/vector I/O
# libspatialindex-dev    : R*-tree index used by Shapely / geopandas sjoin
# git                    : dbt dep resolution (some packages reference git)
# curl                   : health checks / wget fallback
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc g++ git curl \
        libgdal-dev gdal-bin \
        libspatialindex-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Python dependencies ────────────────────────────────────────────────────
# Copy requirements first so this layer is cached when only source changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Project source ─────────────────────────────────────────────────────────
COPY . .

# ── Runtime environment ────────────────────────────────────────────────────
# PYTHONPATH: makes all project packages importable (ingestion, transforms, …)
# DBT_PACKAGES_PATH: a subdirectory *inside* the Docker volume mount point
#   (/tmp/dbt_packages is the volume mount; dbt deps calls rmtree on this path
#   before installing, which fails with EBUSY if it is the mount point itself).
ENV PYTHONPATH=/app \
    DBT_PACKAGES_PATH=/tmp/dbt_packages/pkgs

# Dashboard port (Streamlit default)
EXPOSE 8501

# ── Default command: launch Streamlit dashboard ───────────────────────────
# Override in docker-compose.dev/prod.yml pipeline service to run the pipeline.
CMD ["python", "-m", "streamlit", "run", "dashboard/app.py", \
     "--server.port=8501", \
     "--server.headless=true", \
     "--server.address=0.0.0.0"]
