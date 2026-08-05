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
    print("Iniciando revisión de la agenda consular...", flush=True)
    
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
        page.wait_for_timeout(4000)

        body_text = page.inner_text("body").lower()
        
        # El texto exacto que aparece cuando está cerrado según tu captura
        frase_cierre = "no hay horas disponibles"
        
        # Validamos si la página cargó correctamente y contiene elementos
        if len(body_text) < 50:
            print("Página vacía o error de carga momentáneo. Ignorando.", flush=True)
            return

        # CONDICIÓN DE ORO: ¿Sigue estando el aviso de que no hay horas?
        if frase_cierre in body_text:
            print("Estado normal: La agenda sigue cerrada ('No hay horas disponibles').", flush=True)
        else:
            # ¡OJO! ¡El texto de cierre desapareció! La página cambió de estado.
            print("🚨 ¡EL AVISO DE CIERRE DESAPARECIÓ! ¡POSIBLE APERTURA!", flush=True)
            enviar_telegram(
                "🚨 *¡ATENCIÓN PEDRY! ¡LA AGENDA CAMBIÓ!* 🚨\n"
                "¡El aviso de 'No hay horas disponibles' ya no está en la pantalla!\n"
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
    print("=== MONITOR DE CITAS (MODO ANTI-SPAM) ===", flush=True)
    print(f"Intervalo configurado: {CHECK_INTERVAL} segundos.", flush=True)
    
    enviar_telegram(
        "🤖 *Monitor Antispam Activo*\n"
        "Visado Familiar Comunitario - La Habana\n"
        "Silencioso hasta que la agenda abra de verdad."
    )
    
    while True:
        revisar_citas()
        print(f"Ciclo completado. Esperando {CHECK_INTERVAL} segundos...\n", flush=True)
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
    
