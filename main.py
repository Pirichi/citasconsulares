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

    # Forzar el renderizado JS desde proxy residencial en España
    payload = {
        'api_key': SCRAPER_API_KEY,
        'url': URL_CONSULADO,
        'country_code': 'es',
        'render': 'true'
    }

    try:
        # Timeout de 90s para darle margen al navegador en la nube de ScraperAPI
        response = requests.get('https://api.scraperapi.com', params=payload, timeout=90)
        
        # Ignorar fallos temporales de servidor o timeouts de ScraperAPI
        if response.status_code in [500, 502, 503, 504]:
            print(f"Servidor ocupado o reintento de proxy (HTTP {response.status_code}). Reintentando en el próximo ciclo...")
            return

        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, "html.parser")
        page_text = soup.get_text().lower()
        
        # Evaluación de los textos de indisponibilidad
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
        print(f"Reintento de conexión en el próximo ciclo: {e}")

def main():
    print("Iniciando monitor de citas con ScraperAPI (Proxy España + JS Render)...")
    send_telegram_notification("🤖 **Monitor de citas activado en Railway.** Conexiones ruteadas desde España 🇪🇸.")
    
    while True:
        check_appointments()
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
        
