import os
import time
import json
import calendar
import requests
from datetime import datetime

# ====================== CONFIGURACIÓN ======================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
RAW_CHAT_IDS = os.getenv("TELEGRAM_CHAT_ID", "")
TELEGRAM_CHAT_IDS = [cid.strip() for cid in RAW_CHAT_IDS.split(",") if cid.strip()]

CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "120"))

PUBLIC_KEY = "2f9880d8d5b8feb958c81d2a08157bcf1"
SERVICE_ID = "bkt871926"
WIDGET_URL = f"https://www.citaconsular.es/es/hosteds/widgetdefault/{PUBLIC_KEY}/{SERVICE_ID}"

# ===========================================================

def send_telegram(message: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_IDS:
        print("⚠️ Faltan TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    for chat_id in TELEGRAM_CHAT_IDS:
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True
        }
        try:
            r = requests.post(url, json=payload, timeout=12)
            r.raise_for_status()
            print(f"✅ Notificación enviada a {chat_id}")
        except Exception as e:
            print(f"❌ Error Telegram {chat_id}: {e}")

def get_available_slots(start_date: str, end_date: str) -> list:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        "Referer": WIDGET_URL,
        "Origin": "https://www.citaconsular.es",
    }

    params = {
        "callback": "",
        "type": "default",
        "publickey": PUBLIC_KEY,
        "lang": "es",
        "services[]": SERVICE_ID,
        "agendas[]": SERVICE_ID,
        "src": WIDGET_URL,
        "start": start_date,
        "end": end_date,
    }

    try:
        response = requests.get(
            "https://www.citaconsular.es/onlinebookings/datetime/",
            headers=headers,
            params=params,
            timeout=25
        )

        print(f"→ Status: {response.status_code} | Length: {len(response.text)}")

        if response.status_code != 200:
            print(f"⚠️ Respuesta no 200. Primeros 300 chars:\n{response.text[:300]}")
            return []

        text = response.text.strip()

        if not text:
            print("⚠️ Respuesta vacía")
            return []

        # Intentamos extraer el JSON de diferentes formatos posibles
        try:
            # Caso 1: JSON puro
            data = json.loads(text)
        except json.JSONDecodeError:
            # Caso 2: JSONP tipo callback({...}) o ({...})
            try:
                start = text.find("{")
                end = text.rfind("}") + 1
                if start != -1 and end > start:
                    data = json.loads(text[start:end])
                else:
                    print(f"⚠️ No se encontró JSON. Primeros 400 chars:\n{text[:400]}")
                    return []
            except Exception as e:
                print(f"⚠️ Error parseando JSON: {e}")
                print(f"Contenido recibido:\n{text[:400]}")
                return []

        available = []
        for slot in data.get("Slots", []):
            times = slot.get("times")
            if times:
                available.append({
                    "date": slot.get("date"),
                    "times": times
                })

        return available

    except Exception as e:
        print(f"❌ Error de conexión: {e}")
        return []

def check_appointments():
    today = datetime.now().date()
    months_to_check = []

    current = today.replace(day=1)
    for _ in range(3):
        last_day = calendar.monthrange(current.year, current.month)[1]
        end = current.replace(day=last_day)
        months_to_check.append((
            current.strftime("%Y-%m-%d"),
            end.strftime("%Y-%m-%d")
        ))
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)

    all_slots = []
    for start, end in months_to_check:
        slots = get_available_slots(start, end)
        all_slots.extend(slots)
        time.sleep(1)  # pequeña pausa entre meses

    if all_slots:
        msg = "🚨 *¡CITAS DISPONIBLES!* 🚨\n\n"
        msg += "*Visado Familiar Comunitario - La Habana*\n\n"
        for s in all_slots[:8]:
            times_str = ", ".join(s["times"][:5])
            msg += f"📅 *{s['date']}* → {times_str}\n"
        msg += f"\n🔗 {WIDGET_URL}"
        print("🎉 ¡Citas encontradas!")
        send_telegram(msg)
    else:
        now = datetime.now().strftime("%H:%M:%S")
        print(f"{now} - Sin citas disponibles")

def main():
    print("=" * 55)
    print("Monitor Visado Familiar Comunitario - La Habana")
    print(f"Región: EU West | Intervalo: {CHECK_INTERVAL}s")
    print("=" * 55)

    send_telegram(
        "🤖 *Monitor reiniciado*\n\n"
        "Visado Familiar Comunitario - La Habana\n"
        f"Revisando cada {CHECK_INTERVAL} segundos."
    )

    while True:
        try:
            check_appointments()
        except Exception as e:
            print(f"Error en el ciclo: {e}")
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
