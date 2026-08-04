import os
import time
import json
import re
import calendar
import requests
from datetime import datetime

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
RAW_CHAT_IDS = os.getenv("TELEGRAM_CHAT_ID", "")
TELEGRAM_CHAT_IDS = [cid.strip() for cid in RAW_CHAT_IDS.split(",") if cid.strip()]
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "180"))

PUBLIC_KEY = "2f9880d8d5b8feb958c81d2a08157bcf1"
SERVICE_ID = "bkt871926"
WIDGET_URL = f"https://www.citaconsular.es/es/hosteds/widgetdefault/{PUBLIC_KEY}/{SERVICE_ID}"

def send_telegram(message: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_IDS:
        return
    for chat_id in TELEGRAM_CHAT_IDS:
        try:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown", "disable_web_page_preview": True},
                timeout=12
            )
            print(f"✅ Notificación enviada a {chat_id}")
        except Exception as e:
            print(f"❌ Error Telegram: {e}")

def create_session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        "Origin": "https://www.citaconsular.es",
        "Referer": WIDGET_URL,
        "X-Requested-With": "XMLHttpRequest",
    })
    return s

def extract_jsonp(text):
    """Extrae el JSON de una respuesta JSONP"""
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except:
            return None
    return None

def get_config(session):
    """Obtiene la configuración del widget para sacar agendas"""
    params = {
        "callback": "jQuery",
        "type": "default",
        "publickey": PUBLIC_KEY,
        "lang": "es",
        "services[]": SERVICE_ID,
        "version": "4",
        "src": WIDGET_URL,
        "srvsrc": "https://www.citaconsular.es",
        "_": int(time.time() * 1000)
    }
    try:
        r = session.get("https://www.citaconsular.es/onlinebookings/getwidgetconfigurations/", params=params, timeout=20)
        print(f"→ getwidgetconfigurations | Status: {r.status_code} | Len: {len(r.text)}")
        data = extract_jsonp(r.text)
        if data:
            print("→ Config recibida correctamente")
            return data
        else:
            print(f"→ Preview config: {r.text[:200]}")
    except Exception as e:
        print(f"→ Error config: {e}")
    return None

def check_datetime(session, start, end, agenda_id=None):
    params = {
        "callback": "",
        "type": "default",
        "publickey": PUBLIC_KEY,
        "lang": "es",
        "services[]": SERVICE_ID,
        "src": WIDGET_URL,
        "start": start,
        "end": end,
    }
    if agenda_id:
        params["agendas[]"] = agenda_id

    try:
        r = session.get("https://www.citaconsular.es/onlinebookings/datetime/", params=params, timeout=20)
        print(f"→ datetime | Status: {r.status_code} | Len: {len(r.text)}")

        if len(r.text) < 10:
            print("   Respuesta vacía")
            return []

        data = extract_jsonp(r.text)
        if not data:
            print(f"   Preview: {r.text[:250]}")
            return []

        # Si hay error del sistema
        if "Exception" in data:
            print(f"   Error del sistema: {data}")
            return []

        available = []
        for slot in data.get("Slots", []):
            if slot.get("times"):
                available.append({"date": slot["date"], "times": slot["times"]})
        return available

    except Exception as e:
        print(f"→ Error datetime: {e}")
        return []

def main():
    print("=" * 55)
    print("Monitor Visado Familiar Comunitario - La Habana")
    print("=" * 55)

    session = create_session()

    # 1. Visitar el widget
    print("→ Visitando widget...")
    try:
        session.get(WIDGET_URL, timeout=15)
    except:
        pass

    # 2. Obtener configuración
    config = get_config(session)

    # Intentamos sacar posibles agendas del config
    possible_agendas = [SERVICE_ID]
    if config:
        # Buscamos posibles IDs de agenda en la respuesta
        text_config = json.dumps(config)
        found = re.findall(r'bkt\d+', text_config)
        possible_agendas = list(set(found)) or [SERVICE_ID]
        print(f"→ Posibles agendas encontradas: {possible_agendas}")

    send_telegram("🤖 Monitor actualizado\nBuscando agendas reales del widget...")

    while True:
        today = datetime.now().date()
        current = today.replace(day=1)
        all_slots = []

        for _ in range(3):
            last = calendar.monthrange(current.year, current.month)[1]
            start = current.strftime("%Y-%m-%d")
            end = current.replace(day=last).strftime("%Y-%m-%d")

            for agenda in possible_agendas:
                slots = check_datetime(session, start, end, agenda)
                all_slots.extend(slots)
                time.sleep(1)

            if current.month == 12:
                current = current.replace(year=current.year+1, month=1)
            else:
                current = current.replace(month=current.month+1)

        if all_slots:
            msg = "🚨 *¡CITAS DISPONIBLES!* 🚨\n\n*Visado Familiar Comunitario - La Habana*\n\n"
            for s in all_slots[:8]:
                msg += f"📅 *{s['date']}* → {', '.join(s['times'][:5])}\n"
            msg += f"\n🔗 {WIDGET_URL}"
            print("🎉 ¡Citas encontradas!")
            send_telegram(msg)
        else:
            print(f"{datetime.now().strftime('%H:%M:%S')} - Sin citas disponibles")

        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
