FROM mcr.microsoft.com/playwright/python:v1.62.0-jammy

WORKDIR /app

# Instalar Flask y Playwright (ya viene en la imagen, pero por si acaso)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Instalar el navegador (necesario para Playwright)
RUN python -m playwright install chromium

# Copiar todos los archivos del proyecto
COPY . .

# Exponer el puerto que usará Flask
EXPOSE 5000

# Comando para iniciar el servidor de generación de sesión
CMD ["python", "generate_session.py"]
