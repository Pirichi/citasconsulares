#!/usr/bin/env python3
"""
main.py - Bookitit widget monitor using CloakBrowser (wraps Playwright), safe frame traversal,
Cloudflare/transient-state filtering, and Telegram notifications.

Environment variables:
- WIDGET_URL (required): URL to open that contains the Bookitit widget (page with iframes).
- TELEGRAM_BOT_TOKEN (required to send notifications)
- TELEGRAM_CHAT_ID (required to send notifications)
- CHECK_INTERVAL (optional, seconds, default=30)
- BROWSER_EXECUTABLE_PATH (optional): path to CloakBrowser/Chrome binary to use (passed via env to cloakbrowser if needed)
- HEADLESS (optional, "1" or "0"; default "1")
- NAV_TIMEOUT (optional, navigation timeout in ms; default 60000)
"""

import os
import sys
import time
import traceback
import requests
from datetime import datetime
from typing import List, Tuple

# Use CloakBrowser's launch as requested
from cloakbrowser import launch

# Keep the Playwright TimeoutError import for robust timeout handling,
# CloakBrowser wraps Playwright so these exceptions remain relevant.
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

# Constants
CLOSURE_PHRASE = "No hay horas disponibles"
DEFAULT_CHECK_INTERVAL = 30
DEFAULT_NAV_TIMEOUT_MS = 60000

