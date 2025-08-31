FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY gateway_app /app/gateway_app
ENV PYTHONPATH=/app

RUN mkdir -p /app/data/logs

EXPOSE 8000
CMD ["uvicorn", "gateway_app.main:app", "--host", "0.0.0.0", "--port", "8000"]