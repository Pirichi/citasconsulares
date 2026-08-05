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
        browser = launch(
            headless=True,
            humanize=True,
            human_preset="careful",
            geoip=False
        )
        
        page = browser.new_page()
        
        # 1. Capturar automáticamente cualquier alerta o cuadro de bienvenida de JS
        page.on("dialog", lambda dialog: dialog.accept())
        
        print(f"Navegando hacia el widget consular...", flush=True)
        page.goto(WIDGET_URL, wait_until="domcontentloaded", timeout=30000)
        
        print("Esperando la carga inicial y posibles diálogos...", flush=True)
        page.wait_for_timeout(4000)

        # 2. Barrera del botón "Continue / Continuar" o "Para solicitar cita pulse en el botón continuar"
        body_text_inicial = page.inner_text("body").lower()
        if "continue" in body_text_inicial or "continuar" in body_text_inicial or "pulse en el botón" in body_text_inicial:
            print("Pantalla intermedia detectada. Buscando botón 'Continuar / Continue'...", flush=True)
            clicked = False
            
            # Intentar hacer clic por diferentes selectores o textos comunes en este widget
            intentos_botones = [
                "text=Continuar",
                "text=Continue",
                "button:has-text('Continuar')",
                "button:has-text('Continue')",
                "input[value*='Continuar']",
                "input[value*='Continue']",
                "a:has-text('Continuar')",
                "a:has-text('Continue')"
            ]
            
            for selector in intentos_botones:
                try:
                    if page.locator(selector).count() > 0:
                        page.click(selector, timeout=3000)
                        print(f"¡Clic exitoso usando el selector: {selector}!", flush=True)
                        clicked = True
                        break
                except Exception:
                    continue
            
            if not clicked:
                print("No se pudo hacer clic mediante selectores automáticos, intentando clic por coordenadas o avanzando...", flush=True)
            
            # Dar un respiro tras el clic para que cargue la siguiente vista del widget
            page.wait_for_timeout(5000)

        # 3. Extraer el texto final de la interfaz de citas
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
        
        if "cf-browser-verification" in body_text or "challenge-running" in body_text:
            print("⚠️ Cloudflare interceptó la conexión en este ciclo.", flush=True)
            enviar_telegram("⚠️ *Cloudflare* ha interceptado la consulta en este ciclo.")
        else:
            if len(body_text) < 100:
                print("Carga incompleta o página en blanco detectada. Ignorando este ciclo.", flush=True)
            else:
                sin_cupos = any(frase in body_text for frase in textos_sin_citas)
                
                if not sin_cupos:
                    # Filtro estricto para evitar falsos positivos por páginas vacías o transiciones
                    elementos_calendario = ["seleccione", "calendario", "horario", "mes", "dia", "cita", "servicio"]
                    hay_calendario_activo = any(palabra in body_text for palabra in elementos_calendario)
                    
                    if hay_calendario_activo:
                        print("🚨 ¡CITAS REALES DETECTADAS EN LA INTERFAZ!", flush=True)
                        enviar_telegram(
                            "🚨 *¡ATENCIÓN PEDRY! HAY CITAS* 🚨\n"
                            "¡La agenda avanzó y muestra elementos de selección activos!\n"
                            f"[Enlace directo a la agenda]({WIDGET_URL})"
                        )
                    else:
                        print("Transición detectada pero sin confirmación clara de calendario. Monitoreando...", flush=True)
                else:
                    print("Sin citas disponibles por el momento (Mensaje oficial detectado). Todo normal.", flush=True)
                
    except Exception as e:
        error_msg = f"Error controlado en ciclo de revisión: {e}"
        print(error_msg, flush=True)
        
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
    
