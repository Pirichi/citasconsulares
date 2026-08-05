import os
import time
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
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
            print(f"[{now_str}] Iniciando consulta en la web del consulado...")

            # 1. Cargar la página base
            page.goto(WIDGET_URL, wait_until="domcontentloaded", timeout=60000)

            # 2. Esperar contenedor principal
            page.wait_for_selector("body", timeout=20000)

            # 3. Esperar a que Bookitit responda (Tiempo extendido a 35 seg para servidores lentos)
            try:
                page.wait_for_function(
                    """() => {
                        const text = document.body.innerText.toLowerCase();
                        return text.includes('no hay horas disponibles') || 
                               text.includes('no hay citas') || 
                               text.includes('seleccione') || 
                               document.querySelector('.bkt_day, .bkt_slot, input[type="submit"]') !== null;
                    }""",
                    timeout=35000
                )
            except PlaywrightTimeoutError:
                print(f"[{now_str}] ⚠️ La página tardó demasiado en responder este ciclo. Se reintentará en el próximo.")
                return

            # 4. Analizar el contenido
            content_text = page.content().lower()

            no_hay_citas = "no hay horas disponibles" in content_text or "no hay citas" in content_text

            if no_hay_citas:
                print(f"[{now_str}] → Confirmado: No hay citas disponibles actualmente.")
            else:
                print(f"[{now_str}] 🎉 ¡CITAS DETECTADAS EN PANTALLA!")
                
                msg = "🚨 *¡CITAS DISPONIBLES!* 🚨\n\n"
                msg += "*Visado Familiar Comunitario - La Habana*\n"
                msg += "Se ha detectado apertura en la agenda del consulado.\n\n"
                msg += f"🔗 Entra de inmediato a reservar: {WIDGET_URL}"
                
                send_telegram(msg)

        except Exception as e:
            print(f"❌ Error durante la ejecución del navegador: {e}")
        finally:
            browser.close()

def main():
    print("=" * 60)
    print(" Monitor Visado Familiar Comunitario - La Habana")
    print(" Modo: Evaluación Dinámica de DOM (Sin falsos positivos)")
    print(f" Intervalo de chequeo: {CHECK_INTERVAL} segundos")
    print("=" * 60)

    send_telegram(
        "🤖 *Monitor activado y optimizado*\n"
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
    
