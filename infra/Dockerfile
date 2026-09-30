# AI Farm Intelligence Network - backend image.
#
# Multi-stage so the runtime layer carries no compilers and no build toolchain.
# OpenCV is the headless build: there is no GUI in a container.
#
#   docker build -f infra/Dockerfile -t farm-intelligence .
#   docker run --rm -p 8080:8080 -e MOCK_SERVICES=true farm-intelligence

FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build
COPY requirements.txt .
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install -r requirements.txt


FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    PORT=8080

# Run unprivileged. The image needs no root and no shell tooling at runtime.
RUN useradd --create-home --uid 10001 appuser

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY --chown=appuser:appuser backend/ ./backend/
COPY --chown=appuser:appuser ml/ ./ml/
COPY --chown=appuser:appuser geospatial/ ./geospatial/
COPY --chown=appuser:appuser configs/ ./configs/
COPY --chown=appuser:appuser data/ ./data/
COPY --chown=appuser:appuser requirements.txt ./

# Uploaded images and generated GeoJSON maps land here. Mount a volume in
# production, or point LOCAL_STORAGE_DIR at a GCS bucket.
RUN mkdir -p /app/.local_data/storage && chown -R appuser:appuser /app/.local_data

USER appuser
EXPOSE 8080

# Mock mode is the safe default for a container that has no credentials yet.
# Override with -e MOCK_SERVICES=false in a real deployment.
ENV MOCK_SERVICES=true

# One worker: the service holds in-process state and a single container is the
# documented topology. Scale horizontally, not with more workers.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=4).status == 200 else 1)"

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1", "--no-server-header"]
