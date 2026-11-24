FROM python:3.14-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends bubblewrap nodejs npm fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

COPY package.json package-lock.json ./

RUN npm ci --omit=dev --no-audit --no-fund

COPY requirements.txt ./

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd --uid 1000 --create-home appuser \
    && mkdir -p /app/data \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

# the app mostly waits on upstream apis, so a couple of threaded workers is plenty.
# fewer workers also means fewer copies of every in-memory cache
ENV WEB_CONCURRENCY=2 \
    MALLOC_ARENA_MAX=2 \
    PYTHONUNBUFFERED=1

CMD ["gunicorn", "--worker-class", "gthread", "--threads", "16", "--backlog", "512", "--max-requests", "5000", "--max-requests-jitter", "500", "-b", "0.0.0.0:8000", "--timeout", "180", "wrapped-fm:app"]
