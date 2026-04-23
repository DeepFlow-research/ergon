FROM python:3.13-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    libtesseract-dev \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

RUN pip install uv

# Install ergon_core package
COPY ergon_core/pyproject.toml ergon_core/
COPY ergon_core/ergon_core/ ergon_core/ergon_core/
RUN cd ergon_core && uv pip install --system -e ".[dev]"

# Install ergon_builtins package WITH [data] extra.  ``registry_core.py``
# imports ``SweBenchVerifiedBenchmark`` / ``MiniF2FBenchmark`` /
# ``StagedRubric`` at module-level (per the registry-lazy-import
# refactor); those modules transitively require ``datasets``,
# ``huggingface_hub``, and ``pandas`` respectively.  Without ``[data]``
# the api container fails to import on startup.
COPY ergon_builtins/pyproject.toml ergon_builtins/
COPY ergon_builtins/ergon_builtins/ ergon_builtins/ergon_builtins/
RUN cd ergon_builtins && uv pip install --system -e ".[data]"

# Install the ergon_cli package so the in-container smoke harness can
# call ``ergon_cli.composition.build_experiment`` directly instead of
# shelling out to the ``ergon`` CLI.  Same editable-install pattern.
COPY ergon_cli/pyproject.toml ergon_cli/
COPY ergon_cli/ergon_cli/ ergon_cli/ergon_cli/
RUN cd ergon_cli && uv pip install --system -e "."

# Test-runtime dependencies.  Tests are executed *inside* this container
# (see docker-compose.yml + scripts/smoke_local_run.sh), so pytest and
# friends must be on the image.  Kept aligned with the ``dev`` group in
# the root ``pyproject.toml`` — lint tools (ruff/ty/slopcop/xenon) stay
# host-side and are intentionally absent here.
RUN uv pip install --system \
    "pytest>=9.0.3" \
    "pytest-asyncio>=1.3.0" \
    "pytest-timeout>=0.8.2" \
    "pytest-xdist>=3.8.0" \
    "httpx"

# Copy test + scripts + ci trees so pytest can run inside the container
# without any host-side mount.  docker-compose.yml still bind-mounts
# these paths in dev so edits are live, but the image is self-contained
# for CI and for the real-LLM harness tier.
COPY tests/ /app/tests/
COPY scripts/ /app/scripts/
COPY ci/ /app/ci/

EXPOSE 9000

CMD ["uvicorn", "ergon_core.core.api.app:app", "--host", "0.0.0.0", "--port", "9000"]
