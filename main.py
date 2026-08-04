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

CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "120"))  # segundos (recomendado 120-180)

# Datos del Visado Familiar Comunitario - Consulado La Habana
PUBLIC_KEY = "2f9880d8d5b8feb958c81d2a08157bcf1"
SERVICE_ID = "bkt871926"
WIDGET_URL = f"https://www.citaconsular.es/es/hosteds/widgetdefault/{PUBLIC_KEY}/{SERVICE_ID}"

# ===========================================================

def send_telegram(message: str):
    """Envía notificación a todos los chat_id configurados"""
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
            print(f"❌ Error enviando a {chat_id}: {e}")

def get_available_slots(start_date: str, end_date: str) -> list:
    """Consulta el endpoint real de disponibilidad"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        "Referer": WIDGET_URL,
        "Origin": "https://www.citaconsular.es",
        "Connection": "keep-alive",
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

        if response.status_code != 200:
            print(f"⚠️ HTTP {response.status_code}")
            return []

        text = response.text.strip()

        # La respuesta suele venir como JSONP → extraemos el JSON
        if text.startswith("(") or "({" in text:
            json_str = text[text.find("{"): text.rfind("}") + 1]
        else:
            json_str = text

        data = json.loads(json_str)
        available = []

        for slot in data.get("Slots", []):
            times = slot.get("times")
            if times:  # Solo si hay horas disponibles
                available.append({
                    "date": slot.get("date"),
                    "times": times
                })

        return available

    except Exception as e:
        print(f"❌ Error consultando endpoint: {e}")
        return []

def check_appointments():
    """Revisa los próximos 3 meses"""
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
        # Siguiente mes
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)

    all_slots = []
    for start, end in months_to_check:
        slots = get_available_slots(start, end)
        all_slots.extend(slots)

    if all_slots:
        msg = "🚨 *¡CITAS DISPONIBLES DETECTADAS!* 🚨\n\n"
        msg += "*Visado Familiar Comunitario - La Habana*\n\n"

        for s in all_slots[:10]:  # Máximo 10 fechas para no saturar
            times_str = ", ".join(s["times"][:6])
            msg += f"📅 *{s['date']}*\n   → {times_str}\n\n"

        msg += f"🔗 Entra inmediatamente:\n{WIDGET_URL}"

        print("🎉 ¡Citas encontradas! Enviando alerta...")
        send_telegram(msg)
    else:
        now = datetime.now().strftime("%H:%M:%S")
        print(f"{now} - Sin citas disponibles")

def main():
    print("=" * 55)
    print("Monitor Visado Familiar Comunitario - Consulado La Habana")
    print(f"Región: EU West | Intervalo: {CHECK_INTERVAL}s")
    print("=" * 55)

    # Notificación de arranque
    send_telegram(
        "🤖 *Monitor iniciado*\n\n"
        "Visado Familiar Comunitario - La Habana\n"
        f"Revisando cada {CHECK_INTERVAL} segundos desde EU West."
    )

    while True:
        try:
            check_appointments()
        except Exception as e:
            print(f"Error inesperado en el ciclo: {e}")

        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
