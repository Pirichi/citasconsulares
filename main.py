#!/usr/bin/env python3
"""
main.py - Bookitit widget monitor using CloakBrowser, detailed runtime logging,
Cloudflare/transient-state stabilization, and Telegram notifications.

This variant adds very fine-grained logs around page creation, navigation,
frame extraction and stabilization so you can see exactly where the loop
is blocking in production.

Environment variables:
- WIDGET_URL (required)
- TELEGRAM_BOT_TOKEN (required)
- TELEGRAM_CHAT_ID (required)
- CHECK_INTERVAL (optional, seconds, default=60)
- BROWSER_EXECUTABLE_PATH (optional)
- HEADLESS (optional, "1" or "0"; default "1")
- NAV_TIMEOUT (optional, navigation timeout in ms; default 60000)
- CLOUDFLARE_STABILIZE_SECONDS (optional, default 8)
- CLOUDFLARE_RETRIES (optional, default 2)
"""
import os
import sys
import time
import traceback
import requests
from datetime import datetime
from typing import List, Tuple

from cloakbrowser import launch
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, Error as PlaywrightError

# Configuration / constants
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


def extract_frame_texts(page, per_frame_timeout_ms: int = 3000) -> List[Tuple[str, str]]:
    """
    Collect text content from all frames (including main frame).
    This function logs each step and applies short timeouts for frame operations.
    Falls back to a safe evaluate that reads document.body.innerText (inherits Playwright timeout).
    """
    results = []
    seen_frames = set()
    try:
        frames = page.frames
    except Exception as e:
        log(f"extract_frame_texts: failed to read page.frames: {e}")
        return results

    log(f"extract_frame_texts: discovered {len(frames)} frames")

    for idx, frame in enumerate(frames):
        try:
            frame_url = frame.url or "<no-url>"
            frame_name = frame.name or ""
            frame_id = (frame_url, frame_name)
            if frame_id in seen_frames:
                log(f"extract_frame_texts: skipping duplicate frame {frame_url!r} name={frame_name!r}")
                continue
            seen_frames.add(frame_id)

            log(f"extract_frame_texts: processing frame #{idx} url={frame_url!r} name={frame_name!r}")

            text = ""

            # Try using body locator.inner_text with a controlled timeout
            try:
                log(f"extract_frame_texts: attempting body.inner_text (timeout={per_frame_timeout_ms}ms)")
                body = frame.locator("body")
                if body:
                    # inner_text accepts timeout in ms
                    text = body.inner_text(timeout=per_frame_timeout_ms)
                    log(f"extract_frame_texts: body.inner_text succeeded (len={len(text)})")
                else:
                    log("extract_frame_texts: no body locator found")
                    text = ""
            except PlaywrightTimeoutError:
                log("extract_frame_texts: body.inner_text timed out")
                text = ""
            except PlaywrightError as e:
                log(f"extract_frame_texts: Playwright error during body.inner_text: {e}")
                text = ""
            except Exception as e:
                log(f"extract_frame_texts: unexpected error during body.inner_text: {e}")
                text = ""

            # Fallback: use a safe evaluate to return document.body.innerText
            if not text:
                try:
                    log(f"extract_frame_texts: attempting evaluate fallback (timeout inherits page default)...")
                    # Evaluate the page's body text; this inherits page default timeout
                    # If no body exists return empty string
                    text = frame.evaluate("() => document.body ? document.body.innerText : ''")
                    if text:
                        log(f"extract_frame_texts: evaluate fallback succeeded (len={len(text)})")
                    else:
                        log("extract_frame_texts: evaluate fallback returned empty text")
                except PlaywrightTimeoutError:
                    log("extract_frame_texts: evaluate fallback timed out")
                    text = ""
                except PlaywrightError as e:
                    log(f"extract_frame_texts: Playwright error during evaluate fallback: {e}")
                    text = ""
                except Exception as e:
                    log(f"extract_frame_texts: unexpected error during evaluate fallback: {e}")
                    text = ""

            results.append((frame_url, (text or "").strip()))
        except Exception as e:
            log(f"extract_frame_texts: unexpected outer exception for a frame: {e}\n{traceback.format_exc()}")
            continue

    log(f"extract_frame_texts: completed, collected {len(results)} frame texts")
    return results


