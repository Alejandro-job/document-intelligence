FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-spa && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY core ./core
COPY ui ./ui
RUN mkdir /app/runtime_data && chown -R 10001:10001 /app/runtime_data
USER 10001:10001
EXPOSE 8000
CMD ["python", "app/server.py", "--host", "0.0.0.0", "--data", "/app/runtime_data"]
