FROM mcr.microsoft.com/playwright/python:v1.62.0-jammy

WORKDIR /app

# Instalar dependencias del sistema adicionales (por si acaso)
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Instalar el navegador para CloakBrowser (usa el mismo que Playwright)
RUN python -m playwright install chromium

COPY . .

ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
ENV PYTHONUNBUFFERED=1

CMD ["python", "main.py"]
