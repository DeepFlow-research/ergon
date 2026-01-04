FROM python:3.13-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    libtesseract-dev \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install uv

# Copy requirements and lock file
COPY pyproject.toml uv.lock ./
RUN uv pip install --system -e .

# Copy application code
COPY . .

# Expose port
EXPOSE 9000

# Run FastAPI server
# Use --reload in development (when INNGEST_DEV=1) for hot-reload on code changes
# Explicitly watch mounted directories for changes
CMD ["sh", "-c", "if [ \"$INNGEST_DEV\" = \"1\" ]; then uvicorn h_arcane.api.main:app --host 0.0.0.0 --port 9000 --reload --reload-dir /app/h_arcane --reload-dir /app/scripts; else uvicorn h_arcane.api.main:app --host 0.0.0.0 --port 9000; fi"]

