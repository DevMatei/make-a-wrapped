FROM python:3.14-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends nodejs npm \
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

CMD ["gunicorn", "--worker-class", "gthread", "--workers", "4", "--threads", "8", "--backlog", "512", "-b", "0.0.0.0:8000", "--timeout", "180", "wrapped-fm:app"]
