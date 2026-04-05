FROM python:3.13-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    libtesseract-dev \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

RUN pip install uv

# Install h_arcane package
COPY h_arcane/pyproject.toml h_arcane/
COPY h_arcane/h_arcane/ h_arcane/h_arcane/
RUN cd h_arcane && uv pip install --system -e .

# Install arcane_builtins package
COPY arcane_builtins/pyproject.toml arcane_builtins/
COPY arcane_builtins/arcane_builtins/ arcane_builtins/arcane_builtins/
RUN cd arcane_builtins && uv pip install --system -e .

COPY .env ./

EXPOSE 9000

CMD ["uvicorn", "h_arcane.core.api.app:app", "--host", "0.0.0.0", "--port", "9000"]
