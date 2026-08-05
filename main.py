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
            response = requests.post(url, json=payload, timeout=10)
            if not response.ok:
                print(f"Error al enviar Telegram: {response.text}", flush=True)
        except Exception as e:
            print(f"Excepción al conectar con Telegram: {e}", flush=True)

def revisar_citas():
    print("--------------------------------------------------", flush=True)
    print("Iniciando ciclo de revisión con CloakBrowser...", flush=True)
    
    browser = None
    try:
        print("Lanzando navegador sigiloso...", flush=True)
        browser = launch(
            headless=True,
            humanize=True,
            human_preset="careful",
            geoip=False
        )
        
        print("Abriendo nueva pestaña...", flush=True)
        page = browser.new_page()
        
        # Manejador automático de alertas de JavaScript
        page.on("dialog", lambda dialog: dialog.accept())
        
        print(f"Navegando hacia la URL de la agenda...", flush=True)
        # Forzamos un timeout estricto de 30 segundos para que no se quede congelado nunca
        page.goto(WIDGET_URL, wait_until="domcontentloaded", timeout=30000)
        
        print("Página alcanzada. Esperando renderizado de elementos...", flush=True)
        page.wait_for_timeout(4000)

        # Verificar contenido actual del DOM
        body_text = page.inner_text("body").lower()
        print(f"Texto extraído correctamente (Longitud: {len(body_text)} caracteres).", flush=True)
        
        textos_sin_citas = [
            "no hay horas disponibles",
            "no hay citas",
            "no disponemos de citas",
            "en este momento no hay",
            "próximamente se abrirán",
            "completo",
            "inténtelo de nuevo dentro de unos días"
        ]
        
        if "cf-browser-verification" in body_text or "challenge-running" in body_text:
            print("⚠️ Cloudflare interceptó la conexión en este ciclo.", flush=True)
            enviar_telegram("⚠️ *Cloudflare* ha interceptado la consulta en este ciclo.")
        else:
            sin_cupos = any(frase in body_text for frase in textos_sin_citas)
            
            if not sin_cupos:
                print("🚨 ¡POSIBLE CAMBIO O CITAS DETECTADAS!", flush=True)
                enviar_telegram(
                    "🚨 *¡ATENCIÓN PEDRY!* 🚨\n"
                    "¡La página avanzó y ya no dice que no hay horas disponibles!\n"
                    f"[Enlace directo a la agenda]({WIDGET_URL})"
                )
            else:
                print("Estado normal: Sin citas disponibles detectadas en la interfaz.", flush=True)
                
    except Exception as e:
        error_msg = f"Error controlado en ciclo de revisión: {e}"
        print(error_msg, flush=True)
        # Opcional: Descomentar la siguiente línea si quieres alerta de cada pequeño error temporal
        # enviar_telegram(f"⚠️ *Aviso del Bot*:\n`{str(e)}`")
        
    finally:
        if browser:
            try:
                browser.close()
                print("Navegador cerrado con éxito. Sesión liberada.", flush=True)
            except Exception as close_error:
                print(f"Error al cerrar navegador: {close_error}", flush=True)

def main():
    print("=== MONITOR DE CITAS CONSULARES CON CLOAKBROWSER ===", flush=True)
    print(f"Intervalo configurado: {CHECK_INTERVAL} segundos.", flush=True)
    
    enviar_telegram(
        "🤖 *Monitor con CloakBrowser Activo*\n"
        "Visado Familiar Comunitario - La Habana\n"
        f"Revisando agenda cada {CHECK_INTERVAL} segundos."
    )
    
    while True:
        revisar_citas()
        print(f"Ciclo finalizado. Durmiendo {CHECK_INTERVAL} segundos...\n", flush=True)
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
    
