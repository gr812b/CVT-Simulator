# Build from repository root so both sibling projects are available:
#   docker build -f backend/Dockerfile -t cvt-simulator-api .
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# requirements.txt installs CINDER from ../cvtModel, which resolves to /cvtModel
# from this working directory.
COPY cvtModel /cvtModel
COPY backend/requirements.txt /app/requirements.txt
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements.txt

COPY backend /app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
