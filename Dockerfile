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

EXPOSE 9000

CMD ["uvicorn", "ergon_core.core.api.app:app", "--host", "0.0.0.0", "--port", "9000"]
