import os
import time
import requests
from bs4 import BeautifulSoup

# Variables de entorno (se configuran en el panel de Railway)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
URL_CONSULADO = os.getenv("TARGET_URL", "https://citaconsular.es/")

# Intervalo de verificación en segundos (ejemplo: 60 segundos para ser respetuosos con el servidor)
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "60"))

def send_telegram_notification(message):
    """Envía un mensaje a tu chat de Telegram a través del Bot API."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
    except Exception as e:
        print(f"Error enviando mensaje a Telegram: {e}")

def check_appointments():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        response = requests.get(URL_CONSULADO, headers=headers, timeout=15)
        
        # Si el servidor responde con error 502/503 (muy común), simplemente omitimos el ciclo
        if response.status_code in [502, 503, 504]:
            print(f"Servidor saturado (HTTP {response.status_code}). Reintentando en el próximo ciclo...")
            return

        response.raise_for_status()
        
        # Análisis del contenido
        soup = BeautifulSoup(response.text, "html.parser")
        
        # Criterio de búsqueda: Verificamos si la frase típica de "no hay citas" NO está presente
        # O buscamos elementos que indiquen la presencia de un calendario activo
        page_text = soup.get_text().lower()
        
        if "no hay citas disponibles" not in page_text and "no existen huecos" not in page_text:
            msg = (
                "🚨 **¡POSIBLE CITA DISPONIBLE!** 🚨\n\n"
                "El sistema del Consulado muestra cambios o disponibilidad.\n"
                f"Entra de inmediato aquí: {URL_CONSULADO}"
            )
            print("¡Cita detectada! Enviando notificación...")
            send_telegram_notification(msg)
        else:
            print("Sin citas disponibles por el momento.")

    except requests.exceptions.RequestException as e:
        print(f"Error de red/conexión: {e}")

def main():
    print("Iniciando monitor de citas...")
    send_telegram_notification("🤖 **Monitor de citas activado en Railway.** Te avisaré en cuanto haya cambios.")
    
    while True:
        check_appointments()
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
  
