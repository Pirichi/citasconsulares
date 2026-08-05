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
        browser = launch(
            headless=True,
            humanize=True,
            human_preset="careful",
            geoip=False
        )
        
        page = browser.new_page()
        
        # 1. Configurar el escucha automático para aceptar cualquier alerta JavaScript (como "Welcome / Bienvenido")
        page.on("dialog", lambda dialog: dialog.accept())
        
        print(f"Navegando hacia: {WIDGET_URL}", flush=True)
        # Entrar al enlace de la agenda
        page.goto(WIDGET_URL, timeout=60000)
        
        # Esperar a que pase el diálogo y cargue la pantalla intermedia
        print("Esperando la pantalla intermedia...", flush=True)
        page.wait_for_timeout(6000)

        # 2. Buscar y hacer clic en el botón verde "Continue / Continuar"
        body_text_inicial = page.inner_text("body").lower()
        if "continue" in body_text_inicial or "continuar" in body_text_inicial:
            print("Pantalla intermedia detectada. Haciendo clic en Continuar...", flush=True)
            try:
                page.click("text=Continuar", timeout=5000)
            except Exception:
                try:
                    page.click("text=Continue", timeout=3000)
                except Exception:
                    print("No se pudo hacer clic mediante texto directo, buscando por selector...", flush=True)
            
            # Esperar a que cargue la vista final del widget
            page.wait_for_timeout(5000)

        # Extraer el texto final de la interfaz de citas
        body_text = page.inner_text("body").lower()
        
        # Frases exactas que indican que la agenda está cerrada / sin turnos
        textos_sin_citas = [
            "no hay horas disponibles",
            "no hay citas",
            "no disponemos de citas",
            "en este momento no hay",
            "próximamente se abrirán",
            "completo",
            "inténtelo de nuevo dentro de unos días"
        ]
        
        # Comprobar si Cloudflare interrumpió la carga
        hay_bloqueo_cloudflare = "cf-browser-verification" in body_text or "challenge-running" in body_text
        
        if hay_bloqueo_cloudflare:
            print("⚠️ Alerta: Cloudflare detuvo la ejecución.", flush=True)
            enviar_telegram("⚠️ *Cloudflare* ha interceptado la consulta en este ciclo.")
        else:
            # Validar si aparece alguno de los textos de que NO hay cupos
            sin_cupos = any(frase in body_text for frase in textos_sin_citas)
            
            if not sin_cupos:
                print("¡POSIBLE CAMBIO O CITAS DETECTADAS!", flush=True)
                enviar_telegram(
                    "🚨 *¡ATENCIÓN PEDRY!* 🚨\n"
                    "¡La página avanzó y ya no dice que no hay horas disponibles!\n"
                    f"[Enlace directo a la agenda]({WIDGET_URL})"
                )
            else:
                print("Sin citas disponibles por el momento (Mensaje oficial detectado en la interfaz final). Todo normal.", flush=True)
                
    except Exception as e:
        error_msg = f"Error crítico durante la ejecución del navegador: {e}"
        print(error_msg, flush=True)
        enviar_telegram(f"❌ *Error en el Bot de Citas*:\n`{str(e)}`")
        
    finally:
        if browser:
            try:
                browser.close()
                print("Navegador cerrado limpiamente (Sesión liberada).", flush=True)
            except Exception as close_error:
                print(f"Error al cerrar el navegador: {close_error}", flush=True)

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
        print(f"Esperando {CHECK_INTERVAL} segundos para la siguiente revisión...\n", flush=True)
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
        
