FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    AUTO_INSTALL_DEPENDENCIES=0

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Persistent database: attach a Railway Volume at mount path /data
# (Railway -> service -> Settings -> Volumes -> Add Volume -> /data)
ENV BOT_DATABASE_PATH=/data/casino.db

# Bot runs alongside the Mini App server in one container.
CMD ["sh", "-c", "python casino_bot.py & exec uvicorn miniapp:app --host 0.0.0.0 --port ${PORT:-8000}"]
