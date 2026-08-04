import os
import time
import json
import re
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright
import requests

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
                "--window-size=1280,720",
            ]
        )

        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            locale="es-ES",
            viewport={"width": 1280, "height": 720},
        )

        # Stealth básico
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)

        page = context.new_page()

        try:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Navegando al widget...")
            page.goto(WIDGET_URL, wait_until="domcontentloaded", timeout=90000)
            page.wait_for_timeout(6000)

            # --- Intentamos hacer clic en "Continuar" si aparece ---
            print("→ Buscando botón Continuar...")
            clicked = False
            for selector in [
                "text=Continuar",
                "text=Continue",
                "button:has-text('Continuar')",
                "button:has-text('Continue')",
                "a:has-text('Continuar')",
                "input[value*='Continuar']",
                "input[value*='Continue']",
            ]:
                try:
                    btn = page.locator(selector).first
                    if btn.is_visible(timeout=3000):
                        btn.click(timeout=5000)
                        print(f"→ Clic en botón: {selector}")
                        clicked = True
                        page.wait_for_timeout(7000)
                        break
                except:
                    continue

            if not clicked:
                print("→ No se encontró botón Continuar (puede que ya esté dentro)")

            # Esperamos un poco más a que cargue el contenido del widget
            page.wait_for_timeout(5000)

            content = page.content().lower()
            if "no hay horas disponibles" in content:
                print("→ La página muestra: No hay horas disponibles")
            elif "no hay citas" in content:
                print("→ La página muestra: No hay citas")

            # --- Consulta a la API desde dentro del navegador ---
            print("→ Consultando disponibilidad...")

            # Calculamos rango de fechas (hoy + 90 días)
            start_date = datetime.now().strftime("%Y-%m-%d")
            end_date = (datetime.now() + timedelta(days=90)).strftime("%Y-%m-%d")

            result = page.evaluate(f"""
                async () => {{
                    try {{
                        const params = new URLSearchParams({{
                            callback: '',
                            type: 'default',
                            publickey: '{PUBLIC_KEY}',
                            lang: 'es',
                            'services[]': '{SERVICE_ID}',
                            'agendas[]': '{SERVICE_ID}',
                            src: window.location.href,
                            start: '{start_date}',
                            end: '{end_date}'
                        }});

                        const res = await fetch('/onlinebookings/datetime/?' + params.toString(), {{
                            method: 'GET',
                            credentials: 'include',
                            headers: {{
                                'Accept': 'application/json, text/javascript, */*; q=0.01',
                                'X-Requested-With': 'XMLHttpRequest',
                                'Referer': window.location.href
                            }}
                        }});

                        const text = await res.text();
                        return {{
                            status: res.status,
                            length: text.length,
                            body: text.substring(0, 2000)
                        }};
                    }} catch (err) {{
                        return {{ error: err.toString() }};
                    }}
                }}
            """)

            if "error" in result:
                print(f"❌ Error en fetch: {result['error']}")
                return

            print(f"→ Status: {result.get('status')} | Longitud: {result.get('length')}")

            body = result.get("body", "")
            if not body or len(body) < 30:
                print("→ Respuesta vacía")
                print(f"   Preview: {body[:300] if body else 'vacío'}")
                return

            # Extraer JSON
            match = re.search(r'\{.*\}', body, re.DOTALL)
            if not match:
                print("→ No se encontró JSON válido")
                print(f"   Preview: {body[:400]}")
                return

            try:
                data = json.loads(match.group(0))
            except Exception as e:
                print(f"→ Error parseando JSON: {e}")
                print(f"   Preview: {body[:400]}")
                return

            if "Exception" in str(data):
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
                print("→ No hay citas disponibles en este momento.")

        except Exception as e:
            print(f"❌ Error general: {e}")
        finally:
            browser.close()

def main():
    print("=" * 55)
    print("Monitor Visado Familiar Comunitario - La Habana")
    print("Modo: Playwright + Clic en Continuar")
    print(f"Intervalo: {CHECK_INTERVAL}s")
    print("=" * 55)

    send_telegram(
        "🤖 *Monitor actualizado*\n"
        "Visado Familiar Comunitario - La Habana\n"
        "Ahora intenta hacer clic en Continuar automáticamente."
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
