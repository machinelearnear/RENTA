"""
Data ingestion components for RENTA library.

Handles downloading and initial processing of data from external sources
including InsideAirbnb and Zonaprop.
"""

import json
import os
import re
import time
import random
import unicodedata
from datetime import date
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import urljoin, urlparse
import requests
import cloudscraper
from bs4 import BeautifulSoup
import pandas as pd
from tqdm import tqdm
import structlog

from .config import ConfigManager
from .exceptions import AirbnbDataError, ScrapingError, ZonapropAntiBotError

logger = structlog.get_logger()


class AirbnbIngester:
    """Handles Airbnb data download and initial processing from InsideAirbnb.

    Provides web scraping to discover Buenos Aires file URLs, HTTPS download
    with progress tracking, and freshness checking with force download option.
    """

    def __init__(self, config: ConfigManager):
        """Initialize AirbnbIngester with configuration.

        Args:
            config: ConfigManager instance with data and airbnb settings
        """
        self.config = config
        self.cache_dir = Path(config.get("data.cache_dir", "~/.renta/cache")).expanduser()
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # InsideAirbnb base URL and Buenos Aires city identifier
        self.base_url = "http://insideairbnb.com/get-the-data/"
        self.city_name = "buenos-aires"

        # File types we need to download
        self.required_files = {
            "listings": "listings.csv.gz",
            "reviews": "reviews.csv.gz",
            "calendar": "calendar.csv.gz",
        }

    def download_data(self, force: bool = False) -> Dict[str, str]:
        """Download Airbnb files from InsideAirbnb.

        Args:
            force: If True, download even if fresh data exists

        Returns:
            Dictionary mapping file type to local file path

        Raises:
            AirbnbDataError: If download fails or data cannot be processed
        """
        try:
            # Check if we need to download
            if not force and self.is_data_fresh():
                existing_files = self._get_existing_files()
                if existing_files:
                    return existing_files

            # Get file URLs from InsideAirbnb
            file_urls = self.get_file_urls()

            # Download each file
            downloaded_files = {}
            for file_type, url in file_urls.items():
                local_path = self._download_file(url, file_type)
                downloaded_files[file_type] = local_path

            # Update timestamp
            self._update_download_timestamp()

            return downloaded_files

        except Exception as e:
            if isinstance(e, AirbnbDataError):
                raise
            raise AirbnbDataError(
                f"Failed to download Airbnb data: {e}",
                details={"error_type": type(e).__name__, "force": force},
            )

    def is_data_fresh(self) -> bool:
        """Check if cached data is within freshness threshold.

        Returns:
            True if data is fresh, False if needs refresh
        """
        timestamp_file = self.cache_dir / ".airbnb_download_timestamp"

        if not timestamp_file.exists():
            return False

        try:
            with open(timestamp_file, "r") as f:
                timestamp = float(f.read().strip())

            freshness_hours = self.config.get("data.freshness_threshold_hours", 24)
            age_hours = (time.time() - timestamp) / 3600

            return age_hours < freshness_hours

        except (ValueError, IOError):
            return False

    def get_file_urls(self) -> Dict[str, str]:
        """Scrape InsideAirbnb for Buenos Aires file URLs.

        Returns:
            Dictionary mapping file type to download URL

        Raises:
            AirbnbDataError: If URLs cannot be discovered
        """
        try:
            # Request the data page
            response = requests.get(self.base_url, timeout=30)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, "html.parser")

            # Find Buenos Aires section
            file_urls = {}

            # Look for Buenos Aires data links
            # InsideAirbnb typically has links in format:
            # http://data.insideairbnb.com/argentina/ciudad-autónoma-de-buenos-aires/buenos-aires/YYYY-MM-DD/data/listings.csv.gz

            links = soup.find_all("a", href=True)
            buenos_aires_links = []

            for link in links:
                href = link["href"]
                if "buenos-aires" in href.lower() and any(
                    file_name in href for file_name in self.required_files.values()
                ):
                    buenos_aires_links.append(href)

            if not buenos_aires_links:
                raise AirbnbDataError(
                    "No Buenos Aires data links found on InsideAirbnb",
                    details={"base_url": self.base_url, "links_found": len(links)},
                )

            # Group links by date (get most recent)
            date_pattern = r"(\d{4}-\d{2}-\d{2})"
            dated_links = {}

            for link in buenos_aires_links:
                match = re.search(date_pattern, link)
                if match:
                    date = match.group(1)
                    if date not in dated_links:
                        dated_links[date] = []
                    dated_links[date].append(link)

            if not dated_links:
                raise AirbnbDataError(
                    "No dated Buenos Aires links found",
                    details={"links_checked": len(buenos_aires_links)},
                )

            # Get most recent date
            latest_date = max(dated_links.keys())
            latest_links = dated_links[latest_date]

            # Map file types to URLs
            for file_type, file_name in self.required_files.items():
                matching_links = [link for link in latest_links if file_name in link]
                if matching_links:
                    file_urls[file_type] = matching_links[0]

            # Validate we found all required files
            missing_files = set(self.required_files.keys()) - set(file_urls.keys())
            if missing_files:
                raise AirbnbDataError(
                    f"Missing required files: {missing_files}",
                    details={
                        "found_files": list(file_urls.keys()),
                        "missing_files": list(missing_files),
                        "latest_date": latest_date,
                    },
                )

            return file_urls

        except requests.RequestException as e:
            raise AirbnbDataError(
                f"Failed to fetch InsideAirbnb data page: {e}",
                details={"url": self.base_url, "error_type": type(e).__name__},
            )
        except Exception as e:
            if isinstance(e, AirbnbDataError):
                raise
            raise AirbnbDataError(
                f"Failed to parse InsideAirbnb data page: {e}",
                details={"error_type": type(e).__name__},
            )

    def _download_file(self, url: str, file_type: str) -> str:
        """Download a single file with progress tracking.

        Args:
            url: URL to download
            file_type: Type of file (listings, reviews, calendar)

        Returns:
            Path to downloaded file

        Raises:
            AirbnbDataError: If download fails
        """
        try:
            # Determine local filename
            parsed_url = urlparse(url)
            original_filename = Path(parsed_url.path).name
            local_filename = f"airbnb_{file_type}_{original_filename}"
            local_path = self.cache_dir / local_filename

            # Download with progress bar
            response = requests.get(url, stream=True, timeout=60)
            response.raise_for_status()

            total_size = int(response.headers.get("content-length", 0))

            with open(local_path, "wb") as f, tqdm(
                desc=f"Downloading {file_type}",
                total=total_size,
                unit="B",
                unit_scale=True,
                unit_divisor=1024,
            ) as pbar:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        pbar.update(len(chunk))

            return str(local_path)

        except requests.RequestException as e:
            raise AirbnbDataError(
                f"Failed to download {file_type} from {url}: {e}",
                details={"url": url, "file_type": file_type, "error_type": type(e).__name__},
            )
        except IOError as e:
            raise AirbnbDataError(
                f"Failed to save {file_type} to {local_path}: {e}",
                details={"local_path": str(local_path), "file_type": file_type},
            )

    def _get_existing_files(self) -> Dict[str, str]:
        """Get paths to existing cached files.

        Returns:
            Dictionary mapping file type to local file path, empty if any missing
        """
        existing_files = {}

        for file_type in self.required_files.keys():
            # Look for files matching pattern
            pattern = f"airbnb_{file_type}_*.csv.gz"
            matching_files = list(self.cache_dir.glob(pattern))

            if matching_files:
                # Get most recent file
                latest_file = max(matching_files, key=lambda p: p.stat().st_mtime)
                existing_files[file_type] = str(latest_file)
            else:
                return {}  # Missing file, return empty dict

        return existing_files

    def _update_download_timestamp(self) -> None:
        """Update the download timestamp file."""
        timestamp_file = self.cache_dir / ".airbnb_download_timestamp"
        with open(timestamp_file, "w") as f:
            f.write(str(time.time()))


