"""
Playwright-based scraper for Zonaprop with Cloudflare bypass.

Uses Playwright + playwright-stealth to bypass Cloudflare protection and
intercepts browser API calls to extract clean JSON property data.
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


logger = structlog.get_logger(__name__)


class ZonapropPlaywrightClient:
    """
    Playwright-based scraper for Zonaprop with response interception.

    Uses Playwright + playwright-stealth to bypass Cloudflare protection and
    intercepts browser API calls to extract clean JSON property data.

    Key Features:
    - Cloudflare bypass using playwright-stealth
    - Response interception for clean JSON extraction
    - Browser session reuse for performance
    - Pagination support
    - Comprehensive error handling and retry logic
    - Configurable via ConfigManager
    """

    def __init__(self, config: ConfigManager):
        """Initialize Playwright client with configuration.

        Args:
            config: ConfigManager instance with scraping configuration
        """
        self.config = config
        self.base_url = "https://www.zonaprop.com.ar"

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
        self._intercepted_responses: List[Dict] = []
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
        """Launch Playwright browser with anti-detection configuration."""
        self._playwright = await async_playwright().start()

        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-dev-shm-usage',
            ],
            timeout=self.browser_timeout * 1000
        )

        logger.info("Playwright browser launched", headless=self.headless)

    async def _create_context(self) -> None:
        """Create browser context with realistic fingerprint."""
        self._context = await self._browser.new_context(
            viewport=self.viewport,
            user_agent=self.user_agent,
            locale=self.locale,
            timezone_id=self.timezone,
            extra_http_headers={
                "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
        )

        logger.debug("Browser context created", locale=self.locale)

    async def _create_page(self) -> None:
        """Create page and apply stealth evasions."""
        self._page = await self._context.new_page()

        # Apply playwright-stealth
        stealth = Stealth()
        await stealth.apply_stealth_async(self._page)

        # Set default timeouts
        self._page.set_default_timeout(self.navigation_timeout * 1000)

        logger.debug("Page created with stealth evasions applied")

    async def _scrape_page(
        self,
        page_url: str,
        page_number: int,
        retry_count: int = 0
    ) -> Dict:
        """
        Scrape a single page by intercepting API responses.

        Args:
            page_url: URL to scrape
            page_number: Page number (for logging)
            retry_count: Current retry attempt

        Returns:
            API response data as dictionary

        Raises:
            ZonapropAntiBotError: If Cloudflare blocks the request
            ScrapingError: If scraping fails
        """
        try:
            await self._ensure_browser_session()

            # Clear previous intercepted responses
            self._intercepted_responses.clear()

            # Set up response interception
            async def handle_response(response: Response):
                try:
                    # Check if this is the API endpoint we want
                    if '/rplis-api/postings' in response.url and response.status == 200:
                        # Extract JSON data
                        data = await response.json()
                        self._intercepted_responses.append(data)
                        logger.debug(
                            "Intercepted API response",
                            url=response.url,
                            status=response.status,
                            has_data=bool(data)
                        )
                except Exception as e:
                    logger.debug("Failed to parse response", error=str(e), url=response.url)

            # Register response handler
            self._page.on('response', handle_response)

            # Navigate to page
            logger.debug("Navigating to page", url=page_url, page=page_number)
            response = await self._page.goto(
                page_url,
                wait_until='domcontentloaded',
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

            # Check page content for Cloudflare indicators
            content = await self._page.content()
            if self._is_cloudflare_block(content):
                raise ZonapropAntiBotError(
                    "Cloudflare challenge page detected",
                    details={
                        "reason": "cloudflare_challenge_page",
                        "url": page_url,
                        "page": page_number
                    }
                )

            # Wait for API calls to complete
            await asyncio.sleep(self.page_load_delay)

            # Verify we intercepted responses
            if not self._intercepted_responses:
                raise ScrapingError(
                    "No API responses intercepted",
                    details={"url": page_url, "page": page_number}
                )

            # Update pages scraped counter
            self._pages_scraped += 1

            # Return the first (and usually only) intercepted response
            return self._intercepted_responses[0]

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
