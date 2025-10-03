# backend.Dockerfile
FROM python:3.11-slim

WORKDIR /app

# 1) install dependencies
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# 2) copy the backend code (relative to backend/ root)
COPY . /app

# 3) runtime
ENV PORT=8000
EXPOSE 8000

# 4) start
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
