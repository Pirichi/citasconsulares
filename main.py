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
    print("Iniciando ciclo de sondeo...", flush=True)
    
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
        page.wait_for_timeout(8000)
        
        # Obtenemos todo el contenido de la página incluyendo marcos si existen
        contenido_total = ""
        try:
            for frame in page.frames:
                contenido_total += " " + frame.inner_text("body").lower()
        except Exception:
            pass
            
        # Respaldo con el body principal si los frames fallan
        contenido_total += " " + page.inner_text("body").lower()

        # 1. Si aparece Cloudflare, lo ignoramos amablemente sin disparar alarmas
        if "security service" in contenido_total or "performing security verification" in contenido_total or "cf-browser-verification" in contenido_total:
            print("🛡️ Cloudflare activo en la pasarela. Omitiendo ciclo.", flush=True)
            return

        # 2. Verificamos la presencia del texto de cierre oficial
        if "no hay horas disponibles" in contenido_total:
            print("Estado normal: La agenda sigue cerrada.", flush=True)
        else:
            if len(contenido_total.strip()) > 50:
                print("🚨 ¡EL CARTEL DE CIERRE DESAPARECIÓ DE LA AGENDA!", flush=True)
                enviar_telegram(
                    "🚨 *¡ATENCIÓN PEDRY! ¡LA AGENDA CAMBIÓ!* 🚨\n"
                    "¡El widget ya no muestra el aviso de cierre!\n"
                    f"[Enlace directo a la agenda]({WIDGET_URL})"
                )
            else:
                print("Página en blanco o cargando. Omitiendo.", flush=True)

    except Exception as e:
        print(f"Error durante el ciclo: {e}", flush=True)
        
    finally:
        if browser:
            try:
                browser.close()
            except Exception:
                pass

def main():
    print("=== MONITOR DE CITAS DEFINITIVO ===", flush=True)
    print(f"Intervalo configurado: {CHECK_INTERVAL} segundos.", flush=True)
    
    while True:
        revisar_citas()
        print(f"Ciclo completado. Esperando {CHECK_INTERVAL} segundos...\n", flush=True)
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
    
