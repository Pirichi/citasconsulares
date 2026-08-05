```python name=main.py
#!/usr/bin/env python3
"""
main.py - Bookitit widget monitor using CloakBrowser.

This variant launches CloakBrowser per-check and closes it at the end of each cycle
to avoid accumulating Chromium state and to keep memory usage bounded on constrained hosts.

Behavior:
- Each loop iteration launches CloakBrowser, creates a page, navigates (wait_until="domcontentloaded"),
  extracts frame texts (with per-frame timeouts and fallbacks), detects Cloudflare, stabilizes,
  checks the closure phrase "No hay horas disponibles", and optionally sends a Telegram message
  when that phrase disappears.
- The browser is closed in every cycle (finally block) and references are cleared + gc.collect()
  is called to help free memory before sleeping for CHECK_INTERVAL seconds.
- Detailed logs are emitted for each step so you can see precisely where cycles spend time.

Environment variables:
- WIDGET_URL (required)
- TELEGRAM_BOT_TOKEN (required)
- TELEGRAM_CHAT_ID (required)
- CHECK_INTERVAL (optional, seconds; default 60)
- BROWSER_EXECUTABLE_PATH (optional): path to CloakBrowser/Chrome binary (set as env for cloakbrowser)
- HEADLESS (optional, "1" or "0"; default "1")
- NAV_TIMEOUT (optional, ms; default 60000)
- CLOUDFLARE_STABILIZE_SECONDS (optional; default 8)
- CLOUDFLARE_RETRIES (optional; default 2)
"""

import gc
import os
import sys
import time
import traceback
import requests
from datetime import datetime
from typing import List, Tuple

from cloakbrowser import launch
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, Error as PlaywrightError

# Config / defaults
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
    Extract text from all frames. Uses short per-frame timeouts and a safe evaluate fallback.
    Logs progress to make it easy to see which frame (if any) causes trouble.
    """
    results = []
    try:
        frames = page.frames
    except Exception as e:
        log(f"extract_frame_texts: failed to read page.frames: {e}")
        return results

    log(f"extract_frame_texts: found {len(frames)} frames")
    seen = set()
    for idx, frame in enumerate(frames):
        try:
            url = frame.url or "<no-url>"
            name = frame.name or ""
            key = (url, name)
            if key in seen:
                log(f"extract_frame_texts: skipping duplicate frame {url!r} name={name!r}")
                continue
            seen.add(key)

            log(f"extract_frame_texts: frame #{idx} url={url!r} name={name!r}")
            text = ""

            # Try body.inner_text with a short timeout
            try:
                log(f"extract_frame_texts: attempting body.inner_text timeout={per_frame_timeout_ms}ms")
                body = frame.locator("body")
                if body:
                    text = body.inner_text(timeout=per_frame_timeout_ms)
                    log(f"extract_frame_texts: body.inner_text ok len={len(text)}")
                else:
                    log("extract_frame_texts: no body locator")
                    text = ""
            except PlaywrightTimeoutError:
                log("extract_frame_texts: body.inner_text timed out")
                text = ""
            except PlaywrightError as e:
                log(f"extract_frame_texts: PlaywrightError during inner_text: {e}")
                text = ""
            except Exception as e:
                log(f"extract_frame_texts: error during inner_text: {e}")
                text = ""

            # Fallback: evaluate document.body.innerText (inherits page default timeout)
            if not text:
                try:
                    log("extract_frame_texts: attempting evaluate fallback")
                    text = frame.evaluate("() => document.body ? document.body.innerText : ''")
                    if text:
                        log(f"extract_frame_texts: evaluate ok len={len(text)}")
                    else:
                        log("extract_frame_texts: evaluate returned empty")
                except PlaywrightTimeoutError:
                    log("extract_frame_texts: evaluate timed out")
                    text = ""
                except PlaywrightError as e:
                    log(f"extract_frame_texts: PlaywrightError during evaluate: {e}")
                    text = ""
                except Exception as e:
                    log(f"extract_frame_texts: unexpected evaluate error: {e}")
                    text = ""

            results.append((url, (text or "").strip()))
        except Exception as e:
            log(f"extract_frame_texts: unexpected frame loop error: {e}\n{traceback.format_exc()}")
            continue

    log(f"extract_frame_texts: completed collected {len(results)} entries")
    return results


def choose_relevant_texts(frame_texts: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
    filtered = []
    for url, text in frame_texts:
        if not text:
            continue
        if is_cloudflare_text(text):
            log(f"choose_relevant_texts: filtered cloudflare-like content from {url}")
            continue
        filtered.append((url, text))

    if not filtered:
        return []

    bookitit = [t for t in filtered if "bookitit" in (t[0] or "").lower()]
    if bookitit:
        log(f"choose_relevant_texts: preferring {len(bookitit)} bookitit frames")
        return bookitit

    log(f"choose_relevant_texts: returning {len(filtered)} filtered frames")
    return filtered


def send_telegram(bot_token: str, chat_id: str, message: str) -> bool:
    api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "disable_web_page_preview": True}
    try:
        r = requests.post(api_url, json=payload, timeout=15)
        if r.status_code == 200:
            log("send_telegram: ok")
            return True
        else:
            log(f"send_telegram: failed status={r.status_code} body={r.text}")
            return False
    except Exception as e:
        log(f"send_telegram: exception {e}")
        return False


def safe_navigate(page, url: str, timeout_ms: int) -> bool:
    """
    Use wait_until='domcontentloaded' to avoid waiting forever for networkidle.
    Returns True/False and never raises.
    """
    try:
        log(f"safe_navigate: goto {url!r} timeout={timeout_ms}ms wait_until=domcontentloaded")
        page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        log("safe_navigate: goto returned (domcontentloaded reached or quick return)")
        return True
    except PlaywrightTimeoutError:
        log(f"safe_navigate: timeout after {timeout_ms}ms for {url}")
        return False
    except PlaywrightError as e:
        log(f"safe_navigate: PlaywrightError during goto: {e}")
        return False
    except Exception as e:
        log(f"safe_navigate: unexpected exception during goto: {e}\n{traceback.format_exc()}")
        return False


def perform_check_cycle(
    widget_url: str,
    bot_token: str,
    chat_id: str,
    check_interval: int,
    nav_timeout: int,
    cf_stabilize_seconds: int,
    cf_retries: int,
    headless: bool,
    exec_path: str,
):
    """
    Launch browser, perform one full check, and then close browser.
    Returns True if cycle ran (even if it found nothing), False if browser launch failed.
    """
    browser = None
    try:
        # Provide exec path via env if present (cloakbrowser may read it)
        if exec_path:
            os.environ.setdefault("BROWSER_EXECUTABLE_PATH", exec_path)
            log(f"perform_check_cycle: set BROWSER_EXECUTABLE_PATH={exec_path}")

        log("perform_check_cycle: launching CloakBrowser...")
        browser = launch(headless=headless, humanize=True, human_preset="careful", geoip=False)
        log("perform_check_cycle: CloakBrowser launched")

        page = None
        try:
            log("perform_check_cycle: creating new page...")
            page = browser.new_page()
            log("perform_check_cycle: page created")
        except Exception as e:
            log(f"perform_check_cycle: new_page failed: {e}\n{traceback.format_exc()}")
            return True  # browser exists and will be closed in finally; treat as cycle done

        # Set page timeouts
        try:
            page.set_default_navigation_timeout(nav_timeout)
            page.set_default_timeout(10000)
            log(f"perform_check_cycle: set page timeouts nav={nav_timeout}ms default=10000ms")
        except Exception as e:
            log(f"perform_check_cycle: warning setting timeouts: {e}")

        # Navigate
        nav_ok = safe_navigate(page, widget_url, nav_timeout)

        # Allow a short attachment window for frames
        log("perform_check_cycle: sleeping 2s after navigation for frames to attach")
        time.sleep(2)

        # Extract frames
        frame_texts = []
        try:
            log("perform_check_cycle: extracting frame texts")
            frame_texts = extract_frame_texts(page)
            log(f"perform_check_cycle: extracted {len(frame_texts)} frames")
        except Exception as e:
            log(f"perform_check_cycle: extract_frame_texts exception: {e}\n{traceback.format_exc()}")
            frame_texts = []

        combined_all = "\n\n".join((t for _, t in frame_texts)) if frame_texts else ""
        detected_cf = is_cloudflare_text(combined_all) or (not nav_ok and not combined_all)
        log(f"perform_check_cycle: detected_cf={detected_cf} nav_ok={nav_ok} frames={len(frame_texts)}")

        # Stabilization if Cloudflare-like or nav failure with empty content
        if detected_cf:
            log("perform_check_cycle: Cloudflare detected; running stabilization retries")
            stabilized = False
            for attempt in range(1, cf_retries + 1):
                log(f"perform_check_cycle: stabilization attempt {attempt}/{cf_retries} sleeping {cf_stabilize_seconds}s")
                time.sleep(cf_stabilize_seconds)
                try:
                    frame_texts = extract_frame_texts(page)
                    log(f"perform_check_cycle: re-extraction returned {len(frame_texts)} frames")
                except Exception as e:
                    log(f"perform_check_cycle: re-extraction error: {e}")
                    frame_texts = []
                combined_all = "\n\n".join((t for _, t in frame_texts)) if frame_texts else ""
                if frame_texts and not is_cloudflare_text(combined_all):
                    log("perform_check_cycle: stabilization successful")
                    stabilized = True
                    break
                else:
                    log("perform_check_cycle: stabilization attempt shows Cloudflare/empty")
            if not stabilized:
                log("perform_check_cycle: stabilization failed; skipping this cycle to avoid false positives")
                try:
                    if page:
                        page.close()
                except Exception:
                    pass
                return True  # cycle completed (no notification), browser will be closed in finally

        # Filter relevant frames
        relevant = choose_relevant_texts(frame_texts)
        log(f"perform_check_cycle: relevant frames count={len(relevant)}")

        if not relevant:
            log("perform_check_cycle: no relevant frames -> end cycle")
            try:
                if page:
                    page.close()
            except Exception:
                pass
            return True

        # Phrase detection
        combined_text = "\n\n".join(t for _, t in relevant)
        closed_present = CLOSURE_PHRASE.lower() in combined_text.lower()
        log(f"perform_check_cycle: closure phrase present? {closed_present}")

        # previous_closed_state is managed by caller; send notification via provided bot if needed.
        # For this per-cycle function we only return the detection result via return value convention.
        # We'll return tuple (True, closed_present, relevant) but to keep signature simple return details below.
        # Close page
        try:
            if page:
                page.close()
        except Exception:
            pass

        return (True, closed_present, relevant)
    except Exception as e:
        log(f"perform_check_cycle: unexpected error: {e}\n{traceback.format_exc()}")
        # Ensure we don't raise to caller; treat as completed cycle
        return True
    finally:
        # Close browser and try to free memory
        try:
            if browser:
                log("perform_check_cycle: closing browser to free memory")
                try:
                    browser.close()
                except Exception as e:
                    log(f"perform_check_cycle: browser.close() exception: {e}")
                # delete reference and collect
                del browser
                gc.collect()
                # small delay to allow subprocesses to exit and kernel to reclaim
                time.sleep(1)
                log("perform_check_cycle: browser closed and garbage collected")
        except Exception as e:
            log(f"perform_check_cycle: error during browser cleanup: {e}")


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
        log("ERROR: WIDGET_URL env required")
        sys.exit(2)
    if not bot_token or not chat_id:
        log("ERROR: TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID required")
        sys.exit(2)

    log("Main monitor starting (per-cycle browser launch).")
    log(f"WIDGET_URL={widget_url} CHECK_INTERVAL={check_interval}s NAV_TIMEOUT={nav_timeout}ms HEADLESS={headless}")
    previous_closed_state = None

    while True:
        cycle_start = time.time()
        log(f"heartbeat: cycle_start={now_ts()} previous_closed_state={previous_closed_state}")

        # perform one cycle with a fresh browser
        try:
            result = perform_check_cycle(
                widget_url=widget_url,
                bot_token=bot_token,
                chat_id=chat_id,
                check_interval=check_interval,
                nav_timeout=nav_timeout,
                cf_stabilize_seconds=cf_stabilize_seconds,
                cf_retries=cf_retries,
                headless=headless,
                exec_path=exec_path,
            )

            # perform_check_cycle returns either True (simple signal) or (True, closed_present, relevant)
            closed_present = None
            relevant = []
            if isinstance(result, tuple) and len(result) == 3:
                _, closed_present, relevant = result
            else:
                # result could be True (cycle ran but no meaningful data), treat as no-op
                log("main: cycle completed without frame result (no change to previous state)")
                # Sleep and continue
                log(f"main: sleeping full CHECK_INTERVAL {check_interval}s")
                time.sleep(check_interval)
                continue

            log(f"main: cycle detection closed_present={closed_present} relevant_count={len(relevant)}")

            # Initialize previous state if unknown
            if previous_closed_state is None:
                previous_closed_state = closed_present
                log(f"main: initial previous_closed_state set to {previous_closed_state}")

            # Trigger notification only when previous was True (closed) and now False (opened)
            if previous_closed_state and (closed_present is False):
                log("main: detected disappearance of closure phrase -> sending notification")
                message = (
                    f"Agenda changed: '{CLOSURE_PHRASE}' is no longer present on the widget at {widget_url}\n"
                    f"Time: {now_ts()}\n"
                    f"Detected frames (snippets):\n"
                )
                for url, text in relevant:
                    snippet = (text[:300].replace("\n", " ")) if text else ""
                    message += f"- {url} -> {snippet}\n"

                try:
                    ok = send_telegram(bot_token, chat_id, message)
                    if ok:
                        previous_closed_state = closed_present
                        log("main: notification sent; updated previous_closed_state")
                    else:
                        log("main: notification failed; keeping previous_closed_state to avoid repeat notifications")
                except Exception as e:
                    log(f"main: exception while sending telegram: {e}\n{traceback.format_exc()}")

            else:
                previous_closed_state = closed_present
                log(f"main: no notification. previous_closed_state updated to {previous_closed_state}")

        except KeyboardInterrupt:
            log("main: KeyboardInterrupt received; exiting")
            break
        except Exception as e:
            log(f"main: unexpected error during cycle: {e}\n{traceback.format_exc()}")

        # Always sleep the full configured check interval between cycles
        log(f"main: cycle finished. Sleeping full CHECK_INTERVAL: {check_interval}s")
        time.sleep(check_interval)

    log("main: monitor exiting")


if __name__ == "__main__":
    main()
```
