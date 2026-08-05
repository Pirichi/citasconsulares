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
    print("Iniciando ciclo con CloakBrowser...", flush=True)
    
    browser = None
    try:
        # Lanzamos el navegador sigiloso con timeout estricto
        browser = launch(
            headless=True,
            humanize=True,
            human_preset="careful",
            geoip=False
        )
        
        page = browser.new_page()
        
        # Aceptar automáticamente cualquier alerta nativa de JavaScript
        page.on("dialog", lambda dialog: dialog.accept())
        
        print(f"Navegando a: {WIDGET_URL}", flush=True)
        page.goto(WIDGET_URL, wait_until="domcontentloaded", timeout=35000)
        
        # Breve pausa para que el widget renderice sus scripts internos
        page.wait_for_timeout(4000)
        
        # Intentar clic en el botón de continuar si aparece la pantalla intermedia
        body_inicial = page.inner_text("body").lower()
        if "continuar" in body_inicial or "continue" in body_inicial:
            print("Pantalla intermedia detectada, haciendo clic...", flush=True)
            try:
                page.click("text=Continuar", timeout=3000)
            except Exception:
                try:
                    page.click("text=Continue", timeout=3000)
                except Exception:
                    pass
            page.wait_for_timeout(4000)

        body_text = page.inner_text("body").lower()
        
        textos_sin_citas = [
            "no hay horas disponibles",
            "no hay citas",
            "no disponemos de citas",
            "en este momento no hay",
            "próximamente se abrirán",
            "completo",
            "inténtelo de nuevo dentro de unos días"
        ]
        
        # Detección de Cloudflare o bloqueos visuales
        if "cf-browser-verification" in body_text or "challenge-running" in body_text or "robot" in body_text:
            print("⚠️ Cloudflare o desafío detectado en la interfaz.", flush=True)
            enviar_telegram("⚠️ *Cloudflare / Captcha detectado* en el widget consular.")
        else:
            sin_cupos = any(frase in body_text for frase in textos_sin_citas)
            
            if not sin_cupos:
                # Doble validación para confirmar que hay elementos de calendario y no una página vacía
                if len(body_text) > 100 and any(p in body_text for p in ["calendario", "horario", "mes", "dia", "cita", "servicio"]):
                    print("🚨 ¡POSIBLES CITAS O CAMBIOS DETECTADOS!", flush=True)
                    enviar_telegram(
                        "🚨 *¡ATENCIÓN PEDRY!* 🚨\n"
                        "¡La agenda avanzó y muestra elementos activos!\n"
                        f"[Enlace directo a la agenda]({WIDGET_URL})"
                    )
                else:
                    print("Página en transición o sin confirmar calendario.", flush=True)
            else:
                print("Sin citas disponibles por el momento. Todo normal.", flush=True)

    except Exception as e:
        print(f"Error durante el ciclo con navegador: {e}", flush=True)
        
    finally:
        if browser:
            try:
                browser.close()
                print("Navegador cerrado correctamente.", flush=True)
            except Exception:
                pass

def main():
    print("=== MONITOR CLOAKBROWSER SEGURO ===", flush=True)
    print(f"Intervalo configurado: {CHECK_INTERVAL} segundos.", flush=True)
    
    enviar_telegram(
        "🤖 *Monitor CloakBrowser Activo*\n"
        "Visado Familiar Comunitario - La Habana\n"
        f"Revisando agenda cada {CHECK_INTERVAL} segundos."
    )
    
    while True:
        revisar_citas()
        print(f"Ciclo completado. Esperando {CHECK_INTERVAL} segundos...\n", flush=True)
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
    
