FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

ENV PORT=8000 WEB_CONCURRENCY=2
EXPOSE 8000

# sh -c to expand $PORT, exec so uvicorn becomes PID 1 and receives SIGTERM.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} \
     --workers ${WEB_CONCURRENCY} --loop uvloop --http httptools"]
