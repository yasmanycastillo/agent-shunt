FROM python:3.11-slim

WORKDIR /app

COPY src/ /app/src/
COPY pyproject.toml README.md LICENSE /app/

ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["python", "-m", "model_shunt"]
