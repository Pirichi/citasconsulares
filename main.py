import os
import time
import json
import re
from datetime import datetime
from playwright.sync_api import sync_playwright
import requests

# ====================== CONFIGURACIÓN ======================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
RAW_CHAT_IDS = os.getenv("TELEGRAM_CHAT_ID", "")
TELEGRAM_CHAT_IDS = [cid.strip() for cid in RAW_CHAT_IDS.split(",") if cid.strip()]

CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "180"))  # 3 minutos recomendado

PUBLIC_KEY = "2f9880d8d5b8feb958c81d2a08157bcf1"
SERVICE_ID = "bkt871926"
WIDGET_URL = f"https://www.citaconsular.es/es/hosteds/widgetdefault/{PUBLIC_KEY}/{SERVICE_ID}"

# ===========================================================

def send_telegram(message: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_IDS:
        print("⚠️ Faltan variables de Telegram")
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
                "--disable-infobars",
                "--window-size=1920,1080",
            ]
        )

        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            locale="es-ES",
            viewport={"width": 1920, "height": 1080},
            java_script_enabled=True,
        )

        # Evitar detección básica de automatización
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.chrome = { runtime: {} };
        """)

        page = context.new_page()

        try:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Navegando al widget...")
            page.goto(WIDGET_URL, wait_until="domcontentloaded", timeout=90000)

            # Esperamos a que Cloudflare o el widget carguen
            print("→ Esperando carga del widget / Cloudflare...")
            page.wait_for_timeout(8000)

            # Intentamos detectar si aparece el mensaje de "No hay horas disponibles"
            content = page.content().lower()

            if "no hay horas disponibles" in content or "no hay citas" in content:
                print("→ Página muestra: No hay horas disponibles")
            elif "continuar" in content or "continue" in content:
                print("→ Se detectó botón Continuar / pantalla intermedia")

            # Llamada a la API desde dentro del navegador (aprovecha cookies + CF)
            print("→ Consultando endpoint datetime desde el navegador...")

            api_result = page.evaluate("""
                async () => {
                    try {
                        const url = '/onlinebookings/datetime/?' + new URLSearchParams({
                            callback: '',
                            type: 'default',
                            publickey: '2f9880d8d5b8feb958c81d2a08157bcf1',
                            lang: 'es',
                            'services[]': 'bkt871926',
                            'agendas[]': 'bkt871926',
                            src: window.location.href,
                            start: '2026-08-01',
                            end: '2026-10-31'
                        }).toString();

                        const res = await fetch(url, {
                            method: 'GET',
                            credentials: 'include',
                            headers: {
                                'Accept': 'application/json, text/javascript, */*; q=0.01',
                                'X-Requested-With': 'XMLHttpRequest'
                            }
                        });

                        const text = await res.text();
                        return { status: res.status, length: text.length, body: text };
                    } catch (e) {
                        return { error: e.toString() };
                    }
                }
            """)

            if "error" in api_result:
                print(f"❌ Error en fetch interno: {api_result['error']}")
                return

            print(f"→ Status: {api_result.get('status')} | Longitud: {api_result.get('length')}")

            body = api_result.get("body", "")

            if not body or len(body) < 20:
                print("→ Respuesta vacía o demasiado corta")
                print(f"   Preview: {body[:200]}")
                return

            # Extraer JSON
            match = re.search(r'\{.*\}', body, re.DOTALL)
            if not match:
                print("→ No se encontró JSON en la respuesta")
                print(f"   Preview: {body[:300]}")
                return

            try:
                data = json.loads(match.group(0))
            except Exception as e:
                print(f"→ Error parseando JSON: {e}")
                print(f"   Preview: {body[:300]}")
                return

            # Revisar si hay error del sistema
            if "Exception" in data:
                print(f"→ Error del sistema: {data}")
                return

            available = []
            for slot in data.get("Slots", []):
                if slot.get("times"):
                    available.append({
                        "date": slot.get("date"),
                        "times": slot["times"]
                    })

            if available:
                msg = "🚨 *¡CITAS DISPONIBLES!* 🚨\n\n"
                msg += "*Visado Familiar Comunitario - La Habana*\n\n"
                for s in available[:8]:
                    times = ", ".join(s["times"][:5])
                    msg += f"📅 *{s['date']}* → {times}\n"
                msg += f"\n🔗 {WIDGET_URL}"

                print("🎉 ¡Citas encontradas!")
                send_telegram(msg)
            else:
                print("→ Consulta correcta: No hay citas libres actualmente.")

        except Exception as e:
            print(f"❌ Error general en el navegador: {e}")
        finally:
            browser.close()

def main():
    print("=" * 55)
    print("Monitor Visado Familiar Comunitario - La Habana")
    print("Modo: Playwright + Headless Chromium")
    print(f"Intervalo: {CHECK_INTERVAL} segundos")
    print("=" * 55)

    send_telegram(
        "🤖 *Monitor Playwright activado*\n"
        "Visado Familiar Comunitario - La Habana\n"
        f"Revisando cada {CHECK_INTERVAL} segundos."
    )

    while True:
        try:
            check_with_browser()
        except Exception as e:
            print(f"Error en el ciclo principal: {e}")

        print(f"Esperando {CHECK_INTERVAL} segundos...\n")
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
