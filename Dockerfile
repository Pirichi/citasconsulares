FROM python:3.10-slim

# Permitir instalación de fuentes propietarias sin interacción
ENV DEBIAN_FRONTEND=noninteractive

# Instalar dependencias esenciales y fuentes de Microsoft para spoofing perfecto
RUN apt-get update && apt-get install -y \
    wget \
    curl \
    gnupg \
    fontconfig \
    ttf-mscorefonts-installer \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libc6 \
    libstdc++6 \
    && fc-cache -f -v \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copiar e instalar las dependencias de Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el código del proyecto al contenedor
COPY . .

# Comando para ejecutar el script de monitoreo
CMD ["python", "main.py"]
