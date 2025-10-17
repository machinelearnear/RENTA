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
from datetime import date
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import urljoin, urlparse
import requests
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
        self.rate_limit = config.get("zonaprop.scraping.rate_limit_seconds", 5)
        self.max_retries = config.get("zonaprop.scraping.max_retries", 3)
        self.user_agents = config.get(
            "zonaprop.scraping.user_agents",
            [
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            ],
        )

        self.session = requests.Session()
        self.last_request_time = 0

        # Allowed domains for scraping (security measure)
        self.allowed_domains = ["zonaprop.com.ar", "www.zonaprop.com.ar"]

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
            # Validate URL for security
            self._validate_url(search_url)

            # Get search results page
            html_content = self._fetch_page(search_url)

            # Parse property listings
            properties = self._parse_search_results(html_content, search_url)

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
                # Single file
                with open(html_path, "r", encoding="utf-8") as f:
                    html_content = f.read()
                properties = self._parse_search_results(html_content, str(html_path))

            elif html_path.is_dir():
                # Directory of HTML files
                properties = []
                for html_file in html_path.glob("*.html"):
                    with open(html_file, "r", encoding="utf-8") as f:
                        html_content = f.read()
                    file_properties = self._parse_search_results(html_content, str(html_file))
                    properties.extend(file_properties)
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

    def _fetch_page(self, url: str) -> str:
        """Fetch a web page with rate limiting and anti-bot detection.

        Args:
            url: URL to fetch

        Returns:
            HTML content as string

        Raises:
            ZonapropAntiBotError: If anti-bot protection detected
            ScrapingError: If request fails
        """
        # Validate URL before fetching
        self._validate_url(url)

        # Rate limiting
        time_since_last = time.time() - self.last_request_time
        if time_since_last < self.rate_limit:
            time.sleep(self.rate_limit - time_since_last)

        for attempt in range(self.max_retries):
            try:
                # Random user agent
                headers = {
                    "User-Agent": random.choice(self.user_agents),
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
                    "Accept-Encoding": "gzip, deflate",
                    "Connection": "keep-alive",
                    "Upgrade-Insecure-Requests": "1",
                }

                response = self.session.get(url, headers=headers, timeout=30)
                self.last_request_time = time.time()

                # Check for anti-bot protection
                if response.status_code == 403:
                    raise ZonapropAntiBotError(
                        details={"status_code": 403, "url": url, "attempt": attempt + 1}
                    )

                if response.status_code >= 400:
                    if attempt == self.max_retries - 1:
                        raise ZonapropAntiBotError(
                            f"HTTP {response.status_code} after {self.max_retries} attempts",
                            details={"status_code": response.status_code, "url": url},
                        )
                    continue

                # Check for Cloudflare or other anti-bot indicators
                content_lower = response.text.lower()
                anti_bot_indicators = [
                    "cloudflare",
                    "checking your browser",
                    "please wait while we verify",
                    "ddos protection",
                    "security check",
                ]

                if any(indicator in content_lower for indicator in anti_bot_indicators):
                    raise ZonapropAntiBotError(
                        "Anti-bot protection detected in page content",
                        details={"url": url, "indicators_found": True},
                    )

                return response.text

            except requests.RequestException as e:
                if attempt == self.max_retries - 1:
                    raise ScrapingError(
                        f"Failed to fetch {url} after {self.max_retries} attempts: {e}",
                        details={"url": url, "error_type": type(e).__name__},
                    )

                # Wait before retry
                time.sleep(2**attempt)

        raise ScrapingError(f"Failed to fetch {url} after all retries")

    def _parse_search_results(self, html_content: str, source: str) -> List[Dict]:
        """Parse property listings from HTML content.

        Args:
            html_content: HTML content to parse
            source: Source identifier (URL or file path)

        Returns:
            List of property dictionaries
        """
        soup = BeautifulSoup(html_content, "html.parser")
        properties = []

        # Zonaprop typically uses specific CSS classes for property listings
        # This is a simplified parser - real implementation would need to handle
        # Zonaprop's actual HTML structure

        # Look for property cards/listings
        property_elements = soup.find_all(
            ["div", "article"], class_=re.compile(r"(property|listing|card)", re.I)
        )

        if not property_elements:
            # Fallback: look for common patterns
            property_elements = soup.find_all("div", attrs={"data-id": True})

        for element in property_elements:
            try:
                property_data = self._extract_property_details(element)
                if property_data:
                    property_data["source"] = source
                    properties.append(property_data)
            except Exception as e:
                # Log warning but continue processing
                logger.warning(
                    "Failed to extract property details",
                    element_id=element.get("id") or element.get("data-id"),
                    error=str(e),
                )
                continue

        return properties

    def _extract_property_details(self, element) -> Optional[Dict]:
        """Extract property details from a single listing element.

        Args:
            element: BeautifulSoup element containing property data

        Returns:
            Dictionary with property details or None if extraction fails
        """
        try:
            property_data = {}

            # Extract ID (from data attributes or URL)
            prop_id = element.get("data-id") or element.get("id")
            if not prop_id:
                # Try to extract from link
                link = element.find("a", href=True)
                if link:
                    href = link["href"]
                    id_match = re.search(r"/(\d+)/?", href)
                    if id_match:
                        prop_id = id_match.group(1)

            if not prop_id:
                return None

            property_data["id"] = prop_id

            # Extract title
            title_elem = element.find(["h1", "h2", "h3", "h4"], class_=re.compile(r"title", re.I))
            if not title_elem:
                title_elem = element.find("a", href=True)
            property_data["title"] = title_elem.get_text(strip=True) if title_elem else None

            # Extract price (look for currency symbols and numbers)
            price_text = element.get_text()

            # ARS price
            ars_match = re.search(r"\$\s*([\d.,]+)", price_text)
            if ars_match:
                price_str = ars_match.group(1).replace(",", "").replace(".", "")
                try:
                    property_data["price_ars"] = float(price_str)
                except ValueError:
                    property_data["price_ars"] = None
            else:
                property_data["price_ars"] = None

            # USD price
            usd_match = re.search(r"USD?\s*([\d.,]+)", price_text, re.I)
            if usd_match:
                price_str = usd_match.group(1).replace(",", "")
                try:
                    property_data["price_usd"] = float(price_str)
                except ValueError:
                    property_data["price_usd"] = None
            else:
                property_data["price_usd"] = None

            # Extract address
            address_elem = element.find(
                ["span", "div", "p"], class_=re.compile(r"(address|location|zona)", re.I)
            )
            property_data["address"] = address_elem.get_text(strip=True) if address_elem else None

            # Extract coordinates (if available in data attributes or scripts)
            lat = element.get("data-lat") or element.get("data-latitude")
            lon = element.get("data-lon") or element.get("data-longitude")

            if lat and lon:
                try:
                    property_data["latitude"] = float(lat)
                    property_data["longitude"] = float(lon)
                except ValueError:
                    property_data["latitude"] = None
                    property_data["longitude"] = None
            else:
                property_data["latitude"] = None
                property_data["longitude"] = None

            # Extract property metrics
            metrics_text = element.get_text()

            # Rooms
            rooms_match = re.search(r"(\d+)\s*(amb|ambiente|habitacion)", metrics_text, re.I)
            if rooms_match:
                try:
                    property_data["rooms"] = int(rooms_match.group(1))
                except ValueError:
                    property_data["rooms"] = None
            else:
                property_data["rooms"] = None

            # Bathrooms
            bath_match = re.search(r"(\d+(?:\.\d+)?)\s*(baño|bathroom)", metrics_text, re.I)
            if bath_match:
                try:
                    property_data["bathrooms"] = float(bath_match.group(1))
                except ValueError:
                    property_data["bathrooms"] = None
            else:
                property_data["bathrooms"] = None

            # Surface area
            m2_match = re.search(r"(\d+(?:\.\d+)?)\s*m[²2]", metrics_text, re.I)
            if m2_match:
                try:
                    property_data["surface_m2"] = float(m2_match.group(1))
                except ValueError:
                    property_data["surface_m2"] = None
            else:
                property_data["surface_m2"] = None

            # Extract engagement metrics (views, favorites)
            views_match = re.search(r"(\d+)\s*(vista|view)", metrics_text, re.I)
            if views_match:
                try:
                    property_data["views_per_day"] = int(views_match.group(1))
                except ValueError:
                    property_data["views_per_day"] = None
            else:
                property_data["views_per_day"] = None

            # Extract listing URL
            link_elem = element.find("a", href=True)
            if link_elem:
                href = link_elem["href"]
                if href.startswith("/"):
                    href = "https://www.zonaprop.com.ar" + href
                property_data["listing_url"] = href
            else:
                property_data["listing_url"] = None

            return property_data

        except Exception:
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
