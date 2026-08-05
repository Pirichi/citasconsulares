#!/usr/bin/env python3
"""
main.py - Bookitit widget monitor using CloakBrowser, safe frame traversal,
Cloudflare/transient-state stabilization, and Telegram notifications.

Environment variables:
- WIDGET_URL (required): URL to open that contains the Bookitit widget (page with iframes).
- TELEGRAM_BOT_TOKEN (required to send notifications)
- TELEGRAM_CHAT_ID (required to send notifications)
- CHECK_INTERVAL (optional, seconds, default=60)
- BROWSER_EXECUTABLE_PATH (optional): path to CloakBrowser/Chrome binary to use (passed via env to cloakbrowser if needed)
- HEADLESS (optional, "1" or "0"; default "1")
- NAV_TIMEOUT (optional, navigation timeout in ms; default 60000)
- CLOUDFLARE_STABILIZE_SECONDS (optional, seconds to wait while Cloudflare may resolve; default 8)
- CLOUDFLARE_RETRIES (optional, number of stabilization retries; default 2)
"""
import os
import sys
import time
import traceback
import requests
from datetime import datetime
from typing import List, Tuple

from cloakbrowser import launch
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

CLOSURE_PHRASE = "No hay horas disponibles"
DEFAULT_CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "60"))
DEFAULT_NAV_TIMEOUT_MS = int(os.environ.get("NAV_TIMEOUT", "60000"))
DEFAULT_CF_STABILIZE_SECONDS = int(os.environ.get("CLOUDFLARE_STABILIZE_SECONDS", "8"))
DEFAULT_CF_RETRIES = int(os.environ.get("CLOUDFLARE_RETRIES", "2"))

CLOUDFLARE_INDICATORS = [
    "checking your browser",
    "please enable javascript and cookies to continue",
    "ddos protection by cloudflare",
    "cf-chl-bypass",
    "cloudflare",
    "checking your browser before accessing",
    "verifying you are human",
    "turnstile",
    "challenge",
]


def now_ts() -> str:
    return datetime.utcnow().isoformat() + "Z"


def log(msg: str) -> None:
    print(f"{now_ts()} | {msg}", flush=True)


def is_cloudflare_text(text: str) -> bool:
    if not text:
        return False
    lower = text.lower()
    for phrase in CLOUDFLARE_INDICATORS:
        if phrase in lower:
            return True
    return False


def extract_frame_texts(page) -> List[Tuple[str, str]]:
    results = []
    seen_frames = set()
    try:
        frames = page.frames
    except Exception:
        return results

    for frame in frames:
        try:
            frame_id = (frame.url or "<no-url>", frame.name or "")
            if frame_id in seen_frames:
                continue
            seen_frames.add(frame_id)

            text = ""
            try:
                body = frame.locator("body")
                if body:
                    text = body.inner_text(timeout=2000)
                else:
                    text = ""
            except PlaywrightTimeoutError:
                text = ""
            except Exception:
                text = ""

            if not text:
                try:
                    html = frame.content()
                    import re
                    text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.S | re.I)
                    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.S | re.I)
                    text = re.sub(r"<[^>]+>", " ", text)
                    text = " ".join(text.split())
                except Exception:
                    text = ""

            results.append((frame.url or "<no-url>", text.strip()))
        except Exception as e:
            log(f"Warning extracting frame text: {e}")
            continue

    return results


def choose_relevant_texts(frame_texts: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
    filtered = []
    for url, text in frame_texts:
        if not text:
            continue
        if is_cloudflare_text(text):
            continue
        filtered.append((url, text))

    if not filtered:
        return []

    bookitit_frames = [t for t in filtered if "bookitit" in (t[0] or "").lower()]
    if bookitit_frames:
        return bookitit_frames

    return filtered


def send_telegram(bot_token: str, chat_id: str, message: str) -> bool:
    api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "disable_web_page_preview": True}
    try:
        r = requests.post(api_url, json=payload, timeout=15)
        if r.status_code == 200:
            log("Telegram notification sent successfully.")
            return True
        else:
            log(f"Telegram API responded with status {r.status_code}: {r.text}")
            return False
    except Exception as e:
        log(f"Failed to send Telegram message: {e}")
        return False


def safe_navigate(page, url: str, timeout_ms: int) -> bool:
    try:
        page.goto(url, wait_until="networkidle", timeout=timeout_ms)
        return True
    except PlaywrightTimeoutError:
        log(f"Navigation timeout after {timeout_ms}ms for URL: {url}")
        return False
    except Exception as e:
        log(f"Navigation exception for URL {url}: {e}")
        return False


