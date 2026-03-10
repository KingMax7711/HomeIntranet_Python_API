#!/bin/sh

set -e

echo "Attente de PostgreSQL sur $POSTGRES_HOST:$POSTGRES_PORT..."

while ! nc -z "$POSTGRES_HOST" "$POSTGRES_PORT"; do
  sleep 1
done

echo "PostgreSQL est disponible."

echo "Application des migrations Alembic..."
alembic upgrade head

echo "Démarrage de l'application FastAPI..."
uvicorn main:app --host 0.0.0.0 --port 8000