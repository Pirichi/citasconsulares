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
            print(f"✅ Notificación enviada a {chat_id}")
        except Exception as e:
            print(f"❌ Error Telegram {chat_id}: {e}")

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
            print(f"[{now_str}] Navegando al sitio...")
            page.goto(WIDGET_URL, wait_until="domcontentloaded", timeout=60000)

            # Esperar a que el contenedor principal del widget exista en el DOM
            page.wait_for_selector("body", timeout=15000)
            
            # Dar tiempo suficiente (10 seg) para que la app SPA de Bookitit descargue el estado de la agenda
            page.wait_for_timeout(10000)

            content = page.content().lower()

            # Textos explícitos de "sin citas"
            no_hay_citas = "no hay horas disponibles" in content or "no hay citas" in content
            
            # Confirmación de que el widget terminó de cargar (debe tener el pie de marca o interfaz)
            widget_cargado = "bookitit" in content or "consulado" in content

            if no_hay_citas:
                print(f"[{now_str}] → Confirmado: No hay citas disponibles actualmente.")
            elif widget_cargado:
                # Si la interfaz cargó pero NO está el texto de "No hay horas", hacemos una pausa breve y re-confirmamos
                page.wait_for_timeout(3000)
                re_check_content = page.content().lower()
                
                if "no hay horas disponibles" not in re_check_content and "no hay citas" not in re_check_content:
                    print(f"[{now_str}] 🎉 ¡ATENCIÓN REAL! Citas detectadas en pantalla.")
                    
                    msg = "🚨 *¡CITAS DISPONIBLES!* 🚨\n\n"
                    msg += "*Visado Familiar Comunitario - La Habana*\n"
                    msg += "Se ha detectado apertura real en la agenda del consulado.\n\n"
                    msg += f"🔗 Entra de inmediato: {WIDGET_URL}"
                    
                    send_telegram(msg)
                else:
                    print(f"[{now_str}] → Falso positivo descartado tras re-verificación.")
            else:
                print(f"[{now_str}] ⚠️ El widget no terminó de renderizar en este ciclo. Reintentando en el próximo.")

        except Exception as e:
            print(f"❌ Error durante el chequeo: {e}")
        finally:
            browser.close()

def main():
    print("=" * 55)
    print("Monitor Visado Familiar Comunitario - La Habana")
    print("Modo: Anti-Falsos Positivos (Doble Verificación)")
    print(f"Intervalo: {CHECK_INTERVAL}s")
    print("=" * 55)

    send_telegram(
        "🤖 *Monitor actualizado (Sin falsos positivos)*\n"
        "Visado Familiar Comunitario - La Habana\n"
        f"Revisando cada {CHECK_INTERVAL} segundos con doble verificación visual."
    )

    while True:
        try:
            check_with_browser()
        except Exception as e:
            print(f"Error en ciclo: {e}")

        print(f"Esperando {CHECK_INTERVAL} segundos...\n")
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
    
