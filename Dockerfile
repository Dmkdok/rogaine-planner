# syntax=docker/dockerfile:1

# Base: everything the product needs at runtime. CPU only — the GPU is M7's business.
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_ROOT_USER_ACTION=ignore

# tesseract-ocr  — control numbers (ADR-009)
# libglib2.0-0   — required by opencv-python-headless
# libgomp1       — OpenMP runtime used by scikit-image / scipy
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        libglib2.0-0 \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependency layer: only invalidated when pyproject changes.
COPY pyproject.toml ./
COPY src ./src
RUN pip install -e .

EXPOSE 8000
CMD ["rogaine", "--help"]


# Test: adds the dev toolchain. Playwright browsers land here in M6 (T062).
FROM base AS test

RUN pip install -e ".[dev]"
RUN playwright install --with-deps chromium
COPY . .
CMD ["pytest"]