def choose_relevant_texts(frame_texts: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
    filtered = []
    for url, text in frame_texts:
        if not text:
            continue
        if is_cloudflare_text(text):
            log(f"choose_relevant_texts: filtering out Cloudflare-like text from {url}")
            continue
        filtered.append((url, text))

    if not filtered:
        return []

    bookitit_frames = [t for t in filtered if "bookitit" in (t[0] or "").lower()]
    if bookitit_frames:
        log(f"choose_relevant_texts: preferred bookitit frames count={len(bookitit_frames)}")
        return bookitit_frames

    log(f"choose_relevant_texts: returning {len(filtered)} filtered frames")
    return filtered


def send_telegram(bot_token: str, chat_id: str, message: str) -> bool:
    api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "disable_web_page_preview": True}
    try:
        r = requests.post(api_url, json=payload, timeout=15)
        if r.status_code == 200:
            log("send_telegram: Telegram notification sent successfully.")
            return True
        else:
            log(f"send_telegram: Telegram API responded with status {r.status_code}: {r.text}")
            return False
    except Exception as e:
        log(f"send_telegram: Failed to send Telegram message: {e}")
        return False


def safe_navigate(page, url: str, timeout_ms: int) -> bool:
    """
    Navigate and wait for networkidle. Return True if navigation completed (or returned quickly),
    False on timeout or exception. Includes logging.
    """
    try:
        log(f"safe_navigate: navigating to {url!r} with timeout {timeout_ms}ms")
        page.goto(url, wait_until="networkidle", timeout=timeout_ms)
        log("safe_navigate: goto returned without exception")
        return True
    except PlaywrightTimeoutError:
        log(f"safe_navigate: Navigation timeout after {timeout_ms}ms for URL: {url}")
        return False
    except PlaywrightError as e:
        log(f"safe_navigate: Playwright error during navigation: {e}")
        return False
    except Exception as e:
        log(f"safe_navigate: Unexpected exception during navigation: {e}")
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

    log("Starting Bookitit widget monitor with CloakBrowser (detailed logging).")
    log(f"WIDGET_URL: {widget_url}")
    log(f"CHECK_INTERVAL: {check_interval}s, HEADLESS: {headless}, NAV_TIMEOUT: {nav_timeout}ms")
    log(f"CLOUDFLARE_STABILIZE_SECONDS: {cf_stabilize_seconds}, CLOUDFLARE_RETRIES: {cf_retries}")

    previous_closed_state = None
    browser = None

    try:
        if exec_path:
            os.environ.setdefault("BROWSER_EXECUTABLE_PATH", exec_path)
            log(f"Using custom BROWSER_EXECUTABLE_PATH: {exec_path}")

        log("Launching CloakBrowser...")
        browser = launch(headless=headless, humanize=True, human_preset="careful", geoip=False)
        log("CloakBrowser launched successfully.")
    except Exception as e:
        log(f"Fatal error launching CloakBrowser: {e}\n{traceback.format_exc()}")
        sys.exit(1)

    try:
        log("Entering monitoring loop.")
        while True:
            cycle_start = time.time()
            # HEARTBEAT
            log(f"heartbeat: cycle_start={now_ts()} previous_closed_state={previous_closed_state}")

            page = None
            try:
                # Page creation
                try:
                    log("loop: creating new page...")
                    page = browser.new_page()
                    log("loop: page created successfully")
                except Exception as e:
                    log(f"loop: failed to create new page: {e}\n{traceback.format_exc()}")
                    log(f"loop: sleeping full CHECK_INTERVAL ({check_interval}s) before retry")
                    time.sleep(check_interval)
                    continue

                # Configure per-page timeouts to avoid hangs
                try:
                    log(f"loop: setting page timeouts nav={nav_timeout}ms default=10000ms")
                    page.set_default_navigation_timeout(nav_timeout)
                    page.set_default_timeout(10000)  # action timeout for locators/evaluate
                except Exception as e:
                    # Some cloakbrowser wrappers might not expose these; log and continue
                    log(f"loop: warning setting page timeouts: {e}")

                # Navigate
                nav_ok = False
                try:
                    log("loop: about to navigate to widget_url")
                    nav_ok = safe_navigate(page, widget_url, nav_timeout)
                    log(f"loop: navigation result nav_ok={nav_ok}")
                except Exception as e:
                    log(f"loop: exception during navigation: {e}\n{traceback.format_exc()}")
                    nav_ok = False

                # Small wait to allow frames to attach (but avoid long sleeps)
                try:
                    log("loop: short post-navigation sleep 2s to allow frames to attach")
                    time.sleep(2)
                except Exception:
                    pass

                # Extract frames with logged detail
                try:
                    log("loop: starting frame extraction")
                    frame_texts = extract_frame_texts(page)
                    log(f"loop: frame extraction returned {len(frame_texts)} entries")
                except Exception as e:
                    log(f"loop: exception during extract_frame_texts: {e}\n{traceback.format_exc()}")
                    frame_texts = []

                # Quick combined inspection for Cloudflare
                combined_all = "\n\n".join((t for _, t in frame_texts)) if frame_texts else ""
                detected_cf = is_cloudflare_text(combined_all) or (not nav_ok and not combined_all)
                log(f"loop: detected_cf={detected_cf} (nav_ok={nav_ok}, frames={len(frame_texts)})")

                if detected_cf:
                    log("loop: Cloudflare or navigation problem detected; attempting stabilization retries")
                    stabilized = False
                    for attempt in range(1, cf_retries + 1):
                        log(f"loop: stabilization attempt {attempt}/{cf_retries} - sleeping {cf_stabilize_seconds}s")
                        time.sleep(cf_stabilize_seconds)
                        try:
                            log(f"loop: re-running extract_frame_texts (attempt {attempt})")
                            frame_texts = extract_frame_texts(page)
                            log(f"loop: re-extraction returned {len(frame_texts)} frames")
                        except Exception as e:
                            log(f"loop: extraction attempt {attempt} failed: {e}")
                            frame_texts = []
                        combined_all = "\n\n".join((t for _, t in frame_texts)) if frame_texts else ""
                        if frame_texts and not is_cloudflare_text(combined_all):
                            log("loop: stabilization successful")
                            stabilized = True
                            break
                        else:
                            log(f"loop: attempt {attempt} still shows Cloudflare/empty")
                    if not stabilized:
                        log("loop: stabilization failed — closing page and sleeping full CHECK_INTERVAL")
                        try:
                            page.close()
                        except Exception:
                            pass
                        time.sleep(check_interval)
                        continue

                # Choose relevant frames for phrase detection
                log("loop: choosing relevant frames (filtering cloudflare/empty)")
                relevant = choose_relevant_texts(frame_texts)
                log(f"loop: relevant frames count={len(relevant)}")

                if not relevant:
                    log("loop: no relevant content found; closing page and sleeping full CHECK_INTERVAL")
                    try:
                        page.close()
                    except Exception:
                        pass
                    time.sleep(check_interval)
                    continue

                # Phrase detection
                combined_text = "\n\n".join(t for _, t in relevant)
                closed_present = CLOSURE_PHRASE.lower() in combined_text.lower()
                log(f"loop: closure phrase present? {closed_present}")

                if previous_closed_state is None:
                    previous_closed_state = closed_present
                    log(f"loop: initial previous_closed_state={previous_closed_state}")

                # Notification trigger
                if previous_closed_state and not closed_present:
                    log("loop: closure phrase DISAPPEARED -> preparing Telegram notification")
                    message = (
                        f"Agenda changed: '{CLOSURE_PHRASE}' is no longer present on the widget at {widget_url}\n"
                        f"Time: {now_ts()}\n"
                        f"Detected frames (snippets):\n"
                    )
                    for url, text in relevant:
                        snippet = (text[:300].replace("\n", " ")) if text else ""
                        message += f"- {url} -> {snippet}\n"

                    try:
                        log("loop: sending Telegram message...")
                        sent_ok = send_telegram(bot_token, chat_id, message)
                        log(f"loop: send_telegram returned {sent_ok}")
                    except Exception as e:
                        log(f"loop: exception while sending Telegram: {e}\n{traceback.format_exc()}")
                        sent_ok = False

                    if sent_ok:
                        previous_closed_state = closed_present
                        log("loop: notification sent; updated previous_closed_state")
                    else:
                        log("loop: notification failed; leaving previous_closed_state to avoid repeated notifications")

                else:
                    previous_closed_state = closed_present
                    log(f"loop: no notification. previous_closed_state={previous_closed_state}")

                # Close page explicitly
                try:
                    log("loop: closing page")
                    page.close()
                except Exception as e:
                    log(f"loop: page.close() error: {e}")

            except KeyboardInterrupt:
                log("KeyboardInterrupt received; exiting loop.")
                break
            except Exception as e:
                log(f"loop: unexpected exception: {e}\n{traceback.format_exc()}")
                try:
                    if page:
                        page.close()
                except Exception:
                    pass
            finally:
                # Always sleep full check_interval before next cycle
                log(f"loop: cycle complete — sleeping full CHECK_INTERVAL {check_interval}s")
                time.sleep(check_interval)

    finally:
        try:
            if browser:
                log("closing browser before exit")
                browser.close()
                log("browser closed")
        except Exception as e:
            log(f"error closing browser: {e}")

    log("monitor exited")


if __name__ == "__main__":
    main()
