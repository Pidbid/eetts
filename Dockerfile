FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    OUTPUT_DIR=/output

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

RUN groupadd --system eetts \
    && useradd --system --gid eetts --home-dir /app eetts \
    && mkdir -p /output \
    && chown eetts:eetts /output

COPY --chown=eetts:eetts eetts.py ./

USER eetts

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3)"]

CMD ["uvicorn", "eetts:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--log-level", "info"]
