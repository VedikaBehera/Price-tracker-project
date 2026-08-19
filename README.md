# Price Fluctuation Tracker

Tracks prices for a set of products on Blinkit, Zepto, and Instamart (and can
be extended to D2C brand sites) and sends a Telegram message whenever a
tracked product's price changes — up or down — from the last check.

## How it works

- `products.json` — the list of products to track (name, platform, URL).
- `track_prices.py` — loads each product page with Playwright, extracts the
  current price, compares it to the last recorded price in
  `price_history.json`, and sends a Telegram alert if it changed.
- `.github/workflows/price_check.yml` — runs the script every hour via GitHub
  Actions and commits the updated `price_history.json` back to the repo so
  price history persists between runs.

## Setup (one-time)

1. Add two repository secrets (Settings → Secrets and variables → Actions):
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
2. Push these files to your repo.
3. Go to the **Actions** tab → you should see "Price Check" listed. You can
   trigger it manually first via "Run workflow" to test before waiting for
   the schedule.

## Adding more products

Edit `products.json` and add an entry like:

```json
{
  "name": "Product name here",
  "platform": "blinkit",
  "url": "https://..."
}
```

Get the URL by opening the product page in the app/website and copying the
link (mobile app share button, or the address bar on desktop/web).

## Known limitations

- Blinkit, Zepto, and Instamart don't have public APIs and change their page
  structure periodically. The price extraction in `track_prices.py` uses a
  best-effort heuristic (finds rupee amounts on the page and picks the
  smallest of the first few, since MRP is usually struck through next to a
  lower selling price). If a product stops updating, check the Action's log
  output — it will print if a price couldn't be extracted, which usually
  means the site layout changed and the heuristic needs adjusting.
- Prices on these platforms are pincode/location-specific. The script
  attempts to fill in a pincode field if a location prompt appears, but this
  is best-effort — if prices look consistently for the wrong location, this
  step may need tuning per platform.
- Every price change (drop or increase) triggers a notification, since the
  goal right now is understanding fluctuation patterns rather than hitting a
  fixed target price.
