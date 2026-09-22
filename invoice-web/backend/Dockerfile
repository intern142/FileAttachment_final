FROM python:3.11-slim
RUN apt-get update && apt-get install -y tesseract-ocr libtesseract-dev poppler-utils libpq-dev libpq5 gcc build-essential && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY frontend/ ./frontend
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--reload"]