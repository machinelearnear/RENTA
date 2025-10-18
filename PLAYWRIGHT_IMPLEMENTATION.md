# Zonaprop Playwright Implementation - Complete Guide

## Overview

This document describes the new **Playwright-based scraping approach** for Zonaprop that successfully bypasses Cloudflare protection. This implementation is now integrated into RENTA and can be used alongside or instead of the existing cloudscraper approach.

## What Was Implemented

### 1. Core Components

#### ZonapropPlaywrightClient (`renta/zonaprop_playwright_client.py`)
- Full-featured Playwright-based scraper
- Uses `playwright-stealth` to bypass Cloudflare
- Intercepts browser API responses for clean JSON data
- Handles pagination automatically
- Comprehensive error handling and retry logic
- Browser session reuse for performance

#### Async Wrapper (`renta/utils/async_scraper_wrapper.py`)
- Unified interface for both scraping methods
- Automatically selects Playwright or cloudscraper based on config
- Provides both async and sync interfaces

### 2. Configuration

New configuration section in `default_config.yaml`:

```yaml
zonaprop:
  scraping:
    use_playwright: false  # Set to true to enable Playwright
    # ... existing config ...
  playwright:
    headless: false  # Visible browser works better
    browser_timeout_seconds: 60
    navigation_timeout_seconds: 60
    cloudflare_wait_seconds: 10
    page_load_delay_seconds: 3
    retry_delay_base_seconds: 5
    viewport:
      width: 1920
      height: 1080
    user_agent: "Mozilla/5.0 ..."
    locale: "es-AR"
    timezone: "America/Argentina/Buenos_Aires"
    reuse_browser_session: true
    session_max_pages: 50
```

### 3. Dependencies

Added to `requirements.txt`:
```
playwright>=1.40.0
playwright-stealth>=1.0.0
```

## Installation

### 1. Install Python Dependencies

```bash
# Install RENTA with new dependencies
pip install -e .

# Or update existing installation
pip install playwright>=1.40.0 playwright-stealth>=1.0.0
```

### 2. Install Playwright Browsers

```bash
# Install Chromium browser for Playwright
playwright install chromium

# This downloads ~130MB and is required for Playwright to work
```

### 3. Verify Installation

```bash
# Run the integration test
python test_playwright_integration.py
```

## Usage

### Option 1: Via Configuration (Recommended)

Edit your `config.yaml`:

```yaml
zonaprop:
  scraping:
    use_playwright: true  # Enable Playwright
```

Then use RENTA normally:

```python
from renta.config import ConfigManager
from renta.utils.async_scraper_wrapper import scrape_zonaprop_sync

config = ConfigManager()  # Loads config.yaml

# Automatically uses Playwright if enabled in config
df = scrape_zonaprop_sync(
    "https://www.zonaprop.com.ar/departamentos-venta-capital-federal.html",
    config,
    max_pages=5
)

print(f"Scraped {len(df)} properties")
```

### Option 2: Direct Async Usage

Use the Playwright client directly in async code:

```python
import asyncio
from renta.config import ConfigManager
from renta.zonaprop_playwright_client import ZonapropPlaywrightClient

async def scrape_properties():
    config = ConfigManager()

    async with ZonapropPlaywrightClient(config) as client:
        df = await client.scrape_search_results(
            "https://www.zonaprop.com.ar/departamentos-venta-palermo.html",
            max_pages=10
        )
        return df

# Run async code
df = asyncio.run(scrape_properties())
```

### Option 3: Async Wrapper

For flexibility between Playwright and cloudscraper:

```python
from renta.utils.async_scraper_wrapper import scrape_zonaprop_async, scrape_zonaprop_sync

# Sync wrapper (creates event loop)
df = scrape_zonaprop_sync(url, config, max_pages=5)

# Async wrapper (for use in async functions)
async def my_function():
    df = await scrape_zonaprop_async(url, config, max_pages=5)
```

## How It Works

### Architecture

