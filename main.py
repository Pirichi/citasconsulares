import time
import os
import requests

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
    print("Consultando widget consular mediante petición HTTP...", flush=True)
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "es-ES,es;q=0.9",
        "Referer": "https://www.citaconsular.es/"
    }
    
    try:
        response = requests.get(WIDGET_URL, headers=headers, timeout=15)
        print(f"Código de estado HTTP: {response.status_code}", flush=True)
        
        if response.status_code != 200:
            print(f"Servidor respondió con código inesperado: {response.status_code}", flush=True)
            return

        body_text = response.text.lower()
        
        # Frases que determinan que la agenda está cerrada
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
            print("⚠️ Cloudflare detectó la petición.", flush=True)
            enviar_telegram("⚠️ *Cloudflare* ha interceptado la consulta HTTP.")
        else:
            sin_cupos = any(frase in body_text for frase in textos_sin_citas)
            
            if not sin_cupos:
                # Verificación extra para asegurar que hay elementos de calendario o fechas reales
                elementos_validos = ["calendario", "horario", "mes", "dia", "cita", "servicio", "continuar", "continue"]
                hay_indicios = any(palabra in body_text for palabra in elementos_validos)
                
                if hay_indicios:
                    print("🚨 ¡CAMBIO DETECTADO EN LA AGENDA!", flush=True)
                    enviar_telegram(
                        "🚨 *¡ATENCIÓN PEDRY! HAY CITAS* 🚨\n"
                        "¡La agenda muestra cambios o elementos activos!\n"
                        f"[Enlace directo a la agenda]({WIDGET_URL})"
                    )
                else:
                    print("Página sin frases de cierre pero sin indicios claros. Monitoreando...", flush=True)
            else:
                print("Sin citas disponibles por el momento. Todo normal.", flush=True)

    except Exception as e:
        print(f"Error en la petición: {e}", flush=True)

def main():
    print("=== MONITOR DE CITAS CONSULARES (HTTP RÁPIDO) ===", flush=True)
    print(f"Intervalo configurado: {CHECK_INTERVAL} segundos.", flush=True)
    
    enviar_telegram(
        "🤖 *Monitor Rápido Activo*\n"
        "Visado Familiar Comunitario - La Habana\n"
        f"Revisando agenda cada {CHECK_INTERVAL} segundos."
    )
    
    while True:
        revisar_citas()
        print(f"Ciclo finalizado. Durmiendo {CHECK_INTERVAL} segundos...\n", flush=True)
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
    
