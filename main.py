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
    print("Iniciando revisión buscando dentro del iframe...", flush=True)
    
    browser = None
    try:
        browser = launch(
            headless=True,
            humanize=True,
            human_preset="careful",
            geoip=False
        )
        
        page = browser.new_page()
        page.on("dialog", lambda dialog: dialog.accept())
        
        page.goto(WIDGET_URL, wait_until="domcontentloaded", timeout=35000)
        
        # Esperamos a que carguen los marcos de la página
        page.wait_for_timeout(6000)
        
        # Buscamos el texto dentro de los iframes si los hay, o en la página principal
        texto_encontrado = ""
        
        # Intentamos extraer texto de los iframes de la página
        frames = page.frames
        print(f"Total de marcos (iframes) detectados: {len(frames)}", flush=True)
        
        for frame in frames:
            try:
                f_text = frame.inner_text("body").lower()
                if "no hay horas disponibles" in f_text or "calendario" in f_text or "horario" in f_text:
                    texto_encontrado = f_text
                    break
            except Exception:
                continue
                
        # Si no se encontró en los iframes, usamos la página principal
        if not texto_encontrado:
            texto_encontrado = page.inner_text("body").lower()

        print(f"Texto analizado con éxito (primeros 100 caracteres): {texto_encontrado[:100]}...", flush=True)
        
        # CONDICIÓN ESTRICTA
        if "no hay horas disponibles" in texto_encontrado:
            print("Estado normal: El cartel de cierre sigue presente.", flush=True)
        else:
            print("🚨 ¡EL CARTEL DE CIERRE DESAPARECIÓ DENTRO DEL WIDGET!", flush=True)
            enviar_telegram(
                "🚨 *¡ATENCIÓN PEDRY! ¡LA AGENDA CAMBIÓ!* 🚨\n"
                "¡El widget ya no muestra el aviso de cierre!\n"
                f"[Enlace directo a la agenda]({WIDGET_URL})"
            )

    except Exception as e:
        print(f"Error durante el ciclo con iframe: {e}", flush=True)
        
    finally:
        if browser:
            try:
                browser.close()
            except Exception:
                pass

def main():
    print("=== MONITOR DE CITAS (SOPORTE IFRAME) ===", flush=True)
    print(f"Intervalo configurado: {CHECK_INTERVAL} segundos.", flush=True)
    
    while True:
        revisar_citas()
        print(f"Ciclo completado. Esperando {CHECK_INTERVAL} segundos...\n", flush=True)
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
    
