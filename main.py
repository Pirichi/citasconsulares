import os
import time
import requests
from bs4 import BeautifulSoup

# Variables de entorno
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
# Obtenemos la cadena de IDs y la dividimos por comas en una lista de cadenas
RAW_CHAT_IDS = os.getenv("TELEGRAM_CHAT_ID", "")
TELEGRAM_CHAT_IDS = [chat_id.strip() for chat_id in RAW_CHAT_IDS.split(",") if chat_id.strip()]

URL_CONSULADO = os.getenv("TARGET_URL", "https://www.citaconsular.es/")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "60"))

def send_telegram_notification(message):
    """Envía el mensaje a todos los Chat IDs configurados en la variable de entorno."""
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
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        response = requests.get(URL_CONSULADO, headers=headers, timeout=15)
        
        # Omitir el ciclo si el servidor del consulado está saturado/caído
        if response.status_code in [502, 503, 504]:
            print(f"Servidor saturado (HTTP {response.status_code}). Reintentando en el próximo ciclo...")
            return

        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, "html.parser")
        page_text = soup.get_text().lower()
        
        # Verificamos si las frases habituales de indisponibilidad NO están en el texto
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
        print(f"Error de red/conexión: {e}")

def main():
    print("Iniciando monitor de citas multiusuario...")
    send_telegram_notification("🤖 **Monitor de citas activado en Railway.** Te avisaré en cuanto haya cambios.")
    
    while True:
        check_appointments()
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
    
