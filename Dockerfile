# Stage 1: Build the frontend
FROM node:20-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# Stage 2: Serve the application using FastAPI
FROM python:3.11-slim
WORKDIR /app

# Install system dependencies including libpq for PostgreSQL/psycopg
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Copy built frontend assets to the location expected by main.py
COPY --from=frontend-build /app/frontend/dist /app/frontend/dist

# Expose backend port
EXPOSE 8000

# Start script
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
