import os
import time
import requests
from bs4 import BeautifulSoup

# Variables de entorno
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
RAW_CHAT_IDS = os.getenv("TELEGRAM_CHAT_ID", "")
TELEGRAM_CHAT_IDS = [chat_id.strip() for chat_id in RAW_CHAT_IDS.split(",") if chat_id.strip()]

URL_CONSULADO = os.getenv("TARGET_URL", "https://www.citaconsular.es/")
SCRAPER_API_KEY = os.getenv("SCRAPER_API_KEY")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "60"))

def send_telegram_notification(message):
    """Envía el mensaje a todos los Chat IDs configurados en Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_IDS:
        print("Error: TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID no están configurados correctamente.")
        return

    for chat_id in TELEGRAM_CHAT_IDS:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "Markdown"
        }
        try:
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            print(f"Notificación enviada con éxito a ID: {chat_id}")
        except Exception as e:
            print(f"Error enviando mensaje a Telegram ID {chat_id}: {e}")

def check_appointments():
    if not SCRAPER_API_KEY:
        print("Error: La variable SCRAPER_API_KEY no está configurada en Railway.")
        return

    # Parámetros para enviar la petición desde una IP de España usando ScraperAPI
    payload = {
        'api_key': SCRAPER_API_KEY,
        'url': URL_CONSULADO,
        'country_code': 'es'
    }

    try:
        # Petición a la API de ScraperAPI
        response = requests.get('http://api.scraperapi.com', params=payload, timeout=30)
        
        # Omitir el ciclo si el servidor del consulado está saturado/caído
        if response.status_code in [502, 503, 504]:
            print(f"Servidor del consulado saturado (HTTP {response.status_code}). Reintentando en el próximo ciclo...")
            return

        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, "html.parser")
        page_text = soup.get_text().lower()
        
        # Verificación de disponibilidad de citas
        if "no hay citas disponibles" not in page_text and "no existen huecos" not in page_text:
            msg = (
                "🚨 **¡POSIBLE CITA DISPONIBLE!** 🚨\n\n"
                "El sistema del Consulado muestra cambios o disponibilidad.\n"
                f"Entra de inmediato aquí: {URL_CONSULADO}"
            )
            print("¡Cita detectada! Enviando alertas a Telegram...")
            send_telegram_notification(msg)
        else:
            print("Sin citas disponibles por el momento.")

    except requests.exceptions.RequestException as e:
        print(f"Error al consultar la página a través de ScraperAPI: {e}")

def main():
    print("Iniciando monitor de citas con ScraperAPI (Proxy España)...")
    send_telegram_notification("🤖 **Monitor de citas activado en Railway.** Peticiones ruteadas desde España 🇪🇸.")
    
    while True:
        check_appointments()
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
            
