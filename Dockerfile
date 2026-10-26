FROM python:3.11-slim

# No .pyc clutter; unbuffered stdout/stderr so `docker logs` shows scheduler
# and pipeline output as it happens.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Runtime dependencies only (pytest etc. live in requirements-dev.txt).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Run as an unprivileged user.
RUN useradd --create-home --uid 10001 appuser
COPY --chown=appuser:appuser . .
USER appuser

CMD ["python", "-m", "src.orchestration.run_pipeline"]