FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps: build tools for paramiko/cryptography wheels, tini for clean PID 1 signal handling
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libffi-dev \
        tini \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY src/ /app/src/

RUN mkdir -p /app/data /app/downloads

# Non-root runtime user
RUN useradd -m -u 1000 tdm && chown -R tdm:tdm /app
USER tdm

ENV PYTHONPATH=/app/src \
    DATA_DIR=/app/data \
    DEFAULT_DOWNLOAD_DIR=/app/downloads \
    HOST=0.0.0.0 \
    PORT=8000

EXPOSE 8000

VOLUME ["/app/data", "/app/downloads"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')" || exit 1

ENTRYPOINT ["tini", "--"]
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
