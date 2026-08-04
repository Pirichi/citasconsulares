import os
import time
import json
import requests
from datetime import datetime
from playwright.sync_api import sync_playwright

# ====================== CONFIGURACIÓN ======================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
RAW_CHAT_IDS = os.getenv("TELEGRAM_CHAT_ID", "")
TELEGRAM_CHAT_IDS = [cid.strip() for cid in RAW_CHAT_IDS.split(",") if cid.strip()]

CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "180"))

PUBLIC_KEY = "2f9880d8d5b8feb958c81d2a08157bcf1"
SERVICE_ID = "bkt871926"
WIDGET_URL = f"https://www.citaconsular.es/es/hosteds/widgetdefault/{PUBLIC_KEY}/{SERVICE_ID}"

# ===========================================================

def send_telegram(message: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_IDS:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    for chat_id in TELEGRAM_CHAT_IDS:
        try:
            requests.post(url, json={
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True
            }, timeout=12)
            print(f"✅ Notificación enviada a {chat_id}")
        except Exception as e:
            print(f"❌ Error Telegram ID {chat_id}: {e}")

def check_with_browser():
    with sync_playwright() as p:
        # Lanzamos navegador Headless en Linux
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            locale="es-ES"
        )
        page = context.new_page()

        print(f"[{datetime.now().strftime('%H:%M:%S')}] Navegando al widget...")
        page.goto(WIDGET_URL, wait_until="networkidle", timeout=60000)

        # Esperamos unos segundos por si salta la pantalla intermedia de Cloudflare
        time.sleep(5)

        # Verificamos si la página cargó el aviso de "No hay horas disponibles" o el botón Continuar
        content = page.content()

        # Ejecutamos la llamada a la API internamente dentro del navegador
        # aprovechando las cookies y tokens ya validados por Cloudflare
        api_script = """
        async () => {
            const res = await fetch('/onlinebookings/datetime/?publickey=2f9880d8d5b8feb958c81d2a08157bcf1&lang=es&type=default&services[]=bkt871926');
            return await res.text();
        }
        """
        try:
            response_text = page.evaluate(api_script)
            print(f"→ Respuesta obtenida (Longitud: {len(response_text)})")

            if "Slots" in response_text:
                start = response_text.find("{")
                end = response_text.rfind("}") + 1
                data = json.loads(response_text[start:end])
                
                available = []
                for slot in data.get("Slots", []):
                    if slot.get("times"):
                        available.append({
                            "date": slot.get("date"),
                            "times": slot["times"]
                        })
                
                if available:
                    msg = "🚨 *¡CITAS DISPONIBLES!* 🚨\n\n*Visado Familiar Comunitario - La Habana*\n\n"
                    for s in available[:8]:
                        msg += f"📅 *{s['date']}* → {', '.join(s['times'][:5])}\n"
                    msg += f"\n🔗 {WIDGET_URL}"
                    print("🎉 ¡Citas encontradas!")
                    send_telegram(msg)
                else:
                    print("→ Consulta correcta: No hay citas libres en este momento.")
            else:
                print("→ No se detectaron huecos disponibles en la respuesta.")

        except Exception as err:
            print(f"❌ Error al consultar API desde el navegador: {err}")

        browser.close()

def main():
    print("=" * 55)
    print("Monitor Visado Habana - Modo Playwright Browser")
    print(f"Intervalo: {CHECK_INTERVAL}s")
    print("=" * 55)

    send_telegram("🤖 *Monitor Playwright Activado*\nVerificación mediante navegador real.")

    while True:
        try:
            check_with_browser()
        except Exception as e:
            print(f"Error en ciclo de navegación: {e}")
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
        
