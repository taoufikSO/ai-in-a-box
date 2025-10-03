# frontend.Dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY frontend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY frontend /app
# Streamlit default port 8501
EXPOSE 8501
ENV PYTHONUNBUFFERED=1

CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501"]
