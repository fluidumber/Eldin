FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY provider_app /app/provider_app
ENV PYTHONPATH=/app

# Create data dir (mounted by compose) and ensure index
RUN mkdir -p /app/data && mkdir -p /app/provider_app

EXPOSE 8001
CMD ["uvicorn", "provider_app.main:app", "--host", "0.0.0.0", "--port", "8001"]