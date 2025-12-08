FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    libtesseract-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e .

# Copy application code
COPY . .

# Expose port
EXPOSE 9000

# Run FastAPI server
# Use --reload in development (when INNGEST_DEV=1) for hot-reload on code changes
# Explicitly watch mounted directories for changes
CMD ["sh", "-c", "if [ \"$INNGEST_DEV\" = \"1\" ]; then uvicorn h_arcane.api.main:app --host 0.0.0.0 --port 9000 --reload --reload-dir /app/h_arcane --reload-dir /app/scripts; else uvicorn h_arcane.api.main:app --host 0.0.0.0 --port 9000; fi"]

