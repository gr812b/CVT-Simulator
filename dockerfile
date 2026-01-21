FROM python:3.10-slim

WORKDIR /app

COPY . .

EXPOSE 8000
CMD pip install --no-cache-dir -r requirements.txt && uvicorn main:app --host 0.0.0.0