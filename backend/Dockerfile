# Build from repository root so the backend and CINDER package are both available:
#   docker build -f backend/Dockerfile -t cvt-simulator-api .
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Production image: install CINDER as a normal package, not an editable install.
COPY cvtModel /opt/cvtModel
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir /opt/cvtModel

# Install only backend runtime dependencies. This file deliberately does not
# contain the local editable CINDER path used during development.
COPY backend/requirements-runtime.txt /app/requirements-runtime.txt
RUN python -m pip install --no-cache-dir -r /app/requirements-runtime.txt

# Includes app/, presets/, and the rest of the runtime backend package.
COPY backend /app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
