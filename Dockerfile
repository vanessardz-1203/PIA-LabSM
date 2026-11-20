# Imagen reproducible para ejecutar pruebas y experimentos sin instalar dependencias en el host
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app:/app/Construccion_de_entorno

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Estructura por etapa del plan de desarrollo
COPY Construccion_de_entorno /app/Construccion_de_entorno
COPY Programacion_de_agentes /app/Programacion_de_agentes
COPY Coordinacion_multiagente /app/Coordinacion_multiagente

CMD ["pytest", "-v"]
