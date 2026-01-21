FROM python:3.10-slim

WORKDIR /app

# Copy backend requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the CVT model package
COPY ../cvtModel /cvtModel
RUN pip install -e /cvtModel

# Copy the rest of the backend code
COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
