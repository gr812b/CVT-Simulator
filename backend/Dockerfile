# Build from repository root:
#   docker build -f backend/Dockerfile -t cvt-simulator-api .
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# CINDER and all backend runtime dependencies come from the backend's pinned
# requirements file. No repository-local CINDER source is copied into the image.
COPY backend/requirements.txt /app/requirements.txt
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r /app/requirements.txt

# Includes app/, presets/, and the rest of the runtime backend package.
COPY backend /app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
