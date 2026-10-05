# syntax=docker/dockerfile:1
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-por \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./requirements.txt
RUN --mount=type=secret,id=proxy_ca,required=false \
    if [ -s /run/secrets/proxy_ca ]; then \
        PIP_CERT=/run/secrets/proxy_ca pip install --no-cache-dir -r requirements.txt; \
    else \
        pip install --no-cache-dir -r requirements.txt; \
    fi
COPY . .
RUN chmod +x scripts/start-web.sh scripts/start-worker.sh
RUN useradd --create-home --uid 10001 leiaberta \
    && chown -R leiaberta:leiaberta /app

EXPOSE 8000
USER leiaberta
CMD ["sh", "scripts/start-web.sh"]
