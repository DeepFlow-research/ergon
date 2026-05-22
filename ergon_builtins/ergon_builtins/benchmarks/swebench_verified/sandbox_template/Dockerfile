# SWE-Bench Verified sandbox: one image that covers the 12 repos in Verified.
# Per-instance Python selection and dependency install is driven at runtime
# by swebench.harness.test_spec — this image only provides the substrate.
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PATH=/root/.local/bin:/usr/local/bin:$PATH
ENV UV_CACHE_DIR=/workspace/.uv-cache

# --- system deps -------------------------------------------------------------
# Kept in a single layer. Grouped by repo that needs them for readability.
RUN apt-get update && apt-get install -y --no-install-recommends \
    # core
    git ca-certificates curl wget unzip xz-utils \
    build-essential pkg-config \
    # python build deps
    libssl-dev libffi-dev libsqlite3-dev libbz2-dev \
    zlib1g-dev libreadline-dev liblzma-dev \
    # matplotlib / pillow
    libfreetype6-dev libpng-dev libjpeg-dev libtiff-dev \
    # scikit-learn / scipy
    libopenblas-dev liblapack-dev gfortran \
    # sphinx / lxml / xarray
    libxml2-dev libxslt1-dev \
    # django (psycopg2)
    libpq-dev \
  && rm -rf /var/lib/apt/lists/*

# --- uv as Python-version manager -------------------------------------------
RUN curl -LsSf https://astral.sh/uv/install.sh | sh && \
    ln -sf /root/.local/bin/uv /usr/local/bin/uv

# --- swebench harness (for test_spec + grading) -----------------------------
# Install into a dedicated venv so it does not collide with task-specific
# repo environments.
RUN uv venv /opt/swebench-harness --python 3.11 && \
    /opt/swebench-harness/bin/pip install --no-cache-dir "swebench>=3.0,<5"
ENV SWEBENCH_PY=/opt/swebench-harness/bin/python

# --- workspace layout -------------------------------------------------------
RUN mkdir -p /workspace/repo /workspace/.uv-cache /workspace/artifacts /inputs

WORKDIR /workspace
CMD ["/bin/bash"]