class ZonapropScraper:
    """Handles Zonaprop website scraping for property listings.

    Provides web scraping with rate limiting and user-agent rotation,
    Cloudflare detection with fallback to manual HTML files, and robust
    HTML parsing for property data extraction.
    """

    def __init__(self, config: ConfigManager):
        """Initialize ZonapropScraper with configuration.

        Args:
            config: ConfigManager instance with zonaprop scraping settings
        """
        self.config = config
        self.rate_limit = float(config.get("zonaprop.scraping.rate_limit_seconds", 30))
        self.max_retries = int(config.get("zonaprop.scraping.max_retries", 3))
        self.timeout = float(config.get("zonaprop.scraping.timeout_seconds", 30))
        self.cloudflare_delay = float(
            config.get("zonaprop.scraping.cloudflare_delay_seconds", 30)
        )
        self.max_pages = config.get("zonaprop.scraping.max_pages")
        if self.max_pages is not None:
            try:
                self.max_pages = int(self.max_pages)
                if self.max_pages <= 0:
                    self.max_pages = None
            except (TypeError, ValueError):
                logger.warning(
                    "Invalid Zonaprop max_pages config, ignoring",
                    value=self.max_pages,
                )
                self.max_pages = None
        self.fetch_listing_views = bool(
            config.get("zonaprop.scraping.fetch_listing_views", False)
        )
        max_view_requests_cfg = config.get(
            "zonaprop.scraping.max_view_requests", 100
        )
        if max_view_requests_cfg is None:
            self.max_view_requests = None
        else:
            try:
                self.max_view_requests = int(max_view_requests_cfg)
                if self.max_view_requests <= 0:
                    self.max_view_requests = None
            except (TypeError, ValueError):
                logger.warning(
                    "Invalid Zonaprop max_view_requests config, ignoring",
                    value=max_view_requests_cfg,
                )
                self.max_view_requests = None
        listing_delay_cfg = config.get(
            "zonaprop.scraping.listing_detail_delay_seconds", None
        )
        if listing_delay_cfg is None:
            self.listing_detail_delay = max(self.rate_limit, 5.0)
        else:
            try:
                self.listing_detail_delay = float(listing_delay_cfg)
            except (TypeError, ValueError):
                logger.warning(
                    "Invalid Zonaprop listing detail delay config, falling back",
                    value=listing_delay_cfg,
                )
                self.listing_detail_delay = max(self.rate_limit, 5.0)
        self.user_agents = config.get(
            "zonaprop.scraping.user_agents",
            [
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            ],
        )

        if not self.user_agents:
            raise ScrapingError("Zonaprop user agent list cannot be empty")

        self.base_url = "https://www.zonaprop.com.ar"
        self.session: cloudscraper.CloudScraper = self._create_session()
        self.current_user_agent = self.session.headers.get("User-Agent")
        self.last_request_time = 0.0
        self.last_detail_request_time = 0.0

        # Allowed domains for scraping (security measure)
        self.allowed_domains = ["zonaprop.com.ar", "www.zonaprop.com.ar"]

    def _create_session(self) -> cloudscraper.CloudScraper:
        """Create a new cloudscraper session with randomized headers."""
        user_agent = random.choice(self.user_agents)
        logger.debug(
            "Creating Zonaprop scraper session", user_agent=user_agent, delay=self.cloudflare_delay
        )
        scraper = cloudscraper.create_scraper(
            delay=max(self.cloudflare_delay, 0),
            browser={
                "browser": "chrome",
                "platform": "windows",
                "desktop": True,
            },
        )
        scraper.headers.update(
            {
                "User-Agent": user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
            }
        )
        self.current_user_agent = user_agent
        return scraper

    def _refresh_session(self) -> None:
        """Recreate the cloudscraper session, typically after anti-bot detection."""
        logger.debug("Refreshing Zonaprop session after blockage or inactivity")
        self.session = self._create_session()

    def _validate_url(self, url: str) -> None:
        """Validate URL for security before making requests.

        Args:
            url: URL to validate

        Raises:
            ScrapingError: If URL is invalid or not allowed
        """
        try:
            parsed = urlparse(url)

            # Only allow HTTPS (or HTTP for development)
            if parsed.scheme not in ["https", "http"]:
                raise ScrapingError(
                    f"Invalid URL scheme: {parsed.scheme}. Only HTTPS/HTTP allowed.",
                    details={"url": url, "scheme": parsed.scheme},
                )

            # Whitelist allowed domains
            if not any(domain in parsed.netloc for domain in self.allowed_domains):
                raise ScrapingError(
                    f"Domain not allowed: {parsed.netloc}. Only Zonaprop domains are permitted.",
                    details={
                        "url": url,
                        "domain": parsed.netloc,
                        "allowed_domains": self.allowed_domains,
                    },
                )

            # Basic URL format validation
            if not parsed.netloc or not parsed.scheme:
                raise ScrapingError("Malformed URL: missing scheme or netloc", details={"url": url})

        except ValueError as e:
            raise ScrapingError(f"Invalid URL format: {e}", details={"url": url}) from e

    def scrape_search_results(self, search_url: str) -> pd.DataFrame:
        """Scrape property listings from search URL.

        Args:
            search_url: Zonaprop search URL to scrape

        Returns:
            DataFrame of normalized property listings

        Raises:
            ZonapropAntiBotError: If anti-bot protection is detected
            ScrapingError: If scraping fails for other reasons
        """
        try:
            self._validate_url(search_url)

            # Fetch first page and extract properties/state
            html_content = self._fetch_page(search_url, bucket="search")
            properties_map: Dict[str, Dict] = {}
            page_properties, state = self._extract_properties_from_html(html_content, search_url)
            for record in page_properties:
                property_id = record.get("id")
                if not property_id:
                    continue
                properties_map[property_id] = record

            total_pages = self._extract_total_pages(html_content, state)
            if self.max_pages is not None:
                total_pages = max(1, min(total_pages, self.max_pages))

            logger.info(
                "Fetched Zonaprop first page",
                url=search_url,
                properties_found=len(properties_map),
                total_pages=total_pages,
            )

            # Iterate through remaining pages if available
            for page_number in range(2, total_pages + 1):
                page_url = self._build_page_url(search_url, page_number)
                self._validate_url(page_url)
                page_html = self._fetch_page(page_url, bucket="search")
                page_records, _ = self._extract_properties_from_html(page_html, page_url)

                for record in page_records:
                    property_id = record.get("id")
                    if not property_id:
                        continue
                    if property_id in properties_map:
                        properties_map[property_id] = self._merge_property_records(
                            properties_map[property_id], record
                        )
                    else:
                        properties_map[property_id] = record

                logger.debug(
                    "Fetched Zonaprop page",
                    page=page_number,
                    url=page_url,
                    cumulative_properties=len(properties_map),
                )

            properties = list(properties_map.values())

            if self.fetch_listing_views and properties:
                properties = self._populate_listing_views(properties)

            return self._normalize_property_data(properties)

        except ZonapropAntiBotError:
            raise
        except Exception as e:
            if isinstance(e, ScrapingError):
                raise
            raise ScrapingError(
                f"Failed to scrape Zonaprop search results: {e}",
                details={"url": search_url, "error_type": type(e).__name__},
            )

    def parse_html_files(self, html_path: str) -> pd.DataFrame:
        """Parse saved HTML files as fallback.

        Args:
            html_path: Path to saved HTML file or directory

        Returns:
            DataFrame of normalized property listings

        Raises:
            ScrapingError: If parsing fails
        """
        try:
            html_path = Path(html_path)

            if html_path.is_file():
                with open(html_path, "r", encoding="utf-8") as f:
                    html_content = f.read()
                properties, _ = self._extract_properties_from_html(html_content, str(html_path))

            elif html_path.is_dir():
                properties_by_id: Dict[str, Dict] = {}
                for html_file in sorted(html_path.glob("*.html")):
                    with open(html_file, "r", encoding="utf-8") as f:
                        html_content = f.read()
                    file_properties, _ = self._extract_properties_from_html(
                        html_content, str(html_file)
                    )
                    for record in file_properties:
                        property_id = record.get("id")
                        if not property_id:
                            continue
                        if property_id in properties_by_id:
                            properties_by_id[property_id] = self._merge_property_records(
                                properties_by_id[property_id], record
                            )
                        else:
                            properties_by_id[property_id] = record

                properties = list(properties_by_id.values())
            else:
                raise ScrapingError(
                    f"HTML path does not exist: {html_path}", details={"path": str(html_path)}
                )

            return self._normalize_property_data(properties)

        except Exception as e:
            if isinstance(e, ScrapingError):
                raise
            raise ScrapingError(
                f"Failed to parse HTML files: {e}",
                details={"path": str(html_path), "error_type": type(e).__name__},
            )

    def _fetch_page(self, url: str, *, bucket: str = "search") -> str:
        """Fetch a web page with cloudscraper to bypass Cloudflare protection.

        Args:
            url: URL to fetch
            bucket: Rate-limit bucket ('search' or 'detail')

        Returns:
            HTML content as string

        Raises:
            ZonapropAntiBotError: If anti-bot protection detected
            ScrapingError: If request fails
        """
        self._validate_url(url)

        last_exception: Optional[Exception] = None

        for attempt in range(1, self.max_retries + 1):
            try:
                self._respect_rate_limit(bucket=bucket)
                response = self.session.get(url, timeout=self.timeout)
                status_code = response.status_code
                content = response.text

                if response.status_code == 200:
                    if self._is_cloudflare_block(content):
                        raise ZonapropAntiBotError(
                            details={
                                "status_code": status_code,
                                "url": url,
                                "attempt": attempt,
                                "reason": "cloudflare_block_page",
                            }
                        )
                    self._record_request_timestamp(bucket)
                    return content

                if status_code in (403, 429, 503):
                    last_exception = ZonapropAntiBotError(
                        details={
                            "status_code": status_code,
                            "url": url,
                            "attempt": attempt,
                            "user_agent": self.current_user_agent,
                        }
                    )
                    logger.warning(
                        "Zonaprop responded with anti-bot status code",
                        url=url,
                        status_code=status_code,
                        attempt=attempt,
                    )
                    self._refresh_session()
                else:
                    last_exception = ScrapingError(
                        f"Unexpected status code {status_code} while fetching {url}",
                        details={"status_code": status_code, "url": url},
                    )

            except cloudscraper.exceptions.CloudflareChallengeError as e:
                last_exception = ZonapropAntiBotError(
                    "Zonaprop anti-bot challenge could not be solved automatically.",
                    details={"url": url, "attempt": attempt, "error": str(e)},
                )
                logger.warning(
                    "Cloudflare challenge error",
                    url=url,
                    attempt=attempt,
                    error=str(e),
                )
                self._refresh_session()

            except ZonapropAntiBotError as e:
                last_exception = e
                self._refresh_session()

            except requests.exceptions.RequestException as e:
                last_exception = e
                logger.warning(
                    "Network error while fetching Zonaprop page",
                    url=url,
                    attempt=attempt,
                    error=str(e),
                )
                self._refresh_session()

            if attempt < self.max_retries:
                retry_delay = self._compute_retry_delay(attempt)
                logger.debug(
                    "Retrying Zonaprop request",
                    url=url,
                    attempt=attempt,
                    delay=round(retry_delay, 2),
                    bucket=bucket,
                )
                time.sleep(retry_delay)
            else:
                break

        if isinstance(last_exception, ZonapropAntiBotError):
            raise last_exception

        if isinstance(last_exception, requests.exceptions.RequestException):
            status_code = (
                getattr(last_exception.response, "status_code", None)
                if hasattr(last_exception, "response")
                else None
            )
            raise ScrapingError(
                f"Failed to fetch {url}: {last_exception}",
                details={
                    "url": url,
                    "status_code": status_code,
                    "error_type": type(last_exception).__name__,
                },
            ) from last_exception

        if isinstance(last_exception, ScrapingError):
            raise last_exception

        raise ScrapingError(f"Failed to fetch {url} after {self.max_retries} attempts")

    def _respect_rate_limit(self, *, bucket: str) -> None:
        """Sleep as needed to respect configured rate limits."""
        if bucket == "detail":
            base_delay = max(self.listing_detail_delay, 0.0)
            last_time = self.last_detail_request_time
        else:
            base_delay = max(self.rate_limit, 0.0)
            last_time = self.last_request_time

        if base_delay <= 0:
            return

        elapsed = time.time() - last_time
        remaining = base_delay - elapsed
        if remaining > 0:
            jitter_bound = 0.5 if base_delay < 5 else 1.5
            sleep_time = remaining + random.uniform(0.2, jitter_bound)
            logger.debug(
                "Respecting Zonaprop rate limit",
                bucket=bucket,
                base_delay=base_delay,
                sleep=round(sleep_time, 2),
            )
            time.sleep(max(sleep_time, 0))

    def _record_request_timestamp(self, bucket: str) -> None:
        """Update the timestamp for the last request in the given bucket."""
        current_time = time.time()
        if bucket == "detail":
            self.last_detail_request_time = current_time
        else:
            self.last_request_time = current_time

    @staticmethod
    def _compute_retry_delay(attempt: int) -> float:
        """Compute exponential backoff delay with jitter."""
        base_delay = 2 ** max(0, attempt - 1)
        jitter = random.uniform(0.5, 1.5)
        return min(base_delay + jitter, 30.0)

    @staticmethod
    def _is_cloudflare_block(html_content: str) -> bool:
        """Detect Cloudflare block/challenge pages."""
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
            "cloudflare ray id",
        ]
        return any(indicator in lowered for indicator in indicators)

    def _extract_properties_from_html(
        self, html_content: str, source: str
    ) -> Tuple[List[Dict], Optional[Dict]]:
        """Extract properties and state dictionary from raw HTML."""
        if self._is_cloudflare_block(html_content):
            raise ZonapropAntiBotError(details={"url": source, "reason": "cloudflare_block"})

        state = self._extract_preloaded_state(html_content, source)
        properties = self._extract_properties_from_state(state, source)
        return properties, state

    def _extract_preloaded_state(self, html_content: str, source: str) -> Dict:
        """Extract the window.__PRELOADED_STATE__ JSON payload."""
        soup = BeautifulSoup(html_content, "html.parser")
        script = soup.find("script", id="preloadedData")
        if not script:
            for candidate in soup.find_all("script"):
                script_text = candidate.string or candidate.get_text()
                if script_text and "__PRELOADED_STATE__" in script_text:
                    script = candidate
                    break

        if not script:
            raise ScrapingError(
                "Failed to locate Zonaprop listing payload",
                details={"source": source},
            )

        script_text = script.string or script.get_text()
        if not script_text:
            raise ScrapingError(
                "Zonaprop listing payload script was empty",
                details={"source": source},
            )

        match = re.search(
            r"window\.__PRELOADED_STATE__\s*=\s*(\{.*?\})\s*;?",
            script_text,
            flags=re.DOTALL,
        )
        if not match:
            raise ScrapingError(
                "Failed to extract Zonaprop JSON payload",
                details={"source": source},
            )

        json_candidate = match.group(1).strip()

        try:
            return json.loads(json_candidate)
        except json.JSONDecodeError as exc:
            raise ScrapingError(
                "Failed to parse Zonaprop listing payload",
                details={"source": source, "error": str(exc)},
            ) from exc

    def _extract_properties_from_state(self, state: Dict, source: str) -> List[Dict]:
        """Convert Zonaprop state dictionary into property records."""
        list_store = state.get("listStore") or {}
        postings = (
            list_store.get("listPostings")
            or list_store.get("searchPostings")
            or list_store.get("postings")
        )

        if isinstance(postings, dict):
            postings_iterable = postings.values()
        else:
            postings_iterable = postings or []

        properties: List[Dict] = []

        for raw_posting in postings_iterable:
            if not isinstance(raw_posting, dict):
                continue
            transformed = self._transform_property_record(raw_posting, source)
            if transformed:
                properties.append(transformed)

        if not properties:
            logger.warning("No Zonaprop postings extracted", source=source)

        return properties

    def _transform_property_record(self, raw: Dict, source: str) -> Optional[Dict]:
        """Normalize a raw Zonaprop posting dictionary."""
        property_id = (
            raw.get("postingId")
            or raw.get("id")
            or raw.get("hash")
            or raw.get("code")
        )
        if not property_id:
            return None

        listing_url = None
        for candidate in (
            raw.get("url"),
            raw.get("canonicalUrl"),
            raw.get("permalink"),
            raw.get("sharingUrl"),
        ):
            if candidate:
                listing_url = urljoin(self.base_url, candidate)
                break

        data: Dict[str, Optional[float]] = {
            "id": str(property_id),
            "title": raw.get("titlePlainText")
            or raw.get("title")
            or raw.get("postingTitle"),
            "listing_url": listing_url,
        }

        data.update(self._extract_price_info(raw))

        location = raw.get("postingLocation") or {}
        address_info = location.get("postingAddress") or {}
        data["address"] = (
            address_info.get("formattedAddress")
            or address_info.get("address")
            or location.get("address")
            or location.get("neighborhoodName")
        )

        geolocation = {}
        posting_geo = location.get("postingGeolocation")
        if isinstance(posting_geo, dict):
            geolocation = posting_geo.get("geolocation") or {}
        if not geolocation and isinstance(location.get("geolocation"), dict):
            geolocation = location.get("geolocation") or {}

        data["latitude"] = self._to_float(geolocation.get("latitude"))
        data["longitude"] = self._to_float(geolocation.get("longitude"))

        feature_map = self._collect_feature_map(raw)

        data["rooms"] = self._to_float(
            raw.get("rooms")
            or feature_map.get("ambientes")
            or feature_map.get("dormitorios")
        )

        data["bathrooms"] = self._to_float(
            raw.get("bathrooms")
            or feature_map.get("banos")
            or feature_map.get("bano")
        )

        surface_candidate = (
            raw.get("surfaceMeters")
            or raw.get("surface")
            or feature_map.get("superficie_total")
            or feature_map.get("superficie_cubierta")
            or feature_map.get("sup_total")
        )
        data["surface_m2"] = self._to_float(surface_candidate)

        stats = raw.get("stats") or raw.get("postingStats") or {}
        views_value = (
            stats.get("usersViewsPerDay")
            or stats.get("viewsPerDay")
            or stats.get("usersViews")
        )
        data["views_per_day"] = self._to_float(views_value)

        return data

    def _collect_feature_map(self, raw: Dict) -> Dict[str, str]:
        """Collect feature entries from different sections into a normalized map."""
        feature_map: Dict[str, str] = {}

        def _collect(container):
            if isinstance(container, dict):
                for entry in container.values():
                    if isinstance(entry, dict):
                        label = entry.get("label") or entry.get("name")
                        value = entry.get("value") or entry.get("formattedValue")
                        if label and value is not None:
                            feature_map[self._slugify_feature_key(label)] = str(value)

        _collect(raw.get("mainFeatures"))

        general_features = raw.get("generalFeatures")
        if isinstance(general_features, dict):
            for group in general_features.values():
                _collect(group)

        characteristics = raw.get("characteristics")
        if isinstance(characteristics, list):
            for item in characteristics:
                if isinstance(item, dict):
                    label = item.get("name") or item.get("label")
                    value = item.get("value") or item.get("formattedValue")
                    if label and value is not None:
                        feature_map[self._slugify_feature_key(label)] = str(value)

        return feature_map

    @staticmethod
    def _slugify_feature_key(label: str) -> str:
        """Convert feature labels into normalized dictionary keys."""
        normalized = unicodedata.normalize("NFKD", label)
        normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
        normalized = normalized.lower()
        normalized = re.sub(r"[^a-z0-9]+", "_", normalized)
        return normalized.strip("_")

    @staticmethod
    def _to_float(value: Optional[object]) -> Optional[float]:
        """Convert a value into float if possible."""
        if value is None:
            return None

        if isinstance(value, (int, float)):
            return float(value)

        text = str(value)
        match = re.search(r"-?\d+(?:[.,]\d+)?", text)
        if not match:
            return None

        normalized = match.group(0).replace(".", "").replace(",", ".")
        try:
            return float(normalized)
        except ValueError:
            return None

    def _extract_price_info(self, raw: Dict) -> Dict[str, Optional[float]]:
        """Extract USD and ARS prices from a posting."""
        price_usd: Optional[float] = None
        price_ars: Optional[float] = None

        def _assign(amount: Optional[float], currency: Optional[str]) -> None:
            nonlocal price_usd, price_ars
            if amount is None or currency is None:
                return
            currency = currency.upper()
            if currency in {"USD", "US$", "U$S", "DOLARES", "DÓLARES"}:
                if price_usd is None:
                    price_usd = amount
            elif currency in {"ARS", "AR$", "PESOS", "PESOS ARGENTINOS"}:
                if price_ars is None:
                    price_ars = amount

        for operation in raw.get("priceOperationTypes") or []:
            for price in operation.get("prices") or []:
                amount = self._to_float(
                    price.get("amount")
                    or price.get("value")
                    or price.get("formattedAmount")
                )
                currency = price.get("currency")
                if isinstance(currency, dict):
                    currency = currency.get("id") or currency.get("symbol")
                elif isinstance(currency, str) and currency.startswith("$"):
                    currency = "ARS"
                _assign(amount, currency)

        if price_usd is None or price_ars is None:
            for key in ("priceString", "mainPrice", "price"):
                text = raw.get(key)
                if isinstance(text, str):
                    if price_usd is None:
                        usd_match = re.search(r"usd\s*([\d.,]+)", text, flags=re.I)
                        if usd_match:
                            price_usd = self._to_float(usd_match.group(1))
                    if price_ars is None:
                        ars_match = re.search(r"\$\s*([\d.,]+)", text)
                        if ars_match:
                            price_ars = self._to_float(ars_match.group(1))

        return {"price_usd": price_usd, "price_ars": price_ars}

    @staticmethod
    def _merge_property_records(existing: Dict, new: Dict) -> Dict:
        """Merge two property dictionaries, filling missing values."""
        for key, value in new.items():
            if key == "id":
                continue
            if value in (None, "", []):
                continue
            if key not in existing or existing[key] in (None, "", []):
                existing[key] = value
        return existing

    def _extract_total_pages(
        self, html_content: str, state: Optional[Dict] = None
    ) -> int:
        """Determine total number of pages available for the search."""
        if state:
            list_store = state.get("listStore") or {}

            potential_keys = [
                ("metadata", "paging", "totalPages"),
                ("metadata", "totalPages"),
                ("totalPages",),
            ]

            for path in potential_keys:
                node = list_store
                try:
                    for key in path:
                        node = node[key]
                except (KeyError, TypeError):
                    continue

                if isinstance(node, (int, float)) and node >= 1:
                    return int(node)
                if isinstance(node, str) and node.isdigit():
                    return int(node)

            search_metadata = state.get("search", {}).get("metadata", {})
            total = search_metadata.get("totalPages")
            if isinstance(total, (int, float)) and total >= 1:
                return int(total)

        match = re.search(r'"totalPages"\s*:\s*(\d+)', html_content)
        if match:
            return max(1, int(match.group(1)))

        return 1

    def _build_page_url(self, search_url: str, page_number: int) -> str:
        """Build the URL for a given results page."""
        if page_number <= 1:
            return search_url

        parsed = urlparse(search_url)
        path = parsed.path or ""

        if re.search(r"-pagina-\d+", path):
            new_path = re.sub(
                r"-pagina-\d+(\.html)?", f"-pagina-{page_number}.html", path
            )
        elif path.endswith(".html"):
            new_path = re.sub(r"\.html$", f"-pagina-{page_number}.html", path)
        else:
            base_path = path.rstrip("/")
            new_path = f"{base_path}-pagina-{page_number}.html"

        rebuilt = f"{parsed.scheme}://{parsed.netloc}{new_path}"

        if parsed.query:
            rebuilt = f"{rebuilt}?{parsed.query}"
        if parsed.fragment:
            rebuilt = f"{rebuilt}#{parsed.fragment}"

        return rebuilt

    def _populate_listing_views(self, properties: List[Dict]) -> List[Dict]:
        """Fetch listing detail pages to enrich with view metrics."""
        logger.info(
            "Fetching Zonaprop listing view metrics",
            total_properties=len(properties),
            max_requests=self.max_view_requests,
        )

        processed = 0
        for property_data in properties:
            if self.max_view_requests is not None and processed >= self.max_view_requests:
                logger.info(
                    "Reached maximum listing view requests",
                    processed=processed,
                    limit=self.max_view_requests,
                )
                break

            listing_url = property_data.get("listing_url")
            if not listing_url:
                continue

            try:
                detail_html = self._fetch_page(listing_url, bucket="detail")
            except ZonapropAntiBotError:
                logger.warning(
                    "Listing detail blocked by Cloudflare",
                    property_id=property_data.get("id"),
                    url=listing_url,
                )
                continue
            except ScrapingError as exc:
                logger.warning(
                    "Failed to fetch listing detail page",
                    property_id=property_data.get("id"),
                    url=listing_url,
                    error=str(exc),
                )
                continue

            views = self._extract_views_from_listing(detail_html)
            if views is not None:
                property_data["views_per_day"] = views
            processed += 1

        return properties

    @staticmethod
    def _extract_views_from_listing(html_content: str) -> Optional[float]:
        """Extract user views metric from a listing detail page."""
        if not html_content:
            return None

        match = re.search(r"usersViewsPerDay\s*=\s*(\d+(?:\.\d+)?)", html_content)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                return None

        match = re.search(r"usersViews\s*=\s*(\d+)", html_content)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                return None

        return None

    def _normalize_property_data(self, properties: List[Dict]) -> pd.DataFrame:
        """Normalize property data into consistent DataFrame.

        Args:
            properties: List of property dictionaries

        Returns:
            Normalized DataFrame with consistent schema
        """
        if not properties:
            # Return empty DataFrame with expected columns
            return pd.DataFrame(
                columns=[
                    "id",
                    "title",
                    "price_ars",
                    "price_usd",
                    "address",
                    "latitude",
                    "longitude",
                    "rooms",
                    "bathrooms",
                    "surface_m2",
                    "views_per_day",
                    "listing_url",
                ]
            )

        df = pd.DataFrame(properties)

        # Ensure all expected columns exist
        expected_columns = [
            "id",
            "title",
            "price_ars",
            "price_usd",
            "address",
            "latitude",
            "longitude",
            "rooms",
            "bathrooms",
            "surface_m2",
            "views_per_day",
            "listing_url",
        ]

        for col in expected_columns:
            if col not in df.columns:
                df[col] = None

        # Reorder columns
        df = df[expected_columns]

        # Convert data types
        numeric_columns = [
            "price_ars",
            "price_usd",
            "latitude",
            "longitude",
            "rooms",
            "bathrooms",
            "surface_m2",
            "views_per_day",
        ]

        for col in numeric_columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        # Remove duplicates based on ID
        df = df.drop_duplicates(subset=["id"], keep="first")

        return df


