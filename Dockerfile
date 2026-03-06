FROM python:3.11-slim

# Chromium from Debian repos — lighter than full Chrome, no special repos needed
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p instance static/uploads

CMD ["bash", "start.sh"]
