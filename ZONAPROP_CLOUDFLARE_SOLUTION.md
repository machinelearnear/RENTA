# Zonaprop Cloudflare Bypass Solution

> **⚠️ EXPERIMENTAL / ARCHIVED**
>
> This document describes experimental approaches to bypassing Cloudflare on Zonaprop.
> **All automated approaches failed** - Cloudflare Turnstile successfully detected all attempts.
> The implementation code has been moved to `renta/experimental/zonaprop/`.
>
> **✅ Recommended alternative**: Use the **MercadoLibre provider** instead (see `examples/mercadolibre_*.py`).
> MercadoLibre provides a public API with no anti-bot protection and is Argentina's largest marketplace.

## Problem

Zonaprop uses Cloudflare protection to prevent automated scraping. When accessing the site with Playwright, Cloudflare presents a CAPTCHA challenge (Turnstile) that blocks automated access.

## Solution: Cookie-Based Authentication

Instead of trying to bypass Cloudflare automatically (which is unreliable and eventually fails), we implement a **hybrid approach**:

1. **User manually solves CAPTCHA once** using a browser window
2. **Cookies are saved** for future automated sessions
3. **Automated scraping uses saved cookies** (valid for 24 hours)
4. **Re-authenticate when cookies expire**

This approach is:
- ✅ **More reliable** than automated bypass attempts
- ✅ **Respects Cloudflare** (legitimate human verification)
- ✅ **Simple to use** (one manual step, then automated)
- ✅ **Well-supported** by industry research (2025 best practices)

## Usage

### First-Time Setup (Manual Authentication)

Run the authentication tool to open a browser and solve the Cloudflare challenge:

```bash
python -m renta.utils.cloudflare_auth auth
```

This will:
1. Open a visible browser window to Zonaprop
2. Wait for you to manually solve the Cloudflare challenge (if it appears)
3. Save valid cookies to `~/.renta/zonaprop_cookies.json`
4. Auto-close after 2 minutes (or press Ctrl+C when ready)

**What to do in the browser:**
- If you see a Cloudflare challenge page: Complete the CAPTCHA
- Wait until you see property listings (the main Zonaprop page)
- Press Ctrl+C in the terminal to close the browser and save cookies

### Automated Scraping

Once authenticated, use the analyzer normally:

```python
from renta import RealEstateAnalyzer

analyzer = RealEstateAnalyzer()

# Cookies are automatically loaded!
properties = analyzer.scrape_zonaprop(
    "https://www.zonaprop.com.ar/departamentos-venta-palermo.html"
)

print(f"Scraped {len(properties)} properties")
```

### Checking Cookie Status

To check if your cookies are still valid:

```bash
python -m renta.utils.cloudflare_auth check
```

Expected output:
```
✓ Valid cookies found (12 cookies)
  Age: 2.3 hours
  File: /Users/username/.renta/zonaprop_cookies.json
```

### Clearing Cookies

To delete saved cookies (forces re-authentication):

```bash
python -m renta.utils.cloudflare_auth clear
```

### Cookie Expiration

Cookies are valid for **24 hours**. After that:

1. You'll see a warning in the logs:
   ```
   WARNING: No valid Cloudflare cookies found
   ```

2. Simply re-authenticate:
   ```bash
   python -m renta.utils.cloudflare_auth auth
   ```

## How It Works

### Architecture

```
┌─────────────────┐
│  User runs:     │
│  auth auth      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Opens browser   │
│ (visible)       │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ User solves     │
│ CAPTCHA         │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Save cookies to │
│ ~/.renta/       │
└─────────────────┘

Later, automated scraping:

┌─────────────────┐
│ analyzer.       │
│ scrape_zonaprop │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Load cookies    │
│ from ~/.renta/  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Apply cookies   │
│ to Playwright   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Scrape without  │
│ Cloudflare      │
│ challenge!      │
└─────────────────┘
```

### Implementation Details

**CloudflareAuthManager** (`renta/utils/cloudflare_auth.py`):
- Manages cookie persistence and loading
- Provides `authenticate_manual()` for browser-based auth
- Checks cookie expiration (24-hour TTL)
- Applies cookies to Playwright browser contexts