class ExchangeRateProvider:
    """Provides currency exchange rates with caching and fallback options.

    Supports multiple exchange rate sources with configurable TTL caching
    and fallback rates for reliability.
    """

    def __init__(self, config: ConfigManager):
        """Initialize ExchangeRateProvider with configuration.

        Args:
            config: ConfigManager instance with exchange rate settings
        """
        self.config = config
        self.provider = config.get("exchange_rates.provider", "xe.com")
        self.cache_ttl_hours = config.get("exchange_rates.cache_ttl_hours", 24)
        self.fallback_rate = config.get("exchange_rates.fallback_rate", 1000)  # ARS per USD

        self.cache_dir = Path(config.get("data.cache_dir", "~/.renta/cache")).expanduser()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_file = self.cache_dir / "exchange_rates.json"

        self._rate_cache = {}
        self._load_cache()

    def get_rate(self, from_currency: str, to_currency: str) -> float:
        """Get exchange rate between two currencies.

        Args:
            from_currency: Source currency code (e.g., 'ARS')
            to_currency: Target currency code (e.g., 'USD')

        Returns:
            Exchange rate as float

        Raises:
            AirbnbDataError: If rate cannot be retrieved and no fallback available
        """
        if from_currency == to_currency:
            return 1.0

        cache_key = f"{from_currency}_{to_currency}"

        # Check cache first
        if self.is_rate_fresh(from_currency, to_currency):
            return self._rate_cache[cache_key]["rate"]

        try:
            # Fetch fresh rate
            rate = self._fetch_rate(from_currency, to_currency)

            # Cache the rate
            self._rate_cache[cache_key] = {"rate": rate, "timestamp": time.time()}
            self._save_cache()

            return rate

        except Exception as e:
            # Try fallback rate for ARS/USD
            if (from_currency == "ARS" and to_currency == "USD") or (
                from_currency == "USD" and to_currency == "ARS"
            ):
                fallback = (
                    self.fallback_rate if from_currency == "ARS" else 1.0 / self.fallback_rate
                )
                return fallback

            raise AirbnbDataError(
                f"Failed to get exchange rate {from_currency} -> {to_currency}: {e}",
                details={
                    "from_currency": from_currency,
                    "to_currency": to_currency,
                    "provider": self.provider,
                    "error_type": type(e).__name__,
                },
            )

    def is_rate_fresh(self, from_currency: str, to_currency: str) -> bool:
        """Check if cached rate is still fresh.

        Args:
            from_currency: Source currency code
            to_currency: Target currency code

        Returns:
            True if rate is fresh, False if needs refresh
        """
        cache_key = f"{from_currency}_{to_currency}"

        if cache_key not in self._rate_cache:
            return False

        cached_data = self._rate_cache[cache_key]
        age_hours = (time.time() - cached_data["timestamp"]) / 3600

        return age_hours < self.cache_ttl_hours

    def _fetch_rate(self, from_currency: str, to_currency: str) -> float:
        """Fetch exchange rate from configured provider.

        Args:
            from_currency: Source currency code
            to_currency: Target currency code

        Returns:
            Exchange rate as float

        Raises:
            Exception: If rate cannot be fetched
        """
        if self.provider == "xe.com":
            return self._fetch_from_xe(from_currency, to_currency)
        elif self.provider == "bcra":
            return self._fetch_from_bcra(from_currency, to_currency)
        else:
            raise ValueError(f"Unsupported exchange rate provider: {self.provider}")

    def _fetch_from_xe(self, from_currency: str, to_currency: str) -> float:
        """Fetch rate from XE.com (simplified implementation).

        Note: This is a simplified implementation. Real implementation would
        need to handle XE.com's actual API or scraping requirements.
        """
        # For demo purposes, return a mock rate for ARS/USD
        if from_currency == "ARS" and to_currency == "USD":
            return 1.0 / 1000  # 1000 ARS = 1 USD
        elif from_currency == "USD" and to_currency == "ARS":
            return 1000  # 1 USD = 1000 ARS
        else:
            raise ValueError(f"Unsupported currency pair: {from_currency}/{to_currency}")

    def _fetch_from_bcra(self, from_currency: str, to_currency: str) -> float:
        """Fetch rate from BCRA API (Banco Central de la República Argentina).

        Note: This would connect to the official BCRA API for ARS rates.
        """
        # Simplified implementation - would use actual BCRA API
        if from_currency == "ARS" and to_currency == "USD":
            return 1.0 / 1000
        elif from_currency == "USD" and to_currency == "ARS":
            return 1000
        else:
            raise ValueError(f"BCRA only supports ARS rates")

    def _load_cache(self) -> None:
        """Load exchange rate cache from file."""
        try:
            if self.cache_file.exists():
                with open(self.cache_file, "r") as f:
                    self._rate_cache = json.load(f)
        except Exception as e:
            logger.debug(
                "Failed to load exchange rate cache, starting with empty cache",
                error=str(e),
                cache_file=str(self.cache_file),
            )
            self._rate_cache = {}

    def _save_cache(self) -> None:
        """Save exchange rate cache to file."""
        try:
            with open(self.cache_file, "w") as f:
                json.dump(self._rate_cache, f, indent=2)
        except Exception as e:
            logger.warning(
                "Failed to save exchange rate cache", error=str(e), cache_file=str(self.cache_file)
            )


