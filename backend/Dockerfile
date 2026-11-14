# Build context is the repository root: docker build -f backend/Dockerfile -t isomorph-backend .
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install -r /app/backend/requirements.txt

COPY backend /app/backend
COPY data /app/data
RUN useradd --create-home --uid 10001 isomorph && chown -R isomorph /app
USER isomorph

ENV ISOMORPH_DATA_DIR=/app/data PYTHONPATH=/app/backend
WORKDIR /app/backend
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --retries=3 CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=2)" || exit 1
# Run migrations first in deployment: alembic upgrade head
CMD ["uvicorn", "api.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
