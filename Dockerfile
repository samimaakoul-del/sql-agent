# Image unique pour l'API (FastAPI) et l'interface (Streamlit).
# Le service à lancer est choisi par la commande dans docker-compose.yml.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 1. Dépendances d'abord (mises en cache tant que requirements.txt ne change pas)
COPY requirements.txt .
RUN pip install -r requirements.txt

# 2. Code de l'application
COPY pyproject.toml README.md ./
COPY src/ src/
RUN pip install --no-deps .

# Utilisateur non-root (bonne pratique de sécurité)
RUN useradd --create-home appuser
USER appuser

EXPOSE 8000
CMD ["uvicorn", "sql_agent.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