**Integration** (`renta/zonaprop_playwright_client.py`):
- Automatically initializes `CloudflareAuthManager`
- Loads cookies when creating browser context
- Logs warnings if cookies are missing/expired

### Cookie Storage

Cookies are stored in JSON format:

```json
{
  "cookies": [
    {
      "name": "cf_clearance",
      "value": "...",
      "domain": ".zonaprop.com.ar",
      "path": "/",
      "expires": 1234567890,
      "httpOnly": true,
      "secure": true
    },
    ...
  ],
  "timestamp": 1234567890.123,
  "domain": "zonaprop.com.ar"
}
```

Location: `~/.renta/zonaprop_cookies.json`

## Research & References

This solution is based on 2025 industry best practices for Cloudflare bypass:

1. **Residential proxies + manual CAPTCHA** is the most reliable approach
2. **Cookie reuse** is recommended by ZenRows, Bright Data, and Apify
3. **playwright-stealth** alone is insufficient for modern Cloudflare (Turnstile)
4. **Automated bypass tools** (like undetected-chromedriver) are cat-and-mouse games

### Sources:
- [Kameleo: How to Bypass Cloudflare with Playwright in 2025](https://kameleo.io/blog/how-to-bypass-cloudflare-with-playwright)
- [ZenRows: Playwright Cloudflare Bypass 2025](https://www.zenrows.com/blog/playwright-cloudflare-bypass)
- [Apify: How to bypass Cloudflare (updated for 2025)](https://blog.apify.com/bypass-cloudflare/)

## Troubleshooting

### "No valid Cloudflare cookies found"

**Solution**: Run authentication tool:
```bash
python -m renta.utils.cloudflare_auth auth
```

### "Cloudflare challenge detected"

**Solution**: Cookies expired or invalid. Re-authenticate:
```bash
python -m renta.utils.cloudflare_auth clear
python -m renta.utils.cloudflare_auth auth
```

### Browser doesn't open

**Solution**: Check Playwright installation:
```bash
playwright install chromium
```

### Cookies saved but still getting Cloudflare challenge

**Possible causes**:
1. Cookies expired (> 24 hours old) - re-authenticate
2. IP address changed - Cloudflare tracks IP + cookies
3. Cloudflare updated detection - may need to re-authenticate more frequently

## Alternative Approaches Considered

### 1. ❌ Automated Bypass (playwright-stealth only)
- **Problem**: Cloudflare Turnstile detects playwright-stealth
- **Result**: CAPTCHA challenge page, no data extracted

### 2. ❌ undetected-chromedriver
- **Problem**: Python package for Selenium, not Playwright
- **Problem**: Still cat-and-mouse game with Cloudflare
- **Decision**: Cookie approach more reliable

### 3. ❌ Paid Scraping Services
- **Problem**: Costs money (Bright Data, ScraperAPI)
- **Decision**: Manual auth + cookies is free and reliable

### 4. ✅ Cookie-Based Manual Auth (CHOSEN)
- **Advantages**: Reliable, free, respects Cloudflare
- **Trade-off**: Requires manual interaction once per day
- **Perfect for**: Personal projects, research, low-frequency scraping

## Configuration

The Cloudflare auth manager uses the same Playwright configuration from `config.yaml`:

```yaml
zonaprop:
  playwright:
    headless: false  # Must be false for manual CAPTCHA solving
    viewport:
      width: 1920
      height: 1080
    user_agent: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    locale: "es-AR"
    timezone: "America/Argentina/Buenos_Aires"
```

## Future Improvements

1. **Automatic cookie refresh**: Detect when cookies are about to expire and prompt user
2. **Browser session sharing**: Keep browser open across multiple scraping sessions
3. **Multi-account support**: Save cookies for different Zonaprop accounts
4. **Proxy rotation**: Combine with residential proxies for higher volumes

## Summary

The cookie-based authentication approach provides a **reliable, sustainable solution** for bypassing Cloudflare protection on Zonaprop. While it requires occasional manual interaction, it's far more reliable than automated bypass attempts and respects the site's security measures.

**Key takeaway**: One manual step (every 24 hours) enables fully automated scraping for the rest of the day.
