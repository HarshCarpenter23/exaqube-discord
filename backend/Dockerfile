# Multi-stage build: install dependencies in a builder, copy only what runtime
# needs into a slim final image. The final image has no compiler toolchain and
# runs as a non-root user.

# --- Builder ----------------------------------------------------------------
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 PYTHONDONTWRITEBYTECODE=1

WORKDIR /install
COPY requirements.txt .
# Build wheels here so the final stage installs without build tools.
RUN pip install --upgrade pip && pip wheel --wheel-dir /wheels -r requirements.txt

# --- Runtime ----------------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

# Non-root user.
RUN useradd --create-home --uid 1000 app

WORKDIR /app
COPY --from=builder /wheels /wheels
COPY requirements.txt .
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt \
    && rm -rf /wheels

COPY . /app

# Artifact output dir, owned by the non-root user. A fresh named volume mounted
# here inherits this ownership, so the app can write generated files.
RUN mkdir -p /artifacts && chown -R app:app /artifacts

USER app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