class DataProcessor:
    """Processes and normalizes raw data from various sources.

    Handles data cleaning, currency conversion, validation, and schema
    normalization for both Airbnb and Zonaprop data.
    """

    def __init__(self, config: ConfigManager):
        """Initialize DataProcessor with configuration.

        Args:
            config: ConfigManager instance with processing settings
        """
        self.config = config
        self.exchange_provider = ExchangeRateProvider(config)
        self._historical_rate_cache: Dict[str, Optional[float]] = {}

        # Processing options
        self.keep_intermediates = config.get("debug.keep_intermediates", False)
        self.remove_airbnb_outliers = config.get("airbnb.processing.remove_outliers", True)
        self.airbnb_outlier_sigma = config.get("airbnb.processing.outlier_sigma", 3.0)

        # Cache directory for processed data
        self.cache_dir = Path(config.get("data.cache_dir", "~/.renta/cache")).expanduser()
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def load_airbnb_data(self, file_paths: Dict[str, str]) -> pd.DataFrame:
        """Load Airbnb data from downloaded CSV files.

        Args:
            file_paths: Dictionary mapping file type to local file path

        Returns:
            Combined Airbnb DataFrame

        Raises:
            AirbnbDataError: If loading fails
        """
        try:
            # Load listings data (main dataset)
            if "listings" not in file_paths:
                raise AirbnbDataError("Missing listings file in downloaded data")
            
            listings_df = pd.read_csv(file_paths["listings"], compression='gzip')
            
            # For now, we'll focus on the listings data
            # Reviews and calendar data can be added later for more advanced analysis
            return listings_df
            
        except Exception as e:
            raise AirbnbDataError(
                f"Failed to load Airbnb data: {e}",
                details={"error_type": type(e).__name__, "file_paths": file_paths}
            )

    def process_airbnb_listings(self, raw_data: pd.DataFrame) -> pd.DataFrame:
        """Clean and normalize Airbnb data.

        Args:
            raw_data: Raw Airbnb DataFrame from CSV files

        Returns:
            Cleaned and normalized Airbnb DataFrame

        Raises:
            AirbnbDataError: If processing fails
        """
        try:
            df = raw_data.copy()

            # Validate required columns (check for either raw or processed column names)
            base_required_columns = ["id", "latitude", "longitude", "room_type"]
            
            # Check for price column (either raw 'price' or processed 'price_usd_per_night')
            has_price = "price" in df.columns or "price_usd_per_night" in df.columns
            
            print(f"DEBUG: Available columns: {list(df.columns)}")
            print(f"DEBUG: Has price: {has_price}")
            
            missing_columns = [col for col in base_required_columns if col not in df.columns]
            if not has_price:
                missing_columns.append("price or price_usd_per_night")
            if missing_columns:
                raise AirbnbDataError(
                    f"Missing required columns in Airbnb data: {missing_columns}",
                    details={
                        "missing_columns": missing_columns,
                        "available_columns": list(df.columns),
                    },
                )

            # Clean and validate coordinates
            df = self._clean_coordinates(df)

            # Convert price to USD
            df = self._convert_airbnb_prices(df)

            # Clean room types
            df = self._clean_room_types(df)

            # Normalize bathrooms and beds to numeric values
            df = self._clean_bathrooms_and_beds(df)

            # Handle missing values
            df = self._handle_missing_values(df, "airbnb")

            # Validate data quality
            df = self._validate_airbnb_data(df)

            # Create consistent schema
            df = self._normalize_airbnb_schema(df)

            # Optionally remove extreme price outliers
            if self.remove_airbnb_outliers:
                df = self._remove_price_outliers(df)

            return df

        except Exception as e:
            if isinstance(e, AirbnbDataError):
                raise
            raise AirbnbDataError(
                f"Failed to process Airbnb data: {e}",
                details={"error_type": type(e).__name__, "rows": len(raw_data)},
            )

    def process_zonaprop_listings(self, raw_data: pd.DataFrame) -> pd.DataFrame:
        """Clean and normalize Zonaprop data.

        Args:
            raw_data: Raw Zonaprop DataFrame from scraping

        Returns:
            Cleaned and normalized Zonaprop DataFrame

        Raises:
            ScrapingError: If processing fails
        """
        try:
            df = raw_data.copy()

            # Validate required columns
            required_columns = ["id", "title"]
            missing_columns = [col for col in required_columns if col not in df.columns]
            if missing_columns:
                raise ScrapingError(
                    f"Missing required columns in Zonaprop data: {missing_columns}",
                    details={
                        "missing_columns": missing_columns,
                        "available_columns": list(df.columns),
                    },
                )

            # Clean and validate coordinates
            df = self._clean_coordinates(df)

            # Convert prices to USD
            df = self._convert_zonaprop_prices(df)

            # Clean text fields
            df = self._clean_text_fields(df)

            # Handle missing values
            df = self._handle_missing_values(df, "zonaprop")

            # Validate data quality
            df = self._validate_zonaprop_data(df)

            # Create consistent schema
            df = self._normalize_zonaprop_schema(df)

            return df

        except Exception as e:
            if isinstance(e, ScrapingError):
                raise
            raise ScrapingError(
                f"Failed to process Zonaprop data: {e}",
                details={"error_type": type(e).__name__, "rows": len(raw_data)},
            )

    def convert_currency(
        self, amounts: pd.Series, from_currency: str, to_currency: str
    ) -> pd.Series:
        """Convert currency using exchange rate provider.

        Args:
            amounts: Series of monetary amounts
            from_currency: Source currency code
            to_currency: Target currency code

        Returns:
            Series with converted amounts

        Raises:
            AirbnbDataError: If conversion fails
        """
        try:
            if from_currency == to_currency:
                return amounts

            rate = self.exchange_provider.get_rate(from_currency, to_currency)
            return amounts * rate

        except Exception as e:
            raise AirbnbDataError(
                f"Currency conversion failed {from_currency} -> {to_currency}: {e}",
                details={
                    "from_currency": from_currency,
                    "to_currency": to_currency,
                    "error_type": type(e).__name__,
                },
            )

    def _clean_coordinates(self, df: pd.DataFrame) -> pd.DataFrame:
        """Clean and validate latitude/longitude coordinates."""
        # Convert to numeric
        if "latitude" in df.columns:
            df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
        if "longitude" in df.columns:
            df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")

        # Validate Buenos Aires bounds (approximate)
        if "latitude" in df.columns and "longitude" in df.columns:
            # Buenos Aires bounds: roughly -35.0 to -34.0 lat, -59.0 to -58.0 lon
            valid_coords = (df["latitude"].between(-35.0, -34.0)) & (
                df["longitude"].between(-59.0, -58.0)
            )

            # Set invalid coordinates to NaN
            df.loc[~valid_coords, ["latitude", "longitude"]] = None

        return df

    def _convert_airbnb_prices(self, df: pd.DataFrame) -> pd.DataFrame:
        """Convert Airbnb prices to USD."""
        if "price" not in df.columns:
            return df

        # Preserve original string values and create numeric ARS price column
        price_numeric = (
            df["price"]
            .astype(str)
            .str.replace(r"[^\d.,]", "", regex=True)
            .str.replace(",", "")
        )
        df["price_ars_per_night"] = pd.to_numeric(price_numeric, errors="coerce")

        # Ensure last_scraped exists and is datetime for rate lookup
        if "last_scraped" in df.columns:
            df["last_scraped"] = pd.to_datetime(df["last_scraped"], errors="coerce")

        unique_dates: Iterable[date] = []
        if "last_scraped" in df.columns:
            unique_dates = sorted(
                {ts.date() for ts in df["last_scraped"].dropna() if isinstance(ts, pd.Timestamp)}
            )

        rates_by_date = self._get_historical_ars_usd_rates(unique_dates)

        fallback_multiplier: Optional[float] = None
        fallback_ars_per_usd: Optional[float] = None
        try:
            fallback_multiplier = self.exchange_provider.get_rate("ARS", "USD")
            if fallback_multiplier not in (None, 0):
                fallback_ars_per_usd = 1.0 / fallback_multiplier
        except AirbnbDataError as exc:
            logger.warning(
                "Failed to obtain fallback ARS/USD rate, USD conversion may be missing",
                error=str(exc),
            )

        def resolve_rate(ts: Optional[pd.Timestamp]) -> Optional[float]:
            if isinstance(ts, pd.Timestamp) and not pd.isna(ts):
                rate = rates_by_date.get(ts.date())
                if rate:
                    return rate
            return fallback_ars_per_usd

        if "last_scraped" in df.columns:
            fx_rates = df["last_scraped"].apply(resolve_rate)
        else:
            fx_rates = pd.Series(fallback_ars_per_usd, index=df.index)

        df["fx_rate_ars_per_usd"] = pd.to_numeric(fx_rates, errors="coerce")
        df.loc[df["fx_rate_ars_per_usd"] <= 0, "fx_rate_ars_per_usd"] = pd.NA

        # Convert to USD (ARS price divided by ARS per USD rate)
        df["price_usd_per_night"] = df["price_ars_per_night"] / df["fx_rate_ars_per_usd"]

        return df

    def _get_historical_ars_usd_rates(self, dates: Iterable[date]) -> Dict[date, Optional[float]]:
        """Fetch ARS per USD historical rates for the provided dates."""
        rates: Dict[date, Optional[float]] = {}

        for day in dates:
            cache_key = day.isoformat()
            if cache_key in self._historical_rate_cache:
                cached_rate = self._historical_rate_cache[cache_key]
                if cached_rate is not None:
                    rates[day] = cached_rate
                continue

            try:
                rate = self._fetch_ars_usd_rate_for_date(day)
                self._historical_rate_cache[cache_key] = rate
                if rate is not None:
                    rates[day] = rate
            except Exception as exc:
                self._historical_rate_cache[cache_key] = None
                logger.warning(
                    "Failed to fetch historical ARS/USD rate",
                    date=cache_key,
                    error=str(exc),
                )

        return rates

    def _fetch_ars_usd_rate_for_date(self, day: date) -> Optional[float]:
        """Retrieve ARS per USD rate for a specific day using XE tables."""
        url = f"https://www.xe.com/currencytables/?from=ARS&date={day:%Y-%m-%d}"
        tables = pd.read_html(url)
        if not tables:
            return None

        table = tables[0]
        usd_row = table[table["Currency"] == "USD"]
        if usd_row.empty:
            return None

        rate = pd.to_numeric(usd_row["ARS per unit"], errors="coerce").iloc[0]
        return float(rate) if not pd.isna(rate) else None

    def _convert_zonaprop_prices(self, df: pd.DataFrame) -> pd.DataFrame:
        """Convert Zonaprop prices to USD."""
        # Convert ARS prices to USD
        if "price_ars" in df.columns:
            df["price_usd"] = self.convert_currency(df["price_ars"], "ARS", "USD")

        # USD prices are already in USD
        if "price_usd" not in df.columns:
            df["price_usd"] = None

        return df

    def _clean_room_types(self, df: pd.DataFrame) -> pd.DataFrame:
        """Standardize room type values."""
        if "room_type" in df.columns:
            # Standardize room type names
            room_type_mapping = {
                "Entire home/apt": "Entire home/apt",
                "Private room": "Private room",
                "Shared room": "Shared room",
                "Hotel room": "Hotel room",
            }

            # Apply mapping with case-insensitive matching
            df["room_type"] = df["room_type"].str.strip()
            for original, standard in room_type_mapping.items():
                mask = df["room_type"].str.contains(original, case=False, na=False)
                df.loc[mask, "room_type"] = standard

        return df

    def _clean_bathrooms_and_beds(self, df: pd.DataFrame) -> pd.DataFrame:
        """Convert bathrooms and beds columns to numeric values."""
        if "bathrooms_text" in df.columns:
            numeric = df["bathrooms_text"].astype(str).str.extract(r"(\d+\.?\d*)")
            df["bathrooms"] = pd.to_numeric(numeric[0], errors="coerce")
            df = df.drop(columns=["bathrooms_text"])

        if "bathrooms" in df.columns:
            df["bathrooms"] = pd.to_numeric(df["bathrooms"], errors="coerce")

        if "beds" in df.columns:
            df["beds"] = pd.to_numeric(df["beds"], errors="coerce")

        return df

    def _clean_text_fields(self, df: pd.DataFrame) -> pd.DataFrame:
        """Clean text fields (titles, addresses, etc.)."""
        text_columns = ["title", "address"]

        for col in text_columns:
            if col in df.columns:
                # Strip whitespace and normalize
                df[col] = df[col].astype(str).str.strip()

                # Replace empty strings with None
                df.loc[df[col] == "", col] = None
                df.loc[df[col] == "nan", col] = None

        return df

    def _handle_missing_values(self, df: pd.DataFrame, data_type: str) -> pd.DataFrame:
        """Handle missing values based on data type and business rules."""
        if data_type == "airbnb":
            # Do not drop rows; retain full dataset for downstream indexing
            return df

        elif data_type == "zonaprop":
            # For Zonaprop, we need at least ID and some price info
            # Keep rows even with missing coordinates (can be geocoded later)
            df = df.dropna(subset=["id"])

        return df

    def _validate_airbnb_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """Validate Airbnb data quality."""
        if "id" in df.columns:
            df = df.drop_duplicates(subset=["id"], keep="first")

        return df

    def _remove_price_outliers(self, df: pd.DataFrame) -> pd.DataFrame:
        """Drop listings with extreme prices using z-score filtering."""
        price_col = "price_usd_per_night"
        if price_col not in df.columns:
            return df

        prices = pd.to_numeric(df[price_col], errors="coerce")
        if prices.isna().all():
            return df

        mean = prices.mean()
        std = prices.std(ddof=0)
        if std == 0 or pd.isna(std):
            return df

        threshold = self.airbnb_outlier_sigma or 3.0
        z_scores = (prices - mean).abs() / std
        filtered_df = df[z_scores <= threshold]

        return filtered_df

    def _validate_zonaprop_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """Validate Zonaprop data quality."""
        # Remove invalid prices (negative or extremely high)
        if "price_usd" in df.columns:
            valid_price = (df["price_usd"].isna()) | (
                (df["price_usd"] > 0) & (df["price_usd"] < 10000000)
            )
            df = df[valid_price]

        # Remove duplicate properties
        if "id" in df.columns:
            df = df.drop_duplicates(subset=["id"], keep="first")

        return df

    def _normalize_airbnb_schema(self, df: pd.DataFrame) -> pd.DataFrame:
        """Create consistent Airbnb schema."""
        # Define expected columns with defaults
        expected_schema = {
            "id": str,
            "listing_url": str,
            "last_scraped": "datetime",
            "latitude": float,
            "longitude": float,
            "room_type": str,
            "price_ars_per_night": float,
            "price_usd_per_night": float,
            "fx_rate_ars_per_usd": float,
            "beds": float,
            "bathrooms": float,
            "review_score_rating": float,
            "review_score_location": float,
            "review_score_value": float,
            "neighbourhood": str,
            "last_review": "datetime",
            "estimated_nights_booked_l30d": float,
        }

        # Ensure all columns exist
        for col, dtype in expected_schema.items():
            if col not in df.columns:
                df[col] = None

        # Reorder columns
        df = df[list(expected_schema.keys())]

        # Convert data types
        for col, dtype in expected_schema.items():
            if dtype == float:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            elif dtype == str:
                df[col] = df[col].astype(str)
                df.loc[df[col] == "nan", col] = None
            elif dtype == "datetime":
                df[col] = pd.to_datetime(df[col], errors="coerce")

        # Add derived fields
        df["estimated_nights_booked_l30d"] = self._estimate_nights_booked(df)
        df["estimated_nights_booked"] = self._estimate_occupancy_category(df)

        return df

    def _normalize_zonaprop_schema(self, df: pd.DataFrame) -> pd.DataFrame:
        """Create consistent Zonaprop schema."""
        # Define expected columns
        expected_schema = {
            "id": str,
            "title": str,
            "price_ars": float,
            "price_usd": float,
            "address": str,
            "latitude": float,
            "longitude": float,
            "rooms": float,
            "bathrooms": float,
            "surface_m2": float,
            "views_per_day": float,
            "listing_url": str,
        }

        # Ensure all columns exist
        for col, dtype in expected_schema.items():
            if col not in df.columns:
                df[col] = None

        # Reorder columns
        df = df[list(expected_schema.keys())]

        # Convert data types
        for col, dtype in expected_schema.items():
            if dtype == float:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            elif dtype == str:
                df[col] = df[col].astype(str)
                df.loc[df[col] == "nan", col] = None

        return df

    def _estimate_occupancy_category(self, df: pd.DataFrame) -> pd.Series:
        """Estimate occupancy category based on available data.

        This is a simplified heuristic. Real implementation would use
        calendar availability data and booking patterns.
        """
        if "estimated_nights_booked_l30d" in df.columns:
            nights = pd.to_numeric(df["estimated_nights_booked_l30d"], errors="coerce").fillna(0)
            occupancy = pd.Series("low", index=df.index)
            occupancy.loc[nights > 14] = "high"
            occupancy.loc[(nights >= 7) & (nights <= 14)] = "medium"
            return occupancy

        # Fallback heuristic if estimated nights not available
        occupancy = pd.Series("medium", index=df.index)
        if "number_of_reviews" in df.columns and "review_score_rating" in df.columns:
            high_occupancy = (df["number_of_reviews"] > 50) & (df["review_score_rating"] > 4.5)
            occupancy.loc[high_occupancy] = "high"
        if "number_of_reviews" in df.columns:
            low_occupancy = df["number_of_reviews"] < 5
            occupancy.loc[low_occupancy] = "low"
        return occupancy

    def _estimate_nights_booked(self, df: pd.DataFrame) -> pd.Series:
        """Estimate total nights booked in the last 30 days based on review cadence."""
        if "number_of_reviews_l30d" in df.columns:
            reviews = pd.to_numeric(df["number_of_reviews_l30d"], errors="coerce").fillna(0)
        elif "reviews_per_month" in df.columns:
            reviews = pd.to_numeric(df["reviews_per_month"], errors="coerce").fillna(0) * (30.0 / 30.0)
        else:
            reviews = pd.Series(0, index=df.index)

        estimated_nights = (reviews / 0.50) * 3.0
        estimated_nights = estimated_nights.clip(lower=0, upper=21)  # 70% occupancy cap
        return estimated_nights
