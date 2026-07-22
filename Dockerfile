# Use Python 3.12 slim image for lightweight container
FROM python:3.12-slim

# Prevent Python from writing .pyc files and buffer outputs
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8000

WORKDIR /app

# Install system dependencies (build-essential, curl, git for dependencies if needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements files
COPY requirements.txt ./
COPY scripts/api/requirements.txt ./scripts_api_requirements.txt

# Install Python dependencies and download NLP models
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir -r scripts_api_requirements.txt \
    && python -m spacy download en_core_web_sm \
    && python -c "import nltk; nltk.download('vader_lexicon')"

# Copy full application codebase
COPY . .

# Expose API port
EXPOSE 8000

# Start Uvicorn server for FastAPI
CMD ["sh", "-c", "python -m uvicorn scripts.api.main:create_app --factory --host 0.0.0.0 --port ${PORT}"]
