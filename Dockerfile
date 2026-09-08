# ============================================
# Etapa 1: Descargar dependencias (cache)
# ============================================
FROM python:3.14-slim AS deps
WORKDIR /app
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY pyproject.toml ./
RUN mkdir app && touch app/__init__.py && \
    pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir . && \
    rm -rf app

# ============================================
# Etapa 2: Compilar la aplicación
# ============================================
FROM deps AS build
COPY app ./app
RUN pip install --no-cache-dir --no-deps -e .

# ============================================
# Etapa 3: Imagen final liviana
# ============================================
FROM python:3.14-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl libaio1t64 && \
    rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=deps /opt/venv /opt/venv
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini

RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -s /bin/sh -M appuser && \
    chown -R appuser:appgroup /app
USER appuser

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
EXPOSE 8082
ENTRYPOINT ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8082"]
