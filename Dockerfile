FROM python:3.11-slim as builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt


FROM python:3.11-slim as production

RUN groupadd -r worker && useradd -r -g worker worker

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY --chown=worker:worker . .

USER worker

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    CAMUNDA_URL=http://camunda:8080/engine-rest \
    WORKER_ID=python-worker \
    LOCK_DURATION=300000 \
    POLL_INTERVAL=5 \
    MAX_TASKS=5

CMD ["python", "-u", "start_workers.py"]