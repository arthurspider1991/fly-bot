FROM python:3.11-slim

WORKDIR /app

# Fuso de Brasília (slots matinais 05-08h e o job diário das 09h dependem disso).
ENV TZ=America/Sao_Paulo

RUN apt-get update && apt-get install -y \
    wget curl gnupg ca-certificates tzdata \
    libglib2.0-0 libnss3 libnspr4 libdbus-1-3 \
    libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 \
    libxfixes3 libxrandr2 libgbm1 libasound2 \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium
RUN playwright install-deps chromium

COPY . .

CMD ["python", "main.py"]
