FROM python:3.13-slim-bookworm

WORKDIR /app
COPY requirements.txt ./
COPY alembic.ini ./alembic.ini
COPY alembic/ ./alembic/
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app/ ./backend/app/
COPY frontend/ ./frontend/
# StaticFiles needs this directory even before assets are added.
RUN mkdir -p /app/frontend/static

WORKDIR /app/backend
USER 10001:10001
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
