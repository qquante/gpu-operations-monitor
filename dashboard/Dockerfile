FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY state_store.py .
COPY scout_history.py .
COPY scout_settings.py .
COPY vast_service.py .
COPY clore_service.py .
COPY static ./static

# shared/ is mounted at runtime via docker-compose volume

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
