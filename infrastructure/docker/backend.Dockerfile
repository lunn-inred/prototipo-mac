FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-por tesseract-ocr-eng libglib2.0-0 && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY backend /app/backend
RUN useradd --create-home mac
USER mac
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "backend.mac_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
