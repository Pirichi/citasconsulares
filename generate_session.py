import os
import json
import time
from playwright.sync_api import sync_playwright
from flask import Flask, request

app = Flask(__name__)
session_ready = False

@app.route('/')
def index():
    return '''
    <h1>Generador de sesión para citaconsular</h1>
    <p>1. Abre este enlace en tu navegador: <a href="https://www.citaconsular.es/es/hosteds/widgetdefault/2f9880d8d5b8feb958c81d2a08157bcf1/bkt871926" target="_blank">Haz clic aquí</a></p>
    <p>2. Resuelve el captcha de Cloudflare</p>
    <p>3. Una vez veas el widget, vuelve aquí y haz clic en "Guardar sesión"</p>
    <form action="/save" method="post">
        <button type="submit">Guardar sesión</button>
    </form>
    '''

@app.route('/save', methods=['POST'])
def save():
    global session_ready
    # Ejecuta el guardado de la sesión (usando Playwright)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            locale="es-ES",
            viewport={"width": 1280, "height": 720}
        )
        page = context.new_page()
        page.goto("https://www.citaconsular.es/es/hosteds/widgetdefault/2f9880d8d5b8feb958c81d2a08157bcf1/bkt871926")
        # Esperamos que el usuario haya resuelto el captcha manualmente (no podemos saberlo, asumimos que ya lo hizo)
        time.sleep(5)
        # Guardar estado
        context.storage_state(path="storage_state.json")
        browser.close()
    return "✅ Sesión guardada correctamente. Ahora puedes usar el monitor principal."

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
