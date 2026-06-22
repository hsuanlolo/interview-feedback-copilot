FROM python:3.11-slim

WORKDIR /app

# Build context is the repo root, so backend/ is referenced explicitly
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .

# parents[3] from /app/app/routers/*.py resolves to /  — copy sample_data there
COPY sample_data /sample_data

ENV PYTHONPATH=/app

CMD ["sh", "-c", "python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT"]
