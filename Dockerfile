FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
RUN useradd --create-home --uid 1000 aplicacao && chown aplicacao /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Imagem dos testes: acrescenta pytest e pytest-cov.
FROM base AS testes
COPY requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY . .
USER aplicacao

# Imagem da API (padrão): só as dependências de produção, sem root, servida pelo gunicorn.
FROM base AS producao
COPY . .
USER aplicacao
EXPOSE 8000
# --preload inicializa o banco uma única vez, antes de abrir a porta e criar os workers.
CMD ["gunicorn", "--preload", "--workers", "2", "--bind", "0.0.0.0:8000", "api:criar_app()"]
