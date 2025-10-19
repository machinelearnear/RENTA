"""
Undetected ChromeDriver scraper for Zonaprop with Cloudflare bypass.

Uses undetected-chromedriver (Selenium-based) to bypass Cloudflare protection.
This library is specifically designed to avoid detection by anti-bot systems.

Cookie-based authentication:
- User manually solves CAPTCHA once using cloudflare_auth tool
- Cookies are saved and reused in automated sessions
- Automatic cookie expiration detection and re-authentication prompts
"""

import time
import random
from typing import Dict, List, Optional
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
import pandas as pd
import structlog
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from .config import ConfigManager
from .exceptions import ZonapropAntiBotError, ScrapingError
from .utils.cloudflare_auth import CloudflareAuthManager


logger = structlog.get_logger(__name__)


class ZonapropUndetectedClient:
    """
    Undetected ChromeDriver scraper for Zonaprop with HTML parsing and cookie authentication.

    Uses undetected-chromedriver to bypass Cloudflare protection and
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
        """Initialize Undetected ChromeDriver client with configuration.

        Args:
            config: ConfigManager instance with scraping configuration
        """
        self.config = config
        self.base_url = "https://www.zonaprop.com.ar"

        # Cloudflare authentication manager
        self.auth_manager = CloudflareAuthManager(config)

        # Browser configuration
        self.headless = config.get("zonaprop.playwright.headless", False)
        self.navigation_timeout = config.get("zonaprop.playwright.navigation_timeout_seconds", 60)
        self.cloudflare_wait_seconds = config.get("zonaprop.playwright.cloudflare_wait_seconds", 10)

        # Pagination configuration
        self.max_pages = config.get("zonaprop.scraping.max_pages", None)
        self.page_load_delay = config.get("zonaprop.playwright.page_load_delay_seconds", 3)

        # Retry configuration
        self.max_retries = config.get("zonaprop.scraping.max_retries", 3)
        self.retry_delay_base = config.get("zonaprop.playwright.retry_delay_base_seconds", 5)

        # State tracking
        self._driver: Optional[uc.Chrome] = None
        self._pages_scraped = 0

        logger.info(
            "ZonapropUndetectedClient initialized",
            headless=self.headless,
            max_pages=self.max_pages
        )

    def __enter__(self) -> "ZonapropUndetectedClient":
        """Context manager entry - initialize browser session."""
        self._ensure_browser_session()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - cleanup browser session."""
        self.close()

    def scrape_search_results(
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
            self._ensure_browser_session()

            # Validate URL
            self._validate_url(search_url)

            # Determine page limit
            page_limit = max_pages if max_pages is not None else self.max_pages

            # Scrape first page to get total page count
            logger.info("Fetching first page", url=search_url)
            first_page_data = self._scrape_page(search_url, page_number=1)

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

                page_data = self._scrape_page(page_url, page_number=page_num)
                all_responses.append(page_data)

                # Rate limiting
                if page_num < total_pages:
                    delay = self.page_load_delay + random.uniform(0, 2)
                    time.sleep(delay)

            # Normalize and combine data
            from .ingestion import ZonapropScraper
            scraper = ZonapropScraper(self.config)
            df = scraper._normalize_listing_data(all_responses)

            logger.info(
                "Scraping completed",
                total_pages=len(all_responses),
                total_properties=len(df)
            )

            return df

        except Exception as e:
            logger.error("Scraping failed", error=str(e), url=search_url)
            if isinstance(e, (ZonapropAntiBotError, ScrapingError)):
                raise
            raise ScrapingError(
                f"Failed to scrape Zonaprop: {e}",
                details={"url": search_url, "error_type": type(e).__name__}
            ) from e

    def close(self) -> None:
        """Close browser and cleanup resources."""
        try:
            if self._driver:
                self._driver.quit()
            logger.debug("Browser session closed")
        except Exception as e:
            logger.warning("Error during browser cleanup", error=str(e))
        finally:
            self._driver = None
            self._pages_scraped = 0

    def _ensure_browser_session(self) -> None:
        """Ensure browser session is active and healthy."""
        if self._driver is None:
            self._launch_browser()

    def _launch_browser(self) -> None:
        """Launch undetected ChromeDriver with anti-detection configuration."""
        options = uc.ChromeOptions()

        # Headless mode (if configured)
        if self.headless:
            options.add_argument("--headless=new")

        # Anti-detection arguments
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-gpu")

        # User agent
        user_agent = self.config.get(
            "zonaprop.playwright.user_agent",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )
        options.add_argument(f"--user-agent={user_agent}")

        # Language and locale
        options.add_argument("--lang=es-AR")
        options.add_experimental_option("prefs", {
            "intl.accept_languages": "es-AR,es,en-US,en"
        })

        try:
            self._driver = uc.Chrome(options=options, version_main=None)
            self._driver.set_page_load_timeout(self.navigation_timeout)

            # Load cookies if available
            if self.auth_manager.has_valid_cookies():
                self._load_cookies()
                logger.info("Cloudflare cookies loaded successfully")
            else:
                logger.warning(
                    "No valid Cloudflare cookies found. "
                    "Run 'python -m renta.utils.cloudflare_auth auth' to authenticate."
                )

            logger.info("Undetected ChromeDriver launched", headless=self.headless)

        except Exception as e:
            logger.error("Failed to launch browser", error=str(e))
            raise ScrapingError(f"Failed to launch undetected ChromeDriver: {e}") from e

    def _load_cookies(self) -> None:
        """Load saved cookies into the browser session."""
        try:
            # Navigate to base URL first (required to set cookies)
            self._driver.get(self.base_url)
            time.sleep(2)

            # Load and add cookies
            cookies = self.auth_manager.load_cookies()
            for cookie in cookies:
                # Selenium requires specific format
                selenium_cookie = {
                    'name': cookie.get('name'),
                    'value': cookie.get('value'),
                    'domain': cookie.get('domain'),
                    'path': cookie.get('path', '/'),
                }

                # Optional fields
                if 'expiry' in cookie or 'expires' in cookie:
                    selenium_cookie['expiry'] = int(cookie.get('expiry', cookie.get('expires', 0)))
                if 'httpOnly' in cookie:
                    selenium_cookie['httpOnly'] = cookie['httpOnly']
                if 'secure' in cookie:
                    selenium_cookie['secure'] = cookie['secure']
                if 'sameSite' in cookie:
                    selenium_cookie['sameSite'] = cookie['sameSite']

                self._driver.add_cookie(selenium_cookie)

            logger.info("Loaded cookies into browser", cookie_count=len(cookies))

        except Exception as e:
            logger.warning("Failed to load cookies", error=str(e))

    def _scrape_page(
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
            # Navigate to page
            logger.debug("Navigating to page", url=page_url, page=page_number)
            self._driver.get(page_url)

            # Wait for Cloudflare challenge to complete
            time.sleep(self.cloudflare_wait_seconds)

            # Wait for page to be ready (look for specific element or __PRELOADED_STATE__)
            try:
                WebDriverWait(self._driver, 30).until(
                    lambda driver: driver.execute_script(
                        "return typeof window.__PRELOADED_STATE__ !== 'undefined'"
                    )
                )
                logger.debug("__PRELOADED_STATE__ detected")
            except Exception:
                logger.warning("Timeout waiting for __PRELOADED_STATE__, attempting extraction anyway")

            # Get HTML content
            html_content = self._driver.page_source

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
                self._handle_retry(page_url, page_number, retry_count)
                return self._scrape_page(page_url, page_number, retry_count + 1)
            raise

        except Exception as e:
            if retry_count < self.max_retries:
                self._handle_retry(page_url, page_number, retry_count)
                return self._scrape_page(page_url, page_number, retry_count + 1)
            raise ScrapingError(
                f"Failed to scrape page: {e}",
                details={
                    "url": page_url,
                    "page": page_number,
                    "error_type": type(e).__name__
                }
            ) from e

    def _handle_retry(
        self,
        url: str,
        page_number: int,
        retry_count: int
    ) -> None:
        """Handle retry logic with exponential backoff."""
        delay = self.retry_delay_base * (2 ** retry_count) + random.uniform(0, 2)
        logger.warning(
            "Retrying page scrape",
            url=url,
            page=page_number,
            attempt=retry_count + 1,
            max_retries=self.max_retries,
            delay_seconds=delay
        )
        time.sleep(delay)

        # Restart browser session on retry
        self.close()
        self._ensure_browser_session()

    def _is_cloudflare_block(self, html_content: str) -> bool:
        """Check if HTML indicates a Cloudflare challenge page."""
        cloudflare_indicators = [
            "Checking your browser",
            "Cloudflare",
            "cf-browser-verification",
            "cf_chl_opt",
            "Ray ID:",
            "Verificar que usted es un ser humano"
        ]

        html_lower = html_content.lower()
        return any(indicator.lower() in html_lower for indicator in cloudflare_indicators)

    def _extract_preloaded_state_from_html(self, html_content: str, source: str) -> Dict:
        """
        Extract window.__PRELOADED_STATE__ from HTML content.

        Delegates to the ingestion module's ZonapropScraper for parsing logic.
        """
        from .ingestion import ZonapropScraper
        scraper = ZonapropScraper(self.config)
        return scraper._extract_preloaded_state(html_content, source)

    def _extract_total_pages_from_response(self, response: Dict) -> int:
        """Extract total page count from API response."""
        try:
            return response.get("listStore", {}).get("paging", {}).get("totalPages", 1)
        except Exception as e:
            logger.warning("Could not extract total pages", error=str(e))
            return 1

    def _count_properties_in_response(self, response: Dict) -> int:
        """Count properties in a single response."""
        try:
            return len(response.get("listStore", {}).get("listPostings", []))
        except Exception:
            return 0

    def _build_page_url(self, base_url: str, page_number: int) -> str:
        """Build URL for a specific page number."""
        parsed = urlparse(base_url)
        query_params = parse_qs(parsed.query)
        query_params['pagina'] = [str(page_number)]

        new_query = urlencode(query_params, doseq=True)
        return urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            new_query,
            parsed.fragment
        ))

    def _validate_url(self, url: str) -> None:
        """Validate that URL is from zonaprop.com.ar."""
        parsed = urlparse(url)
        if "zonaprop.com.ar" not in parsed.netloc:
            raise ValueError(f"URL must be from zonaprop.com.ar, got: {parsed.netloc}")
