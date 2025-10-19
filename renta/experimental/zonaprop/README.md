# experimental zonaprop cloudflare bypass implementations

status: archived / experimental
all automated approaches failed - cloudflare turnstile successfully detected all attempts

recommended alternative: use the mercadolibre provider instead (see examples/mercadolibre_*.py)
mercadolibre provides a public api with no anti-bot protection and is argentina's largest marketplace

## overview

this directory contains experimental implementations for bypassing cloudflare protection on zonaprop. all approaches documented here were tested and ultimately failed due to cloudflare's advanced detection capabilities.

## the problem

zonaprop uses cloudflare turnstile protection to prevent automated scraping. when accessing the site with automated tools, cloudflare presents a captcha challenge that blocks automated access.

## implementations in this directory

### 1. playwright with stealth techniques (playwright_client.py)

enhanced playwright implementation with 30+ anti-detection techniques:
- 30+ browser launch arguments to mask automation
- comprehensive http headers (sec-fetch-*, dnt, etc.)
- javascript injection to override navigator.webdriver
- mock browser properties (plugins, languages, chrome object)
- function.prototype.tostring patching

result: detected by cloudflare - preloaded_state never loads

### 2. undetected-chromedriver (undetected_client.py)

selenium-based implementation using undetected-chromedriver library designed to avoid detection:
- automatically patches chromedriver to avoid detection
- custom browser arguments for stealth
- cookie-based authentication support
- retry logic with exponential backoff

result: detected by cloudflare - same behavior as playwright

### 3. cookie-based authentication (cloudflare_auth.py)

hybrid approach requiring manual intervention:
- user manually solves captcha once using browser window
- cookies saved for future automated sessions (valid for 24 hours)
- automated scraping reuses saved cookies
- re-authentication required when cookies expire

result: unreliable - requires manual intervention, cookies expire frequently

### 4. supporting utilities

- async_scraper_wrapper.py - async wrapper for playwright client
- undetected_scraper_wrapper.py - sync wrapper for undetected client
- manual_download_guide.py - guide for manual html download
- zonaprop_downloader.py - manual download tool
- test_playwright_integration.py - integration tests

## why all approaches failed

cloudflare turnstile uses multiple detection layers:
1. tls fingerprinting - detects automated browsers at connection level
2. behavioral analysis - monitors mouse movements, timing patterns, interaction sequences
3. ip reputation - tracks datacenter/cloud ip addresses
4. browser fingerprinting - detects inconsistencies even with masking
5. challenge solving patterns - detects automated challenge solutions

even the most sophisticated anti-detection tools (playwright-stealth, undetected-chromedriver) are eventually detected as cloudflare continuously updates their detection methods.

## research findings

based on 2025 industry research:
- residential proxies + manual captcha is the most reliable approach
- cookie reuse extends session validity but requires manual re-authentication
- playwright-stealth alone is insufficient for modern cloudflare turnstile
- automated bypass tools (undetected-chromedriver) engage in cat-and-mouse games
- paid scraping services (bright data, scraperapi) work but have ongoing costs

sources:
- kameleo: how to bypass cloudflare with playwright in 2025
- zenrows: playwright cloudflare bypass 2025
- apify: how to bypass cloudflare (updated for 2025)

## attempted solutions timeline

### attempt 1: basic playwright
- added stealth plugins
- result: immediately detected

### attempt 2: enhanced playwright with 30+ arguments
- comprehensive browser masking
- javascript property overriding
- result: detected after page load, no data extracted

### attempt 3: undetected-chromedriver
- specialized selenium library for bypass
- automatic chromedriver patching
- result: same detection as playwright

### attempt 4: cookie-based manual auth
- manual captcha solving
- cookie persistence and reuse
- result: works but requires frequent manual intervention, not truly automated

## technical details

### cookie storage format

cookies saved to ~/.renta/zonaprop_cookies.json:
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
    }
  ],
  "timestamp": 1234567890.123,
  "domain": "zonaprop.com.ar"
}
```

### detection indicators observed

common patterns when cloudflare detects automation:
- page loads but javascript never executes
- window.__preloaded_state__ never appears in html
- timeout after 30+ seconds waiting for page data
- challenge page html containing "checking your browser" text
- ray id error messages in html

## lessons learned

1. cloudflare turnstile is extremely effective against automation (2025)
2. even specialized bypass tools fail consistently
3. manual intervention remains the most reliable approach
4. cookie-based auth extends sessions but isn't sustainable
5. using official apis (like mercadolibre) is the better long-term solution

## recommended alternative

instead of attempting to bypass cloudflare, use the mercadolibre provider:

```python
from renta import RealEstateAnalyzer

analyzer = RealEstateAnalyzer()
properties = analyzer.fetch_properties(
    provider="mercadolibre",
    location="palermo",
    property_type="departamento",
    operation_type="venta"
)
```

advantages:
- official public api - no anti-bot protection
- reliable and stable
- better data quality
- no maintenance overhead
- argentina's largest marketplace

## code preservation rationale

this code is preserved in the experimental directory for:
- documenting what was attempted and why it failed
- reference for future cloudflare bypass research
- understanding the evolution of anti-bot detection
- avoiding repeating failed approaches
- educational purposes

## usage (not recommended)

if you still want to experiment with these implementations despite their unreliability:

### playwright client
```python
from renta.experimental.zonaprop.playwright_client import ZonapropPlaywrightClient
from renta.config import ConfigManager

config = ConfigManager()
client = ZonapropPlaywrightClient(config)
# likely to fail due to cloudflare
```

### undetected client
```python
from renta.experimental.zonaprop.undetected_client import ZonapropUndetectedClient
from renta.config import ConfigManager

config = ConfigManager()
with ZonapropUndetectedClient(config) as client:
    df = client.scrape_search_results(url)
    # likely to fail due to cloudflare
```

### cookie auth
```bash
# manual authentication (requires user interaction)
python -m renta.experimental.zonaprop.cloudflare_auth auth

# check cookie status
python -m renta.experimental.zonaprop.cloudflare_auth check

# clear cookies
python -m renta.experimental.zonaprop.cloudflare_auth clear
```

## final recommendation

do not use these experimental implementations for production. they are unreliable and require constant maintenance. use the mercadolibre provider instead, which provides official api access to argentina's largest real estate marketplace without any anti-bot protection.

for reference and research purposes only.
