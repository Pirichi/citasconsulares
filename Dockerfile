FROM python:3.10-slim

# Instalar dependencias del sistema esenciales para Chromium / Playwright / CloakBrowser
RUN apt-get update && apt-get install -y \
    wget \
    curl \
    ca-certificates \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libgobject-2.0-0 \
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    libx11-6 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpangoft2-1.0-0 \
    libpangocairo-1.0-0 \
    libxss1 \
    libxtst6 \
    libxkbcommon0 \
    fonts-liberation \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]
