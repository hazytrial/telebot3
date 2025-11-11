FROM python:3.11.9-slim

WORKDIR /app
COPY . /app

RUN apt-get update && apt-get install -y ffmpeg && \
    pip install --no-cache-dir -r requirements.txt

ENV PORT=5000
CMD ["python", "bot.py"]
