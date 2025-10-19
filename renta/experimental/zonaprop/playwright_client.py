"""
Playwright-based scraper for Zonaprop with Cloudflare bypass.

Uses Playwright + playwright-stealth to bypass Cloudflare protection and
parses HTML content to extract __PRELOADED_STATE__ property data.

Implements cookie-based authentication to bypass Cloudflare challenges:
- User manually solves CAPTCHA once using cloudflare_auth tool
- Cookies are saved and reused in automated sessions
- Automatic cookie expiration detection and re-authentication prompts
"""

import asyncio
import random
import re
from typing import Dict, List, Optional, Any
from urllib.parse import urlparse
import pandas as pd
import structlog
from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Response, Playwright

from playwright_stealth import Stealth

from .config import ConfigManager
from .exceptions import ZonapropAntiBotError, ScrapingError
from .utils.cloudflare_auth import CloudflareAuthManager


logger = structlog.get_logger(__name__)


class ZonapropPlaywrightClient:
    """
    Playwright-based scraper for Zonaprop with HTML parsing and cookie authentication.

    Uses Playwright + playwright-stealth to bypass Cloudflare protection and
    parses HTML content to extract window.__PRELOADED_STATE__ property data.

    Key Features:
    - Cookie-based Cloudflare bypass (user solves CAPTCHA once, cookies are reused)
    - HTML parsing to extract __PRELOADED_STATE__ from embedded JavaScript
    - Browser session reuse for performance
    - Pagination support
    - Comprehensive error handling and retry logic
    - Configurable via ConfigManager

    Authentication:
    Before using this scraper, run the authentication tool once:
        python -m renta.utils.cloudflare_auth auth

    This will open a browser for you to manually solve the Cloudflare challenge.
    The cookies will be saved and reused automatically in subsequent scraping sessions.
    """

    def __init__(self, config: ConfigManager):
        """Initialize Playwright client with configuration.

        Args:
            config: ConfigManager instance with scraping configuration
        """
        self.config = config
        self.base_url = "https://www.zonaprop.com.ar"

        # Cloudflare authentication manager
        self.auth_manager = CloudflareAuthManager(config)

        # Browser configuration
        self.headless = config.get("zonaprop.playwright.headless", False)
        self.browser_timeout = config.get("zonaprop.playwright.browser_timeout_seconds", 60)
        self.navigation_timeout = config.get("zonaprop.playwright.navigation_timeout_seconds", 60)
        self.cloudflare_wait_seconds = config.get("zonaprop.playwright.cloudflare_wait_seconds", 10)

        # Pagination configuration
        self.max_pages = config.get("zonaprop.scraping.max_pages", None)
        self.page_load_delay = config.get("zonaprop.playwright.page_load_delay_seconds", 3)

        # Retry configuration
        self.max_retries = config.get("zonaprop.scraping.max_retries", 3)
        self.retry_delay_base = config.get("zonaprop.playwright.retry_delay_base_seconds", 5)

        # Browser fingerprint
        viewport_config = config.get("zonaprop.playwright.viewport", {})
        self.viewport = {
            "width": viewport_config.get("width", 1920),
            "height": viewport_config.get("height", 1080)
        }
        self.user_agent = config.get(
            "zonaprop.playwright.user_agent",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        self.locale = config.get("zonaprop.playwright.locale", "es-AR")
        self.timezone = config.get("zonaprop.playwright.timezone", "America/Argentina/Buenos_Aires")

        # Session management
        self.reuse_browser = config.get("zonaprop.playwright.reuse_browser_session", True)
        self.session_max_pages = config.get("zonaprop.playwright.session_max_pages", 50)

        # State tracking
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._playwright: Optional[Playwright] = None
        self._session_active = False
        self._pages_scraped = 0

        logger.info(
            "ZonapropPlaywrightClient initialized",
            headless=self.headless,
            max_pages=self.max_pages,
            reuse_browser=self.reuse_browser
        )

    async def __aenter__(self) -> "ZonapropPlaywrightClient":
        """Context manager entry - initialize browser session."""
        await self._ensure_browser_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - cleanup browser session."""
        await self.close()

    async def scrape_search_results(
        self,
        search_url: str,
        max_pages: Optional[int] = None
    ) -> pd.DataFrame:
        """
        Scrape property listings from Zonaprop search URL.

        Args:
            search_url: Zonaprop search URL to scrape
            max_pages: Maximum pages to scrape (overrides config)

        Returns:
            DataFrame of normalized property listings

        Raises:
            ZonapropAntiBotError: If Cloudflare cannot be bypassed
            ScrapingError: If scraping fails for other reasons
        """
        try:
            await self._ensure_browser_session()

            # Validate URL
            self._validate_url(search_url)

            # Determine page limit
            page_limit = max_pages if max_pages is not None else self.max_pages

            # Scrape first page to get total page count
            logger.info("Fetching first page", url=search_url)
            first_page_data = await self._scrape_page(search_url, page_number=1)

            total_pages = self._extract_total_pages_from_response(first_page_data)
            if page_limit is not None:
                total_pages = min(total_pages, page_limit)

            first_page_props = self._count_properties_in_response(first_page_data)
            logger.info(
                "Starting pagination",
                total_pages=total_pages,
                first_page_results=first_page_props
            )

            # Collect all responses
            all_responses = [first_page_data]

            # Scrape remaining pages
            for page_num in range(2, total_pages + 1):
                page_url = self._build_page_url(search_url, page_num)
                logger.debug("Fetching page", page=page_num, url=page_url)

                page_data = await self._scrape_page(page_url, page_number=page_num)
                all_responses.append(page_data)

            # Extract and deduplicate properties
            properties = self._extract_properties_from_responses(all_responses)

            logger.info(
                "Scraping complete",
                total_pages=total_pages,
                unique_properties=len(properties)
            )

            # Convert to DataFrame using existing normalization logic
            # Import here to avoid circular dependency
            from .ingestion import ZonapropScraper
            scraper = ZonapropScraper(self.config)
            return scraper._normalize_property_data(properties)

        except Exception as e:
            logger.error("Scraping failed", error=str(e), url=search_url)
            if isinstance(e, (ZonapropAntiBotError, ScrapingError)):
                raise
            raise ScrapingError(
                f"Failed to scrape Zonaprop: {e}",
                details={"url": search_url, "error_type": type(e).__name__}
            ) from e

    async def close(self) -> None:
        """Close browser and cleanup resources."""
        try:
            if self._page:
                await self._page.close()
            if self._context:
                await self._context.close()
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
            logger.debug("Browser session closed")
        except Exception as e:
            logger.warning("Error during browser cleanup", error=str(e))
        finally:
            self._browser = None
            self._context = None
            self._page = None
            self._playwright = None
            self._session_active = False
            self._pages_scraped = 0

    async def _ensure_browser_session(self) -> None:
        """Ensure browser session is active and healthy."""
        # Check if we need to refresh session due to page limit
        if (self.reuse_browser and
            self._session_active and
            self._pages_scraped >= self.session_max_pages):
            logger.info("Refreshing browser session", pages_scraped=self._pages_scraped)
            await self.close()

        if not self._session_active or self._browser is None:
            await self._launch_browser()
            await self._create_context()
            await self._create_page()
            self._session_active = True

    async def _launch_browser(self) -> None:
        """Launch Playwright browser with enhanced anti-detection configuration."""
        self._playwright = await async_playwright().start()

        # Enhanced browser arguments to bypass Cloudflare detection
        browser_args = [
            '--disable-blink-features=AutomationControlled',
            '--disable-features=IsolateOrigins,site-per-process',
            '--disable-site-isolation-trials',
            '--no-sandbox',
            '--disable-dev-shm-usage',
            '--disable-web-security',
            '--disable-features=VizDisplayCompositor',
            '--disable-background-networking',
            '--disable-background-timer-throttling',
            '--disable-backgrounding-occluded-windows',
            '--disable-breakpad',
            '--disable-client-side-phishing-detection',
            '--disable-component-extensions-with-background-pages',
            '--disable-default-apps',
            '--disable-extensions',
            '--disable-features=Translate',
            '--disable-hang-monitor',
            '--disable-ipc-flooding-protection',
            '--disable-popup-blocking',
            '--disable-prompt-on-repost',
            '--disable-renderer-backgrounding',
            '--disable-sync',
            '--force-color-profile=srgb',
            '--metrics-recording-only',
            '--no-first-run',
            '--password-store=basic',
            '--use-mock-keychain',
            '--enable-features=NetworkService,NetworkServiceInProcess',
        ]

        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
            args=browser_args,
            timeout=self.browser_timeout * 1000
        )

        logger.info("Enhanced Playwright browser launched", headless=self.headless)

    async def _create_context(self) -> None:
        """Create browser context with enhanced realistic fingerprint and load saved cookies."""
        self._context = await self._browser.new_context(
            viewport=self.viewport,
            user_agent=self.user_agent,
            locale=self.locale,
            timezone_id=self.timezone,
            # Enhanced headers to appear more human
            extra_http_headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Accept-Language": "es-AR,es;q=0.9,en-US;q=0.8,en;q=0.7",
                "Accept-Encoding": "gzip, deflate, br",
                "DNT": "1",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Cache-Control": "max-age=0",
            },
            # Grant permissions to reduce suspicion
            permissions=["geolocation", "notifications"],
            # More realistic browser features
            color_scheme="light",
            reduced_motion="no-preference",
            forced_colors="none",
            # Realistic device properties
            device_scale_factor=1,
            is_mobile=False,
            has_touch=False,
            java_script_enabled=True,
        )

        # Load and apply saved Cloudflare cookies
        if self.auth_manager.has_valid_cookies():
            try:
                await self.auth_manager.apply_cookies_to_context(self._context)
                logger.info("Cloudflare cookies loaded successfully")
            except Exception as e:
                logger.warning("Failed to load cookies, may encounter Cloudflare challenge", error=str(e))
        else:
            logger.warning(
                "No valid Cloudflare cookies found. "
                "Run 'python -m renta.utils.cloudflare_auth auth' to authenticate."
            )

        logger.debug("Enhanced browser context created", locale=self.locale)

    async def _create_page(self) -> None:
        """Create page with enhanced stealth evasions and property overrides."""
        self._page = await self._context.new_page()

        # Apply playwright-stealth first
        stealth = Stealth()
        await stealth.apply_stealth_async(self._page)

        # Additional JavaScript injections to mask automation
        await self._page.add_init_script("""
            // Override the navigator.webdriver property
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });

            // Mock plugins
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });

            // Mock languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['es-AR', 'es', 'en-US', 'en']
            });

            // Override permissions
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );

            // Mock chrome property
            window.chrome = {
                runtime: {},
                loadTimes: function() {},
                csi: function() {},
                app: {}
            };

            // Override toString methods to prevent detection
            const originalToString = Function.prototype.toString;
            Function.prototype.toString = function() {
                if (this === window.navigator.permissions.query) {
                    return 'function query() { [native code] }';
                }
                return originalToString.call(this);
            };
        """)

        # Set default timeouts
        self._page.set_default_timeout(self.navigation_timeout * 1000)

        logger.debug("Page created with enhanced stealth evasions applied")

    async def _scrape_page(
        self,
        page_url: str,
        page_number: int,
        retry_count: int = 0
    ) -> Dict:
        """
        Scrape a single page by parsing HTML content.

        Args:
            page_url: URL to scrape
            page_number: Page number (for logging)
            retry_count: Current retry attempt

        Returns:
            __PRELOADED_STATE__ data as dictionary

        Raises:
            ZonapropAntiBotError: If Cloudflare blocks the request
            ScrapingError: If scraping fails
        """
        try:
            await self._ensure_browser_session()

            # Navigate to page
            logger.debug("Navigating to page", url=page_url, page=page_number)
            response = await self._page.goto(
                page_url,
                wait_until='load',  # Wait for full page load including JavaScript
                timeout=self.navigation_timeout * 1000
            )

            # Check for Cloudflare block
            if response.status in (403, 503):
                raise ZonapropAntiBotError(
                    "Cloudflare blocked request",
                    details={
                        "status_code": response.status,
                        "url": page_url,
                        "page": page_number
                    }
                )

            # Wait for Cloudflare challenge to complete
            await asyncio.sleep(self.cloudflare_wait_seconds)

            # Wait for __PRELOADED_STATE__ to be injected by JavaScript
            logger.debug("Waiting for __PRELOADED_STATE__ to load", url=page_url)
            try:
                await self._page.wait_for_function(
                    "window.__PRELOADED_STATE__ !== undefined",
                    timeout=30000  # 30 second timeout for state to appear
                )
            except Exception as e:
                logger.warning(
                    "Timeout waiting for __PRELOADED_STATE__, attempting extraction anyway",
                    url=page_url,
                    error=str(e)
                )

            # Extract HTML content
            html_content = await self._page.content()

            # Check for Cloudflare indicators
            if self._is_cloudflare_block(html_content):
                raise ZonapropAntiBotError(
                    "Cloudflare challenge page detected",
                    details={
                        "reason": "cloudflare_challenge_page",
                        "url": page_url,
                        "page": page_number
                    }
                )

            # Parse __PRELOADED_STATE__ from HTML
            state_data = self._extract_preloaded_state_from_html(html_content, page_url)

            # Update pages scraped counter
            self._pages_scraped += 1

            logger.debug(
                "Successfully extracted state from HTML",
                url=page_url,
                page=page_number,
                has_data=bool(state_data)
            )

            return state_data

        except ZonapropAntiBotError:
            if retry_count < self.max_retries:
                await self._handle_retry(page_url, page_number, retry_count)
                return await self._scrape_page(page_url, page_number, retry_count + 1)
            raise

        except Exception as e:
            if retry_count < self.max_retries:
                await self._handle_retry(page_url, page_number, retry_count)
                return await self._scrape_page(page_url, page_number, retry_count + 1)
            raise ScrapingError(
                f"Failed to scrape page: {e}",
                details={
                    "url": page_url,
                    "page": page_number,
                    "error_type": type(e).__name__
                }
            ) from e

    async def _handle_retry(
        self,
        url: str,
        page_number: int,
        retry_count: int
    ) -> None:
        """Handle retry logic with exponential backoff."""
        delay = self._compute_retry_delay(retry_count)

        logger.warning(
            "Retrying page scrape",
            url=url,
            page=page_number,
            attempt=retry_count + 1,
            max_retries=self.max_retries,
            delay_seconds=delay
        )

        # Close and recreate browser session on retry
        await self.close()
        await asyncio.sleep(delay)
        await self._ensure_browser_session()

    def _compute_retry_delay(self, attempt: int) -> float:
        """Compute exponential backoff delay with jitter."""
        base_delay = self.retry_delay_base * (2 ** attempt)
        jitter = random.uniform(0.5, 1.5)
        return min(base_delay + jitter, 60.0)

    def _build_page_url(self, search_url: str, page_number: int) -> str:
        """Build URL for a specific page number."""
        if page_number <= 1:
            return search_url

        parsed = urlparse(search_url)
        path = parsed.path or ""

        # Handle existing page number in URL
        if re.search(r'-pagina-\d+', path):
            new_path = re.sub(
                r'-pagina-\d+(\.html)?',
                f'-pagina-{page_number}.html',
                path
            )
        # Add page number to .html URL
        elif path.endswith('.html'):
            new_path = re.sub(r'\.html$', f'-pagina-{page_number}.html', path)
        # Add page number to path without extension
        else:
            base_path = path.rstrip('/')
            new_path = f'{base_path}-pagina-{page_number}.html'

        # Reconstruct URL
        rebuilt = f'{parsed.scheme}://{parsed.netloc}{new_path}'
        if parsed.query:
            rebuilt = f'{rebuilt}?{parsed.query}'
        if parsed.fragment:
            rebuilt = f'{rebuilt}#{parsed.fragment}'

        return rebuilt

    def _extract_total_pages_from_response(self, response_data: Dict) -> int:
        """Extract total page count from API response."""
        paths_to_try = [
            ["listStore", "metadata", "paging", "totalPages"],
            ["listStore", "metadata", "totalPages"],
            ["listStore", "totalPages"],
            ["metadata", "totalPages"],
            ["totalPages"],
        ]

        for path in paths_to_try:
            try:
                value = response_data
                for key in path:
                    value = value[key]

                if isinstance(value, (int, float)) and value >= 1:
                    return int(value)
                if isinstance(value, str) and value.isdigit():
                    return int(value)
            except (KeyError, TypeError):
                continue

        logger.warning("Could not extract total pages, defaulting to 1")
        return 1

    def _count_properties_in_response(self, response_data: Dict) -> int:
        """Count properties in a single API response."""
        list_store = response_data.get("listStore", {})
        postings = (
            list_store.get("listPostings") or
            list_store.get("searchPostings") or
            list_store.get("postings") or
            {}
        )

        if isinstance(postings, dict):
            return len(postings)
        elif isinstance(postings, list):
            return len(postings)
        return 0

    def _extract_properties_from_responses(
        self,
        responses: List[Dict]
    ) -> List[Dict]:
        """Extract and deduplicate properties from multiple API responses."""
        # Import here to avoid circular dependency
        from .ingestion import ZonapropScraper
        scraper = ZonapropScraper(self.config)

        properties_by_id: Dict[str, Dict] = {}

        for response in responses:
            properties = self._extract_properties_from_response(response, scraper)

            for prop in properties:
                prop_id = prop.get("id")
                if not prop_id:
                    continue

                # Simple deduplication - first occurrence wins
                if prop_id not in properties_by_id:
                    properties_by_id[prop_id] = prop

        return list(properties_by_id.values())

    def _extract_properties_from_response(
        self,
        response_data: Dict,
        scraper
    ) -> List[Dict]:
        """Extract property records from a single API response."""
        # Look for postings in response
        list_store = response_data.get("listStore", {})
        postings = (
            list_store.get("listPostings") or
            list_store.get("searchPostings") or
            list_store.get("postings") or
            {}
        )

        # Convert to iterable
        if isinstance(postings, dict):
            postings_iterable = postings.values()
        else:
            postings_iterable = postings or []

        # Transform each posting using existing scraper logic
        properties = []
        for raw_posting in postings_iterable:
            if not isinstance(raw_posting, dict):
                continue

            transformed = scraper._transform_property_record(raw_posting, source="playwright")
            if transformed:
                properties.append(transformed)

        return properties

    def _validate_url(self, url: str) -> None:
        """Validate URL before navigation."""
        allowed_domains = ["zonaprop.com.ar", "www.zonaprop.com.ar"]

        parsed = urlparse(url)
        if parsed.netloc not in allowed_domains:
            raise ScrapingError(
                f"Invalid domain: {parsed.netloc}",
                details={"url": url, "allowed_domains": allowed_domains}
            )

        if parsed.scheme not in ["https", "http"]:
            raise ScrapingError(
                f"Invalid scheme: {parsed.scheme}",
                details={"url": url}
            )

    def _extract_preloaded_state_from_html(self, html_content: str, source: str) -> Dict:
        """
        Extract window.__PRELOADED_STATE__ from HTML content.

        Delegates to the ingestion module's ZonapropScraper for parsing logic
        to avoid code duplication and maintain consistency.

        Args:
            html_content: HTML content as string
            source: Source URL (for error messages)

        Returns:
            __PRELOADED_STATE__ dictionary with listing data

        Raises:
            ScrapingError: If state cannot be extracted
        """
        # Import here to avoid circular dependency
        from .ingestion import ZonapropScraper

        # Create scraper instance to reuse extraction logic
        scraper = ZonapropScraper(self.config)

        # Delegate to existing proven parsing method
        return scraper._extract_preloaded_state(html_content, source)

    @staticmethod
    def _is_cloudflare_block(html_content: str) -> bool:
        """Detect Cloudflare challenge/block pages."""
        if not html_content:
            return False

        lowered = html_content.lower()
        indicators = [
            "just a moment",
            "checking your browser",
            "cf-browser-verification",
            "cf-chl-bypass",
            "cf-error",
            "cf-challenge-running",
        ]
        return any(indicator in lowered for indicator in indicators)