def main():
    widget_url = os.environ.get("WIDGET_URL")
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    check_interval = int(os.environ.get("CHECK_INTERVAL", DEFAULT_CHECK_INTERVAL))
    exec_path = os.environ.get("BROWSER_EXECUTABLE_PATH")
    headless = os.environ.get("HEADLESS", "1") != "0"
    nav_timeout = int(os.environ.get("NAV_TIMEOUT", DEFAULT_NAV_TIMEOUT_MS))
    cf_stabilize_seconds = int(os.environ.get("CLOUDFLARE_STABILIZE_SECONDS", DEFAULT_CF_STABILIZE_SECONDS))
    cf_retries = int(os.environ.get("CLOUDFLARE_RETRIES", DEFAULT_CF_RETRIES))

    if not widget_url:
        log("ERROR: WIDGET_URL environment variable is required.")
        sys.exit(2)
    if not bot_token or not chat_id:
        log("ERROR: TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are required to send notifications.")
        sys.exit(2)

    log("Starting Bookitit widget monitor with CloakBrowser.")
    log(f"WIDGET_URL: {widget_url}")
    log(f"CHECK_INTERVAL: {check_interval}s, HEADLESS: {headless}, NAV_TIMEOUT: {nav_timeout}ms")
    log(f"CLOUDFLARE_STABILIZE_SECONDS: {cf_stabilize_seconds}, CLOUDFLARE_RETRIES: {cf_retries}")

    previous_closed_state = None

    browser = None
    try:
        if exec_path:
            os.environ.setdefault("BROWSER_EXECUTABLE_PATH", exec_path)
            log(f"Set BROWSER_EXECUTABLE_PATH env to: {exec_path}")

        log("Launching CloakBrowser...")
        browser = launch(
            headless=headless,
            humanize=True,
            human_preset="careful",
            geoip=False,
        )
        log("CloakBrowser launched successfully.")
    except Exception as e:
        log(f"Fatal error launching CloakBrowser: {e}\n{traceback.format_exc()}")
        sys.exit(1)

    try:
        log("Entering monitoring loop.")
        while True:
            cycle_start = time.time()

            # HEARTBEAT: guaranteed log at the start of each cycle
            log(f"heartbeat: cycle_start={now_ts()} previous_closed_state={previous_closed_state}")

            page = None
            try:
                try:
                    page = browser.new_page()
                except Exception as e:
                    log(f"Failed to create new page: {e}\n{traceback.format_exc()}")
                    log(f"Sleeping full check_interval ({check_interval}s) due to page creation failure.")
                    time.sleep(check_interval)
                    continue

                try:
                    page.set_viewport_size({"width": 1280, "height": 800})
                    page.set_extra_http_headers(
                        {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                                       "Chrome/115.0.0.0 Safari/537.36"}
                    )
                except Exception:
                    pass

                nav_ok = safe_navigate(page, widget_url, nav_timeout)
                time.sleep(2)

                try:
                    frame_texts = extract_frame_texts(page)
                except Exception as e:
                    log(f"Failed extracting frames after navigation: {e}\n{traceback.format_exc()}")
                    frame_texts = []

                combined_all = "\n\n".join((t for _, t in frame_texts)) if frame_texts else ""
                detected_cf = is_cloudflare_text(combined_all) or (not nav_ok and not combined_all)

                if detected_cf:
                    log("Cloudflare/challenge or navigation timeout detected on initial extraction.")
                    stabilized = False
                    for attempt in range(1, cf_retries + 1):
                        log(f"Cloudflare stabilization: waiting {cf_stabilize_seconds}s (attempt {attempt}/{cf_retries})...")
                        time.sleep(cf_stabilize_seconds)
                        try:
                            frame_texts = extract_frame_texts(page)
                        except Exception as e:
                            log(f"Attempt {attempt}: frame extraction failed: {e}")
                            frame_texts = []
                        combined_all = "\n\n".join((t for _, t in frame_texts)) if frame_texts else ""
                        if frame_texts and not is_cloudflare_text(combined_all):
                            log("Stabilization successful: Cloudflare indicators no longer present.")
                            stabilized = True
                            break
                        else:
                            log(f"Attempt {attempt}: still Cloudflare/empty.")
                    if not stabilized:
                        log(f"Cloudflare challenge persisted after stabilization attempts; sleeping full check_interval ({check_interval}s) and skipping analysis to avoid false positives.")
                        try:
                            page.close()
                        except Exception:
                            pass
                        time.sleep(check_interval)
                        continue

                relevant = choose_relevant_texts(frame_texts)
                if not relevant:
                    log("No relevant content found (frames empty or Cloudflare filtered). Sleeping full check_interval to avoid rapid retries.")
                    try:
                        page.close()
                    except Exception:
                        pass
                    time.sleep(check_interval)
                    continue

                combined_text = "\n\n".join(t for _, t in relevant)
                closed_present = CLOSURE_PHRASE.lower() in combined_text.lower()
                log(f"Closure phrase present in relevant content? {closed_present}")

                if previous_closed_state is None:
                    previous_closed_state = closed_present
                    log(f"Initial closure state recorded: {previous_closed_state}")

                if previous_closed_state and not closed_present:
                    log("Detected closure phrase DISAPPEARED -> preparing Telegram notification.")
                    message = (
                        f"Agenda changed: '{CLOSURE_PHRASE}' is no longer present on the widget at {widget_url}\n"
                        f"Time: {now_ts()}\n"
                        f"Detected frames (snippets):\n"
                    )
                    for url, text in relevant:
                        snippet = (text[:300].replace("\n", " ")) if text else ""
                        message += f"- {url} -> {snippet}\n"

                    sent_ok = False
                    try:
                        sent_ok = send_telegram(bot_token, chat_id, message)
                    except Exception as e:
                        log(f"Exception sending Telegram: {e}\n{traceback.format_exc()}")

                    if sent_ok:
                        previous_closed_state = closed_present
                        log("Notification sent and previous_closed_state updated.")
                    else:
                        log("Notification failed; keeping previous_closed_state True to retry notifying only on next disappearance event.")
                else:
                    previous_closed_state = closed_present
                    log(f"No notification. previous_closed_state set to {previous_closed_state}")

                try:
                    page.close()
                except Exception:
                    pass

            except KeyboardInterrupt:
                log("KeyboardInterrupt received: shutting down gracefully.")
                break
            except Exception as e:
                log(f"Unexpected error in monitoring loop: {e}\n{traceback.format_exc()}")
                try:
                    if page:
                        page.close()
                except Exception:
                    pass
            finally:
                log(f"Cycle complete. Sleeping full CHECK_INTERVAL: {check_interval}s before next check.")
                time.sleep(check_interval)

    finally:
        try:
            if browser:
                browser.close()
                log("Browser closed.")
        except Exception:
            log("Error while closing browser (ignored).")

    log("Monitor exited.")


if __name__ == "__main__":
    main()