# Cloudflare / transient detection phrases (case-insensitive)
CLOUDFLARE_INDICATORS = [
    "checking your browser",
    "please enable javascript and cookies to continue",
    "ddos protection by cloudflare",
    "cf-chl-bypass",
    "cloudflare",
    "checking your browser before accessing",
    "verifying you are human",
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
    """
    Collects text content from all frames (including main frame).
    Returns a list of tuples (frame_url, text_content).
    Extraction is defensive: if inner_text fails, falls back to content() with crude tag stripping.
    """
    results = []
    seen_frames = set()
    try:
        frames = page.frames
    except Exception:
        # In rare cases page.frames might fail; return empty list
        return results

    for frame in frames:
        try:
            frame_id = (frame.url, frame.name)
            if frame_id in seen_frames:
                continue
            seen_frames.add(frame_id)

            text = ""
            # Prefer a lightweight body locator inner_text
            try:
                body = frame.locator("body")
                if body:
                    # short timeout to avoid stalling on weird frames
                    text = body.inner_text(timeout=2000)
                else:
                    text = ""
            except PlaywrightTimeoutError:
                text = ""
            except Exception:
                text = ""

            # Fallback: try frame.content() and strip tags crudely
            if not text:
                try:
                    html = frame.content()
                    # crude tag stripper: remove tags, keep spacing
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
            # continue with next frame
            continue

    return results


def choose_relevant_texts(frame_texts: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
    """
    From extracted frame texts, select non-cloudflare, non-empty texts which likely represent the widget content.
    Prefer frames whose URL contains 'bookitit' or 'bookitit.' to reduce false positives.
    If such frames exist, return only those. Otherwise, return all non-cloudflare, non-empty frames.
    """
    filtered = []
    for url, text in frame_texts:
        if not text:
            continue
        if is_cloudflare_text(text):
            continue
        filtered.append((url, text))

    if not filtered:
        return []

    # Prefer bookitit frames if present
    bookitit_frames = [t for t in filtered if "bookitit" in (t[0] or "").lower()]
    if bookitit_frames:
        return bookitit_frames

    # Otherwise return filtered frames
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


def safe_navigate(page, url: str, timeout_ms: int):
    """
    Navigate and wait for network idle; catch timeouts and continue.
    """
    try:
        page.goto(url, wait_until="networkidle", timeout=timeout_ms)
    except PlaywrightTimeoutError:
        log(f"Navigation timeout after {timeout_ms}ms for URL: {url} — continuing to extract available content.")
    except Exception as e:
        log(f"Navigation exception for URL {url}: {e}")


def main():
    widget_url = os.environ.get("WIDGET_URL")
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    check_interval = int(os.environ.get("CHECK_INTERVAL", DEFAULT_CHECK_INTERVAL))
    exec_path = os.environ.get("BROWSER_EXECUTABLE_PATH")  # optional CloakBrowser path
    headless = os.environ.get("HEADLESS", "1") != "0"
    nav_timeout = int(os.environ.get("NAV_TIMEOUT", DEFAULT_NAV_TIMEOUT_MS))

    if not widget_url:
        log("ERROR: WIDGET_URL environment variable is required.")
        sys.exit(2)
    if not bot_token or not chat_id:
        log("ERROR: TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are required to send notifications.")
        # Exit to avoid accidental runs without notification capability.
        sys.exit(2)

    log("Starting Bookitit widget monitor.")
    log(f"WIDGET_URL: {widget_url}")
    log(f"CHECK_INTERVAL: {check_interval}s, HEADLESS: {headless}, NAV_TIMEOUT: {nav_timeout}ms")

    previous_closed_state = None  # None = unknown, True = closed phrase present, False = phrase absent

    # Start CloakBrowser
    browser = None
    try:
        # Pass executable path via environment if provided; cloakbrowser may respect env vars for custom binaries.
        if exec_path:
            # Some cloakbrowser installs accept BROWSER_PATH or similar; set a common env variable just in case.
            os.environ.setdefault("BROWSER_EXECUTABLE_PATH", exec_path)
            log(f"Set BROWSER_EXECUTABLE_PATH env to: {exec_path}")

        log("Launching CloakBrowser...")
        # Use the specialized launch API requested
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
            page = None
            try:
                # Create a fresh page each cycle to avoid stale frames and carry-over state
                try:
                    page = browser.new_page()
                except Exception as e:
                    log(f"Failed to create new page in browser: {e}\n{traceback.format_exc()}")
                    # If we cannot create a page, wait and retry in next cycle
                    elapsed = time.time() - cycle_start
                    sleep_time = max(0, check_interval - elapsed)
                    log(f"Sleeping {sleep_time:.1f}s before next attempt.")
                    time.sleep(sleep_time)
                    continue

                # Optionally set viewport and user agent for more consistent rendering
                try:
                    page.set_viewport_size({"width": 1280, "height": 800})
                    page.set_extra_http_headers(
                        {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                                       "Chrome/115.0.0.0 Safari/537.36"}
                    )
                except Exception:
                    # Not all cloakbrowser/browser wrappers may support these methods; ignore failures
                    pass

                try:
                    safe_navigate(page, widget_url, nav_timeout)
                    # Short delay to let dynamic frames populate
                    time.sleep(2)
                except Exception as e:
                    log(f"Navigation error: {e}")

                try:
                    frame_texts = extract_frame_texts(page)
                    if not frame_texts:
                        log("No frames or no extractable content found on page.")
                    else:
                        log(f"Extracted {len(frame_texts)} frames/texts. Sample (first 3):")
                        for url, text in frame_texts[:3]:
                            sample = (text[:160] + "...") if len(text) > 160 else text
                            log(f" - frame url={url} text_sample={sample!r}")

                    relevant = choose_relevant_texts(frame_texts)

                    if not relevant:
                        # If we could not find any non-cloudflare non-empty frame content, ignore this cycle
                        log("Only Cloudflare/empty content detected or no relevant frames; ignoring this cycle to avoid false positives.")
                        # Do not update previous_closed_state to avoid false positives caused by transient protections
                        elapsed = time.time() - cycle_start
                        sleep_time = max(0, check_interval - elapsed)
                        log(f"Sleeping {sleep_time:.1f}s before next check.")
                        time.sleep(sleep_time)
                        continue

                    # Combine texts into a single blob for phrase search, but maintain per-frame info for logging
                    combined_text = "\n\n".join(t for _, t in relevant)

                    # Strict presence check: we consider the closure phrase present if it's found (case-insensitive)
                    closed_present = CLOSURE_PHRASE.lower() in combined_text.lower()

                    log(f"Closure phrase present in relevant content? {closed_present}")

                    # Initialize previous state if unknown
                    if previous_closed_state is None:
                        previous_closed_state = closed_present
                        log(f"Initial state recorded: closed_present={closed_present}")

                    # Trigger notification only when previous_closed_state True and now False (phrase disappeared)
                    if previous_closed_state and not closed_present:
                        log("Detected CLOSURE PHRASE DISAPPEARED -> possible openings/agenda change. Preparing notification.")
                        message = (
                            f"Agenda changed: '{CLOSURE_PHRASE}' is no longer present on the widget at {widget_url}\n"
                            f"Time: {now_ts()}\n"
                            f"Detected frames:\n"
                        )
                        # Include frame URLs for debugging context
                        for url, text in relevant:
                            snippet = text[:200].replace("\n", " ")
                            message += f"- {url} -> {snippet!s}\n"

                        # Send Telegram notification (safe wrapper)
                        try:
                            ok = send_telegram(bot_token, chat_id, message)
                            if not ok:
                                log("Telegram send reported failure; not changing previous state to avoid repeated notifications until verified.")
                            else:
                                # Update state to avoid repeated notifications for same event
                                previous_closed_state = closed_present
                        except Exception as e:
                            log(f"Error while sending Telegram notification: {e}\n{traceback.format_exc()}")

                    else:
                        # No trigger case: update previous state normally
                        previous_closed_state = closed_present
                        log(f"No notification. previous_closed_state updated to {previous_closed_state}")

                except Exception as e:
                    log(f"Error while extracting or analyzing frames: {e}\n{traceback.format_exc()}")
                finally:
                    try:
                        if page:
                            page.close()
                    except Exception:
                        pass

            except KeyboardInterrupt:
                log("KeyboardInterrupt received: shutting down gracefully.")
                break
            except Exception as e:
                log(f"Unexpected error in monitoring loop: {e}\n{traceback.format_exc()}")

            # Sleep for the configured interval minus time already spent
            elapsed = time.time() - cycle_start
            sleep_time = max(0, check_interval - elapsed)
            log(f"Cycle complete. Sleeping {sleep_time:.1f}s before next check.")
            time.sleep(sleep_time)

    finally:
        # cleanup browser
        try:
            if browser:
                browser.close()
                log("Browser closed.")
        except Exception:
            log("Error while closing browser (ignored).")

    log("Monitor exited.")


if __name__ == "__main__":
    main()
