FROM mcr.microsoft.com/playwright/python:v1.62.0-jammy

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Instalar el navegador (ya está en la imagen, pero por si acaso)
RUN python -m playwright install chromium

COPY . .

ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
ENV PYTHONUNBUFFERED=1

RUN mkdir -p /app/browser-profile && chmod 777 /app/browser-profile

CMD ["python", "main.py"]
