FROM python:3.10-slim

WORKDIR /app

# Copy the CVT model package first (needed by requirements.txt)
COPY cvtModel /cvtModel

# Copy backend requirements
COPY backend/requirements.txt .

# Install Python dependencies (including cvtModel in editable mode)
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the backend code
COPY backend/ .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
