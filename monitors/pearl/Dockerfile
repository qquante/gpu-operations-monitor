FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY monitor.py .

# shared/ is mounted at runtime via docker-compose volume
# so it's available at /app/shared without being baked into the image

CMD ["python", "-u", "monitor.py"]
