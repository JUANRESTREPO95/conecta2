# Conecta2 — panel de pedidos en Docker
# Se construye desde la raíz del repositorio: docker compose -f docker/docker-compose.yml up -d --build
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=America/Bogota \
    CONECTA2_PUERTO=8050

COPY panel/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY panel/app ./app
COPY panel/run.py .
COPY panel/crear_agente_token.py .

# datos/ se monta como volumen (BD, logos y llave de claves)
VOLUME ["/app/datos"]
EXPOSE 8050

CMD ["python", "run.py", "--puerto", "8050"]