```
User Request
    ↓
Config Check (use_playwright?)
    ↓
[YES] → ZonapropPlaywrightClient
    ↓
1. Launch Chromium with stealth
2. Navigate to Zonaprop search page
3. Wait for Cloudflare challenge (10s)
4. Intercept /rplis-api/postings responses
5. Extract clean JSON data
6. Handle pagination
7. Return normalized DataFrame

[NO] → ZonapropScraper (existing cloudscraper)
```

### Response Interception

The key innovation is **response interception**:

1. Browser navigates to Zonaprop search page
2. Zonaprop's JavaScript makes API calls to `/rplis-api/postings`
3. Playwright intercepts these responses
4. We extract the clean JSON data
5. No HTML parsing needed!

```python
# Simplified version of the interception logic
async def handle_response(response):
    if '/rplis-api/postings' in response.url:
        data = await response.json()  # Clean JSON!
        intercepted_responses.append(data)

page.on('response', handle_response)
await page.goto(search_url)
```

### Cloudflare Bypass

The implementation bypasses Cloudflare using:

1. **playwright-stealth**: Removes automation indicators
2. **Realistic browser fingerprint**: Viewport, user-agent, locale, timezone
3. **Headed mode**: Visible browser (works better than headless)
4. **Wait period**: 10 seconds for challenge to complete
5. **Genuine browser**: Real Chromium, not headless detection

## Performance Comparison

| Method | Speed | Reliability | Cloudflare Bypass | Data Quality |
|--------|-------|-------------|-------------------|--------------|
| cloudscraper | ⚡⚡⚡ Fast | ❌ Often blocked | ❌ Failed | ⭐⭐ HTML parsing |
| Playwright | ⚡ Medium | ✅ Reliable | ✅ Success | ⭐⭐⭐ Clean JSON |

**Recommendation**: Use Playwright for production scraping, cloudscraper for quick tests (if it works).

## Configuration Guide

### Essential Settings

```yaml
zonaprop:
  playwright:
    headless: false  # IMPORTANT: Keep false for reliability
    cloudflare_wait_seconds: 10  # Wait for challenge
    page_load_delay_seconds: 3   # Wait for API calls
```

### Performance Tuning

```yaml
zonaprop:
  playwright:
    reuse_browser_session: true  # Faster (reuses browser)
    session_max_pages: 50        # Refresh after N pages
```

### Troubleshooting

```yaml
zonaprop:
  playwright:
    cloudflare_wait_seconds: 15  # Increase if challenges fail
    browser_timeout_seconds: 90  # Increase for slow connections
    retry_delay_base_seconds: 10  # Longer delays between retries
```

## Testing

### Run Integration Tests

```bash
# Full integration test
python test_playwright_integration.py

# Expected output:
# ✓ Direct Client Test: PASSED
# ✓ Async Wrapper Test: PASSED
# 🎉 ALL TESTS PASSED!
```

### Manual Test

```bash
# Simple test script
python -c "
from renta.config import ConfigManager
from renta.utils.async_scraper_wrapper import scrape_zonaprop_sync

config = ConfigManager()
config.set('zonaprop.scraping.use_playwright', True)

df = scrape_zonaprop_sync(
    'https://www.zonaprop.com.ar/departamentos-venta-palermo.html',
    config,
    max_pages=1
)

print(f'Scraped {len(df)} properties')
print(df.head())
"
```

## Troubleshooting

### Issue: "Playwright not installed"

```bash
# Solution: Install playwright browsers
playwright install chromium
```

### Issue: "Timeout waiting for page"

```yaml
# Solution: Increase timeouts in config
zonaprop:
  playwright:
    navigation_timeout_seconds: 90
    cloudflare_wait_seconds: 15
```

### Issue: "Still getting Cloudflare blocks"

Possible causes:
1. **Headless mode enabled** → Set `headless: false`
2. **Not waiting long enough** → Increase `cloudflare_wait_seconds`
3. **Network issues** → Check internet connection
4. **Too many requests** → Increase delays, reduce `session_max_pages`

