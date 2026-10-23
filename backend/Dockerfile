FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir -e .

COPY . .

# Run as an unprivileged user. /data holds the SQLite file and its backups in production.
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin app \
    && mkdir -p /data /app/generated \
    && chown -R app:app /data /app/generated
USER app

EXPOSE 8000

# Apply migrations, then serve. --proxy-headers so the client IP is correct behind a reverse proxy
# (set FORWARDED_ALLOW_IPS to the proxy's address, or "*" when only the proxy can reach the API).
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers"]
