import time
import os
import requests
from cloakbrowser import launch

# Cargar las variables de entorno configuradas en Railway
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", 60))

# Estructura modular del enlace de la agenda consular
PUBLIC_KEY = "2f9880d8d5b8feb958c81d2a08157bcf1"
SERVICE_ID = "bkt871926"
WIDGET_URL = f"https://www.citaconsular.es/es/hosteds/widgetdefault/{PUBLIC_KEY}/{SERVICE_ID}"

def enviar_telegram(mensaje):
    """Envía alertas directamente a tu chat de Telegram"""
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
        # Lanzamiento usando la configuración oficial de CloakBrowser Pro (Plan Gratuito)
        # La licencia se toma automáticamente de la variable de entorno CLOAKBROWSER_LICENSE_KEY en Railway
        browser = launch(
            headless=True,
            humanize=True,
            human_preset="careful",
            geoip=True
        )
        
        page = browser.new_page()
        print(f"Navegando hacia: {WIDGET_URL}", flush=True)
        
        # Entrar al enlace construido de la agenda
        page.goto(WIDGET_URL, timeout=60000)
        
        # Esperar a que cargue el contenido interno de Bookitit y Cloudflare
        print("Esperando a que el widget cargue por completo...", flush=True)
        page.wait_for_timeout(7000)
        
        # Extraer el texto visible de la página para analizarlo
        body_text = page.inner_text("body").lower()
        
        # Palabras clave comunes cuando NO hay citas disponibles
        textos_sin_citas = [
            "no hay citas",
            "no disponemos de citas",
            "en este momento no hay",
            "próximamente se abrirán",
            "completo"
        ]
        
        # Comprobar si Cloudflare interrumpió la carga
        hay_bloqueo_cloudflare = "cf-browser-verification" in body_text or "challenge-running" in body_text
        
        if hay_bloqueo_cloudflare:
            print("⚠️ Alerta: Cloudflare detuvo la ejecución.", flush=True)
            enviar_telegram("⚠️ *Cloudflare* ha interceptado la consulta en este ciclo.")
        else:
            # Validar si aparece algún indicador de falta de cupos
            sin_cupos = any(frase in body_text for frase in textos_sin_citas)
            
            if not sin_cupos:
                print("¡POSIBLE CAMBIO O CITAS DETECTADAS!", flush=True)
                enviar_telegram(
                    "🚨 *¡ATENCIÓN PEDRY!* 🚨\n"
                    "El widget respondió diferente o hay movimiento de citas.\n"
                    f"[Enlace directo a la agenda]({WIDGET_URL})"
                )
            else:
                print("Sin citas disponibles por el momento. Todo normal.", flush=True)
                
    except Exception as e:
        error_msg = f"Error crítico durante la ejecución del navegador: {e}"
        print(error_msg, flush=True)
        enviar_telegram(f"❌ *Error en el Bot de Citas*:\n`{str(e)}`")
        
    finally:
        # Cierre limpio obligatorio para liberar la sesión única gratuita de CloakBrowser
        if browser:
            try:
                browser.close()
                print("Navegador cerrado limpiamente (Sesión liberada).", flush=True)
            except Exception as close_error:
                print(f"Error al cerrar el navegador: {close_error}", flush=True)

def main():
    print("=== MONITOR DE CITAS CONSULARES CON CLOAKBROWSER ===", flush=True)
    print(f"Intervalo configurado: {CHECK_INTERVAL} segundos.", flush=True)
    
    # Notificar a Telegram que el bot arrancó correctamente
    enviar_telegram(
        "🤖 *Monitor con CloakBrowser Activo*\n"
        "Visado Familiar Comunitario - La Habana\n"
        f"Revisando agenda cada {CHECK_INTERVAL} segundos."
    )
    
    while True:
        revisar_citas()
        print(f"Esperando {CHECK_INTERVAL} segundos para la siguiente revisión...\n", flush=True)
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
    
