import os
import time
from datetime import datetime
from cloakbrowser import launch
import requests

# ====================== CONFIGURACIÓN ======================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
RAW_CHAT_IDS = os.getenv("TELEGRAM_CHAT_ID", "")
TELEGRAM_CHAT_IDS = [cid.strip() for cid in RAW_CHAT_IDS.split(",") if cid.strip()]

CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "120"))

PUBLIC_KEY = "2f9880d8d5b8feb958c81d2a08157bcf1"
SERVICE_ID = "bkt871926"
WIDGET_URL = f"https://www.citaconsular.es/es/hosteds/widgetdefault/{PUBLIC_KEY}/{SERVICE_ID}"

# ===========================================================

def send_telegram(message: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_IDS:
        print("⚠️ Variables de Telegram no configuradas correctamente.")
        return
    for chat_id in TELEGRAM_CHAT_IDS:
        try:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": message,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": True
                },
                timeout=15
            )
            print(f"✅ Notificación enviada a Telegram ({chat_id})")
        except Exception as e:
            print(f"❌ Error al enviar mensaje a Telegram ({chat_id}): {e}")

def check_with_browser():
    # Iniciamos CloakBrowser con su Chromium sigiloso anti-Cloudflare
    browser = launch(headless=True)
    page = browser.new_page()

    try:
        now_str = datetime.now().strftime('%H:%M:%S')
        print(f"[{now_str}] Iniciando consulta con CloakBrowser...")

        # Navegación superando los filtros de Cloudflare
        page.goto(WIDGET_URL, wait_until="networkidle", timeout=45000)
        page.wait_for_timeout(3000)

        # Extracción de contenido global incluyendo iframes
        full_content = page.content().lower()
        for frame in page.frames:
            try:
                full_content += " " + frame.content().lower()
            except Exception:
                pass

        no_hay_citas = "no hay horas disponibles" in full_content or "no hay citas" in full_content
        widget_presente = "bookitit" in full_content or "consulado" in full_content

        if no_hay_citas:
            print(f"[{now_str}] → Confirmado: No hay citas disponibles actualmente.")
        elif widget_presente:
            print(f"[{now_str}] 🎉 ¡CITAS DETECTADAS EN PANTALLA!")
            
            msg = "🚨 *¡CITAS DISPONIBLES!* 🚨\n\n"
            msg += "*Visado Familiar Comunitario - La Habana*\n"
            msg += "Se ha detectado apertura en la agenda del consulado.\n\n"
            msg += f"🔗 Entra de inmediato a reservar: {WIDGET_URL}"
            
            send_telegram(msg)
        else:
            print(f"[{now_str}] ⚠️ Posible bloqueo de Cloudflare o estructura no reconocida. Reintentando...")

    except Exception as e:
        print(f"❌ Error durante la ejecución del navegador stealth: {e}")
    finally:
        browser.close()

def main():
    print("=" * 60)
    print(" Monitor Visado Familiar Comunitario - La Habana")
    print(" Modo: CloakBrowser Stealth Anti-Cloudflare")
    print(f" Intervalo de chequeo: {CHECK_INTERVAL} segundos")
    print("=" * 60)

    send_telegram(
        "🤖 *Monitor con CloakBrowser Activo*\n"
        "Visado Familiar Comunitario - La Habana\n"
        f"Revisando agenda cada {CHECK_INTERVAL} segundos."
    )

    while True:
        try:
            check_with_browser()
        except Exception as e:
            print(f"Error en el bucle principal: {e}")

        print(f"Esperando {CHECK_INTERVAL} segundos para la siguiente revisión...\n")
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
    
