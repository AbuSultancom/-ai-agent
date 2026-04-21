FROM python:3.11-slim

WORKDIR /app

# System deps for Playwright and ChromaDB
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl wget gnupg ca-certificates \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libxkbcommon0 \
    libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 \
    libasound2 libx11-6 libxext6 libxss1 \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browser
RUN playwright install chromium --with-deps || true

# Copy project
COPY . .

# Create data directory for ChromaDB
RUN mkdir -p /app/data/chromadb

ENV FLASK_APP=core/app.py
ENV PYTHONPATH=/app
EXPOSE 5000

CMD ["python", "orchestrator.py", "serve"]