### Issue: "Browser keeps opening"

This is normal! Headed mode (visible browser) is more reliable.

To minimize:
```yaml
zonaprop:
  playwright:
    reuse_browser_session: true  # Reuses browser
    session_max_pages: 100  # Fewer refreshes
```

### Issue: "No properties returned"

Check:
1. Search URL is valid
2. Cloudflare challenge completed (check browser window)
3. API responses were intercepted (check logs)

## Migration Guide

### Phase 1: Parallel Testing (Current)

Both methods available, cloudscraper is default:

```yaml
zonaprop:
  scraping:
    use_playwright: false  # Default: cloudscraper
```

### Phase 2: Enable Playwright

When ready, switch to Playwright:

```yaml
zonaprop:
  scraping:
    use_playwright: true  # Use Playwright
```

### Phase 3: Production

Monitor and adjust configuration based on:
- Success rate
- Speed requirements
- Cloudflare challenges

## Advanced Usage

### Custom Browser Configuration

```python
from renta.zonaprop_playwright_client import ZonapropPlaywrightClient

# Override config for specific needs
config.set("zonaprop.playwright.headless", True)  # Try headless
config.set("zonaprop.playwright.viewport.width", 2560)  # Bigger viewport

async with ZonapropPlaywrightClient(config) as client:
    df = await client.scrape_search_results(url)
```

### Parallel Scraping (Future)

Not yet implemented, but possible:

```python
# Future enhancement
async def scrape_multiple_searches():
    searches = [url1, url2, url3]

    tasks = [scrape_zonaprop_async(url, config) for url in searches]
    results = await asyncio.gather(*tasks)

    return pd.concat(results)
```

## File Reference

| File | Purpose |
|------|---------|
| `renta/zonaprop_playwright_client.py` | Main Playwright client implementation |
| `renta/utils/async_scraper_wrapper.py` | Unified async/sync wrapper |
| `renta/data/default_config.yaml` | Configuration defaults |
| `test_playwright_integration.py` | Integration tests |
| `test_playwright_zonaprop.py` | Original proof-of-concept |
| `PLAYWRIGHT_CLOUDFLARE_FINDINGS.md` | Investigation findings |
| `ZONAPROP_API_INVESTIGATION.md` | API endpoint investigation |

## Support and Debugging

### Enable Debug Logging

```yaml
logging:
  level: "DEBUG"  # Verbose logging
```

### Check Browser Automation

The Playwright browser window will:
1. Open (if headless=false)
2. Navigate to Zonaprop
3. Wait for Cloudflare challenge
4. Load search results
5. Close after scraping

Watch the browser to see what's happening.

### Common Log Messages

```
✓ Good signs:
- "Playwright browser launched"
- "Intercepted API response"
- "Scraping complete"

✗ Warning signs:
- "Cloudflare challenge page detected"
- "No API responses intercepted"
- "Retrying page scrape"
```

## Performance Tips

1. **Reuse browser sessions** - Set `reuse_browser_session: true`
2. **Limit pages** - Use `max_pages` parameter
3. **Increase delays slightly** - Reduces blocks
4. **Monitor success rate** - Adjust config based on results

## Future Enhancements

Planned improvements:
- [ ] Headless mode optimization
- [ ] Parallel page scraping
- [ ] Screenshot capture on errors
- [ ] Automatic fallback to manual download
- [ ] Metrics dashboard
- [ ] Proxy support

## Conclusion

The Playwright implementation provides a **reliable, maintainable** solution for scraping Zonaprop that:

✅ Successfully bypasses Cloudflare
✅ Gets clean JSON data
✅ Handles pagination
✅ Includes comprehensive error handling
✅ Integrates seamlessly with existing code
✅ Is production-ready

**Status**: ✅ Ready for use
**Recommended**: ✅ Yes, for production scraping

---

**Questions or Issues?**

Check the logs, review this guide, and test with `test_playwright_integration.py`.
