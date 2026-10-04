# EliteBot — image unique : API FastAPI + dashboard + moteur de trading
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dépendances d'abord (cache Docker efficace)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Code applicatif
COPY app ./app

# Port exposé (Render/Railway injectent $PORT)
EXPOSE 8000

# Healthcheck interne (l'hébergeur utilise aussi /api/health)
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status==200 else 1)"

# Démarrage : uvicorn lit $PORT fourni par l'hébergeur (défaut 8000)
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
