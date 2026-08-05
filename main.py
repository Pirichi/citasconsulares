import os
import time
from datetime import datetime
from playwright.sync_api import sync_playwright
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
        print("⚠️ Variables de Telegram no configuradas.")
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
            print(f"❌ Error Telegram ({chat_id}): {e}")

def check_with_browser():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ]
        )

        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            locale="es-ES",
            viewport={"width": 1280, "height": 720},
        )

        context.add_init_script("Object.defineProperty(navigator, 'webdriver', { get: () => undefined });")
        page = context.new_page()

        try:
            now_str = datetime.now().strftime('%H:%M:%S')
            print(f"[{now_str}] Iniciando consulta...")

            # Usamos domcontentloaded en vez de networkidle (evita el timeout)
            page.goto(WIDGET_URL, wait_until="domcontentloaded", timeout=60000)

            # Esperamos a que el widget termine de renderizar
            page.wait_for_timeout(8000)

            # Extraemos contenido de la página + iframes
            full_content = page.content().lower()

            for frame in page.frames:
                try:
                    full_content += " " + frame.content().lower()
                except:
                    pass

            # Comprobaciones
            no_hay_citas = any(x in full_content for x in [
                "no hay horas disponibles",
                "no hay citas disponibles",
                "no existen huecos",
                "no hay citas"
            ])

            tiene_calendario = any(x in full_content for x in [
                "seleccione fecha",
                "selecciona una fecha",
                "horario disponible",
                "elige fecha",
                "bookitit"
            ])

            if no_hay_citas:
                print(f"[{now_str}] → No hay citas disponibles.")
            elif tiene_calendario or "continuar" in full_content:
                # Puede haber citas o estar en pantalla intermedia
                print(f"[{now_str}] ⚠️ Posible cambio detectado en la página")
                
                # Solo alertamos si claramente NO dice que no hay citas
                if not no_hay_citas:
                    msg = (
                        "🚨 *¡POSIBLE CITA DISPONIBLE!* 🚨\n\n"
                        "*Visado Familiar Comunitario - La Habana*\n"
                        "Se detectó un cambio en la agenda del consulado.\n\n"
                        f"🔗 Entra rápido: {WIDGET_URL}"
                    )
                    send_telegram(msg)
                    print(f"[{now_str}] 🎉 Alerta enviada")
            else:
                print(f"[{now_str}] → Estado no claro / página cargando...")

        except Exception as e:
            print(f"❌ Error: {e}")
        finally:
            browser.close()

def main():
    print("=" * 55)
    print("Monitor Visado Familiar Comunitario - La Habana")
    print("Modo: domcontentloaded + análisis de contenido")
    print(f"Intervalo: {CHECK_INTERVAL}s")
    print("=" * 55)

    send_telegram(
        "🤖 *Monitor actualizado*\n"
        "Visado Familiar Comunitario - La Habana\n"
        f"Revisando cada {CHECK_INTERVAL} segundos."
    )

    while True:
        try:
            check_with_browser()
        except Exception as e:
            print(f"Error en bucle: {e}")

        print(f"Esperando {CHECK_INTERVAL} segundos...\n")
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
