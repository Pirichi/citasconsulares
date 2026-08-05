import time
import os
import requests
from cloakbrowser import launch

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", 60))

PUBLIC_KEY = "2f9880d8d5b8feb958c81d2a08157bcf1"
SERVICE_ID = "bkt871926"
WIDGET_URL = f"https://www.citaconsular.es/es/hosteds/widgetdefault/{PUBLIC_KEY}/{SERVICE_ID}"

def enviar_telegram(mensaje):
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": mensaje, "parse_mode": "Markdown"}
        try:
            requests.post(url, json=payload, timeout=10)
        except Exception as e:
            print(f"Error al enviar Telegram: {e}", flush=True)

def revisar_citas():
    print("--------------------------------------------------", flush=True)
    print("Iniciando revisión con espera de elementos...", flush=True)
    
    browser = None
    try:
        browser = launch(
            headless=True,
            humanize=True,
            human_preset="careful",
            geoip=False
        )
        
        page = browser.new_page()
        page.on("dialog", lambda dialog: dialog.accept())
        
        page.goto(WIDGET_URL, wait_until="domcontentloaded", timeout=35000)
        
        # Esperar obligatoriamente a que aparezca el contenedor del texto para asegurar que cargó
        try:
            page.wait_for_selector("text=No hay horas disponibles", timeout=10000)
            print("Texto de cierre detectado correctamente en la página.", flush=True)
            sigues_cerrado = True
        except Exception:
            sigues_cerrado = False

        body_text = page.inner_text("body").lower()
        print(f"Muestra de texto leída: {body_text[:120]}...", flush=True)
        
        if sigues_cerrado or "no hay horas disponibles" in body_text:
            print("Estado normal: La agenda sigue cerrada.", flush=True)
        else:
            print("🚨 ¡EL CARTEL DE CIERRE DESAPARECIÓ DE VERDAD!", flush=True)
            enviar_telegram(
                "🚨 *¡ATENCIÓN PEDRY! ¡LA AGENDA CAMBIÓ!* 🚨\n"
                "¡El aviso oficial ya no está en el DOM!\n"
                f"[Enlace directo a la agenda]({WIDGET_URL})"
            )

    except Exception as e:
        print(f"Error durante el ciclo: {e}", flush=True)
        
    finally:
        if browser:
            try:
                browser.close()
            except Exception:
                pass

def main():
    print("=== MONITOR DE CITAS (ESPERA EXPLÍCITA) ===", flush=True)
    print(f"Intervalo configurado: {CHECK_INTERVAL} segundos.", flush=True)
    
    while True:
        revisar_citas()
        print(f"Ciclo completado. Esperando {CHECK_INTERVAL} segundos...\n", flush=True)
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
    
