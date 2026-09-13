FROM python:3.13-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    libtesseract-dev \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

RUN pip install uv

# Resolve the API/CLI and their dependencies from the same workspace lock as tests.
# Copy all member manifests because uv validates the workspace even when selecting
# just the CLI package. No credentials or local virtual environment enter the image.
COPY pyproject.toml uv.lock ./
COPY ergon_core/ ergon_core/
COPY ergon_builtins/ ergon_builtins/
COPY ergon_cli/ ergon_cli/
COPY ergon_infra/ ergon_infra/
COPY ergon_ingestion/ ergon_ingestion/
COPY examples/ examples/
RUN uv sync --frozen --no-dev --package ergon-cli
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 9000

CMD ["uvicorn", "ergon_core.core.infrastructure.http.app:app", "--host", "0.0.0.0", "--port", "9000"]
