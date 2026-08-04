import os
import time
import json
import calendar
import requests
from datetime import datetime
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ====================== CONFIGURACIÓN ======================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
RAW_CHAT_IDS = os.getenv("TELEGRAM_CHAT_ID", "")
TELEGRAM_CHAT_IDS = [cid.strip() for cid in RAW_CHAT_IDS.split(",") if cid.strip()]

CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "150"))

PUBLIC_KEY = "2f9880d8d5b8feb958c81d2a08157bcf1"
SERVICE_ID = "bkt871926"
WIDGET_URL = f"https://www.citaconsular.es/es/hosteds/widgetdefault/{PUBLIC_KEY}/{SERVICE_ID}"

# ===========================================================

def create_session():
    session = requests.Session()
    retry = Retry(total=2, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": WIDGET_URL,
        "Origin": "https://www.citaconsular.es",
        "Connection": "keep-alive",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "X-Requested-With": "XMLHttpRequest",
    })
    return session

def send_telegram(message: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_IDS:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    for chat_id in TELEGRAM_CHAT_IDS:
        try:
            requests.post(url, json={
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True
            }, timeout=12)
            print(f"✅ Notificación enviada a {chat_id}")
        except Exception as e:
            print(f"❌ Error Telegram: {e}")

def get_available_slots(session, start_date: str, end_date: str) -> list:
    # Probamos varias combinaciones de parámetros
    param_sets = [
        # Combinación 1 (la más común)
        {
            "callback": "",
            "type": "default",
            "publickey": PUBLIC_KEY,
            "lang": "es",
            "services[]": SERVICE_ID,
            "agendas[]": SERVICE_ID,
            "src": WIDGET_URL,
            "start": start_date,
            "end": end_date,
        },
        # Combinación 2 (sin agendas)
        {
            "callback": "",
            "type": "default",
            "publickey": PUBLIC_KEY,
            "lang": "es",
            "services[]": SERVICE_ID,
            "src": WIDGET_URL,
            "start": start_date,
            "end": end_date,
        },
        # Combinación 3 (formato más simple)
        {
            "publickey": PUBLIC_KEY,
            "lang": "es",
            "type": "default",
            "start": start_date,
            "end": end_date,
            "services[]": SERVICE_ID,
        },
    ]

    for i, params in enumerate(param_sets, 1):
        try:
            response = session.get(
                "https://www.citaconsular.es/onlinebookings/datetime/",
                params=params,
                timeout=20
            )

            print(f"→ Intento {i} | Status: {response.status_code} | Length: {len(response.text)}")

            if response.status_code != 200 or not response.text.strip():
                continue

            text = response.text.strip()

            # Intentamos parsear
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                start = text.find("{")
                end = text.rfind("}") + 1
                if start == -1:
                    print(f"   No JSON encontrado. Preview: {text[:150]}")
                    continue
                data = json.loads(text[start:end])

            available = []
            for slot in data.get("Slots", []):
                if slot.get("times"):
                    available.append({
                        "date": slot.get("date"),
                        "times": slot["times"]
                    })

            if available or "Slots" in data:
                print(f"   ✅ Respuesta válida recibida (intento {i})")
                return available

        except Exception as e:
            print(f"   Error en intento {i}: {e}")
            continue

    return []

def check_appointments(session):
    today = datetime.now().date()
    months = []
    current = today.replace(day=1)

    for _ in range(3):
        last = calendar.monthrange(current.year, current.month)[1]
        end = current.replace(day=last)
        months.append((current.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")))
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)

    all_slots = []
    for start, end in months:
        slots = get_available_slots(session, start, end)
        all_slots.extend(slots)
        time.sleep(1.5)

    if all_slots:
        msg = "🚨 *¡CITAS DISPONIBLES!* 🚨\n\n*Visado Familiar Comunitario - La Habana*\n\n"
        for s in all_slots[:8]:
            msg += f"📅 *{s['date']}* → {', '.join(s['times'][:5])}\n"
        msg += f"\n🔗 {WIDGET_URL}"
        print("🎉 ¡Citas encontradas!")
        send_telegram(msg)
    else:
        print(f"{datetime.now().strftime('%H:%M:%S')} - Sin citas disponibles")

def main():
    print("=" * 55)
    print("Monitor Visado Familiar Comunitario - La Habana")
    print(f"Región: EU West | Intervalo: {CHECK_INTERVAL}s")
    print("=" * 55)

    session = create_session()

    # Primero visitamos el widget para intentar conseguir cookies
    try:
        print("→ Visitando widget para obtener cookies...")
        session.get(WIDGET_URL, timeout=15)
        print("→ Cookies obtenidas")
    except Exception as e:
        print(f"→ No se pudieron obtener cookies: {e}")

    send_telegram("🤖 *Monitor actualizado*\nVisado Familiar Comunitario - La Habana\nProbando múltiples combinaciones de parámetros.")

    while True:
        try:
            check_appointments(session)
        except Exception as e:
            print(f"Error en ciclo: {e}")
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
