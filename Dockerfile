FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

WORKDIR /app

# Instalar solo lo necesario
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el código
COPY . .

# Variables para que Playwright funcione mejor en contenedor
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
ENV PYTHONUNBUFFERED=1

CMD ["python", "main.py"]
