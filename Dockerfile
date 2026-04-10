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

# Install ergon_builtins package
COPY ergon_builtins/pyproject.toml ergon_builtins/
COPY ergon_builtins/ergon_builtins/ ergon_builtins/ergon_builtins/
RUN cd ergon_builtins && uv pip install --system -e .

EXPOSE 9000

CMD ["uvicorn", "ergon_core.core.api.app:app", "--host", "0.0.0.0", "--port", "9000"]
