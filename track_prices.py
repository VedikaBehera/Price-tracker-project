"""
Price fluctuation tracker for Blinkit / Zepto / Instamart / D2C sites.
Loads each product page with Playwright (to handle JS-rendered prices),
extracts the current price, compares to the last known price stored in
price_history.json, and sends a Telegram message on ANY change (up or down).

Run via GitHub Actions on a schedule. The workflow commits the updated
price_history.json back to the repo so state persists between runs.
"""

import json
import os
import re
import sys
from datetime import datetime, timezone

import requests
from playwright.sync_api import sync_playwright

PRODUCTS_FILE = "products.json"
HISTORY_FILE = "price_history.json"

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# Pincode used for quick-commerce location context.
PINCODE = "500089"

# Rough regex to catch rupee amounts like ₹1,199 or Rs. 449 or INR 80
PRICE_PATTERN = re.compile(r"(?:₹|Rs\.?|INR)\s?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{1,2})?)")


def load_json(path, default):
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return default


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def send_telegram(message: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Missing Telegram credentials, skipping notification.")
        print(message)
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        resp = requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": message}, timeout=15)
        if not resp.ok:
            print(f"Telegram send failed: {resp.status_code} {resp.text}")
    except Exception as e:
        print(f"Telegram send error: {e}")


def extract_price_from_text(text: str):
    """
    Best-effort price extraction: finds all rupee-amount matches on the page
    and returns the smallest plausible one that's not obviously a MRP strike-through,
    falling back to the first match found. This is heuristic and may need tuning
    per-site if a page's layout changes.
    """
    matches = PRICE_PATTERN.findall(text)
    if not matches:
        return None
    values = []
    for m in matches:
        try:
            values.append(float(m.replace(",", "")))
        except ValueError:
            continue
    if not values:
        return None
    # Heuristic: the "current" price shown to a buyer is usually the smallest
    # of the first few rupee amounts on the page (MRP is usually struck-through
    # and listed alongside a lower selling price).
    return min(values[:6]) if len(values) >= 2 else values[0]


def fetch_price(page, url: str, platform: str):
    page.goto(url, timeout=45000, wait_until="domcontentloaded")
    page.wait_for_timeout(4000)  # let JS render price widgets

    # Try to set pincode/location context for quick-commerce sites if a
    # location prompt appears. This is best-effort and silently ignored if
    # no such prompt is found (e.g. location already set via cookies).
    try:
        location_input = page.locator("input[placeholder*='pincode' i], input[placeholder*='location' i]")
        if location_input.count() > 0:
            location_input.first.fill(PINCODE)
            page.wait_for_timeout(1500)
    except Exception:
        pass

    text = page.content()
    price = extract_price_from_text(text)
    return price


def main():
    products = load_json(PRODUCTS_FILE, [])
    history = load_json(HISTORY_FILE, {})

    if not products:
        print("No products configured.")
        return

    alerts = []
    now = datetime.now(timezone.utc).isoformat()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
        )
        page = context.new_page()

        for item in products:
            key = f"{item['platform']}::{item['name']}"
            try:
                price = fetch_price(page, item["url"], item["platform"])
            except Exception as e:
                print(f"Failed to fetch {key}: {e}")
                continue

            if price is None:
                print(f"Could not extract price for {key}, page structure may have changed.")
                continue

            last = history.get(key)
            last_price = last["price"] if last else None

            if last_price is None:
                # First time seeing this product, just record it.
                history[key] = {"price": price, "last_checked": now}
                print(f"Initialized {key} at ₹{price}")
                continue

            if price != last_price:
                direction = "dropped" if price < last_price else "increased"
                pct = abs(price - last_price) / last_price * 100
                alerts.append(
                    f"{item['name']} ({item['platform'].title()})\n"
                    f"Price {direction}: ₹{last_price:.0f} → ₹{price:.0f} ({pct:.1f}%)\n"
                    f"{item['url']}"
                )
                history[key] = {"price": price, "last_checked": now}
            else:
                history[key]["last_checked"] = now

        browser.close()

    save_json(HISTORY_FILE, history)

    if alerts:
        message = "Price change detected:\n\n" + "\n\n".join(alerts)
        send_telegram(message)
        print(message)
    else:
        print("No price changes this run.")


if __name__ == "__main__":
    main()
