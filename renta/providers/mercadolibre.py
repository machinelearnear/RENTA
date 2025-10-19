"""MercadoLibre real estate data provider.

This module implements the MercadoLibre provider for fetching real estate
listings from the MercadoLibre API. It provides a unified interface for
accessing property data from Argentina's second-largest real estate platform.
"""

import time
import json
import requests
from typing import Dict, Optional, List, Any, Tuple
from datetime import datetime, timedelta
import pandas as pd
from urllib.parse import urlencode

from .base import BaseRealEstateProvider
from ..exceptions import ProviderAPIError, ProviderRateLimitError


class MercadoLibreProvider(BaseRealEstateProvider):
    """Provider for MercadoLibre real estate data.
    
    Fetches property listings from MercadoLibre's public API and normalizes
    the data to the unified RENTA schema. Supports filtering by location,
    property type, and operation type with automatic pagination and caching.
    
    This provider offers several advantages:
    - Official API access (no scraping required)
    - High reliability and consistent data format
    - Built-in rate limiting and retry logic
    - Comprehensive property metadata
    - Location hierarchy support (state/city/neighborhood)
    
    Supported property types:
    - apartment: Departamentos
    - house: Casas  
    - land: Terrenos y Lotes
    - commercial: Locales
    - office: Oficinas
    
    Supported operation types:
    - sale: Venta
    - rent: Alquiler
    - temporary_rent: Alquiler temporal
    
    Example:
        >>> from renta.providers.mercadolibre import MercadoLibreProvider
        >>> from renta.config import ConfigManager
        >>> 
        >>> config = ConfigManager()
        >>> provider = MercadoLibreProvider(config)
        >>> 
        >>> # Fetch apartments for rent in Palermo
        >>> properties = provider.fetch_properties(
        ...     location="palermo",
        ...     property_type="apartment", 
        ...     operation_type="rent",
        ...     max_results=100
        ... )
        >>> print(f"Found {len(properties)} properties")
    
    API Documentation: https://developers.mercadolibre.com.ar/
    """
    
    # MercadoLibre API endpoints
    BASE_URL = "https://api.mercadolibre.com"
    SEARCH_ENDPOINT = "/sites/MLA/search"
    CATEGORIES_ENDPOINT = "/categories"
    LOCATIONS_ENDPOINT = "/classified_locations"
    
    # Category mappings for property types
    CATEGORY_MAPPING = {
        "apartment": "MLA1472",  # Departamentos
        "house": "MLA1466",      # Casas
        "land": "MLA1493",       # Terrenos y Lotes
        "commercial": "MLA79242", # Locales
        "office": "MLA50538",    # Oficinas
    }
    
    # Operation type mappings
    OPERATION_MAPPING = {
        "sale": "venta",
        "rent": "alquiler",
        "temporary_rent": "alquiler_temporal",
    }
    
    def __init__(self, config):
        """Initialize MercadoLibre provider.
        
        Args:
            config: ConfigManager instance with provider configuration
        """
        super().__init__(config)
        
        # Load MercadoLibre-specific configuration
        ml_config = self.provider_config
        
        self.max_results_per_request = ml_config.get("max_results_per_request", 50)
        self.country = ml_config.get("defaults", {}).get("country", "AR")
        self.default_state = ml_config.get("defaults", {}).get("state", "TUxBUENBUGw3M2E1")  # Capital Federal
        
        # Set up HTTP session
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "RENTA/1.0.0 (Real Estate Network and Trend Analyzer)",
            "Accept": "application/json",
            "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
        })
        self.session.timeout = self.timeout_seconds
        
        self.logger.info(
            "Initialized MercadoLibre provider",
            provider=self.get_provider_name(),
            rate_limit=self.rate_limit_seconds,
            timeout=self.timeout_seconds,
            max_results_per_request=self.max_results_per_request
        )
    
    def get_provider_name(self) -> str:
        """Return the unique name of this provider.
        
        Returns:
            String identifier 'mercadolibre'
        """
        return "mercadolibre"
    
    def validate_filters(self, **filters) -> Dict[str, Any]:
        """Validate and normalize filter parameters.
        
        Args:
            **filters: Filter parameters to validate
            
        Returns:
            Dictionary of validated and normalized filters
            
        Raises:
            ProviderError: If filters are invalid
        """
        validated = {}
        
        # Validate property_type
        if "property_type" in filters and filters["property_type"]:
            prop_type = filters["property_type"].lower()
            if prop_type not in self.CATEGORY_MAPPING:
                available = ", ".join(self.CATEGORY_MAPPING.keys())
                raise ProviderAPIError(
                    f"Invalid property_type '{prop_type}'. Available: {available}"
                )
            validated["property_type"] = prop_type
        
        # Validate operation_type
        if "operation_type" in filters and filters["operation_type"]:
            op_type = filters["operation_type"].lower()
            if op_type not in self.OPERATION_MAPPING:
                available = ", ".join(self.OPERATION_MAPPING.keys())
                raise ProviderAPIError(
                    f"Invalid operation_type '{op_type}'. Available: {available}"
                )
            validated["operation_type"] = op_type
        
        # Validate max_results
        if "max_results" in filters and filters["max_results"]:
            max_results = filters["max_results"]
            if not isinstance(max_results, int) or max_results <= 0:
                raise ProviderAPIError("max_results must be a positive integer")
            validated["max_results"] = max_results
        
        # Pass through other filters
        for key in ["location", "force_refresh"]:
            if key in filters and filters[key] is not None:
                validated[key] = filters[key]
        
        return validated
    
    def fetch_properties(
        self,
        location: Optional[str] = None,
        property_type: Optional[str] = None,
        operation_type: Optional[str] = None,
        max_results: Optional[int] = None,
        force_refresh: bool = False,
        **kwargs
    ) -> pd.DataFrame:
        """Fetch property listings from MercadoLibre API.
        
        Retrieves property listings from MercadoLibre's public API with support
        for location, property type, and operation type filtering. Automatically
        handles pagination to fetch all available results up to the specified limit.
        
        The method includes intelligent caching to avoid redundant API calls and
        respects rate limits to prevent being blocked by the API. Location names
        are automatically resolved to MercadoLibre location IDs for more accurate
        filtering.
        
        Args:
            location: Location filter - can be neighborhood, city, or state name.
                     Examples: "palermo", "capital federal", "recoleta"
            property_type: Type of property to search for. Valid options:
                          "apartment", "house", "land", "commercial", "office"
            operation_type: Type of operation. Valid options:
                           "sale", "rent", "temporary_rent"
            max_results: Maximum number of properties to return. If None, uses
                        a reasonable default (200). API pagination is handled
                        automatically to fetch this many results.
            force_refresh: If True, bypasses cache and fetches fresh data from API.
                          Useful when you need the most up-to-date listings.
            **kwargs: Additional MercadoLibre-specific parameters:
                     - state: MercadoLibre state ID for precise location filtering
                     - city: MercadoLibre city ID for precise location filtering
                     - price_min: Minimum price filter
                     - price_max: Maximum price filter
            
        Returns:
            DataFrame with normalized property data containing columns:
            - id: Unique MercadoLibre property ID
            - title: Property title/description
            - price_usd: Price in USD (if available)
            - price_ars: Price in ARS (if available)
            - address: Property address
            - latitude/longitude: GPS coordinates
            - property_type: Normalized property type
            - operation_type: Normalized operation type
            - rooms: Number of bedrooms
            - bathrooms: Number of bathrooms
            - surface_m2: Surface area in square meters
            - listing_url: URL to the MercadoLibre listing
            - source: Always "mercadolibre"
            
        Raises:
            ProviderAPIError: If API requests fail or return errors
            ProviderRateLimitError: If rate limits are exceeded
            ProviderError: If filter validation fails
            
        Example:
            >>> # Basic search
            >>> properties = provider.fetch_properties(
            ...     location="palermo",
            ...     property_type="apartment",
            ...     operation_type="rent"
            ... )
            >>> 
            >>> # Advanced search with price filters
            >>> properties = provider.fetch_properties(
            ...     location="recoleta",
            ...     property_type="house",
            ...     operation_type="sale",
            ...     max_results=50,
            ...     price_min=100000,
            ...     price_max=500000
            ... )
            >>> 
            >>> # Force fresh data (bypass cache)
            >>> properties = provider.fetch_properties(
            ...     location="belgrano",
            ...     force_refresh=True
            ... )
        """
        # Validate filters
        filters = self.validate_filters(
            location=location,
            property_type=property_type,
            operation_type=operation_type,
            max_results=max_results,
            force_refresh=force_refresh,
            **kwargs
        )
        
        # Check cache first (unless force refresh)
        if not force_refresh:
            cache_key = self._get_cache_key(**filters)
            cached_data = self._get_cached_data(cache_key)
            if cached_data is not None:
                return cached_data
        
        # Fetch fresh data from API
        self.logger.info(
            "Fetching properties from MercadoLibre API",
            provider=self.get_provider_name(),
            location=location,
            property_type=property_type,
            operation_type=operation_type,
            max_results=max_results
        )
        
        try:
            raw_properties = self._search_properties(**filters)
            
            if not raw_properties:
                self.logger.warning(
                    "No properties found",
                    provider=self.get_provider_name(),
                    filters=filters
                )
                return self._empty_dataframe()
            
            # Normalize data to unified schema
            df = self._normalize_to_schema(raw_properties)
            
            # Cache the results
            if not force_refresh:
                self._save_to_cache(cache_key, df)
            
            self.logger.info(
                "Successfully fetched properties",
                provider=self.get_provider_name(),
                total_properties=len(df),
                filters=filters
            )
            
            return df
            
        except Exception as e:
            self.logger.error(
                "Failed to fetch properties",
                provider=self.get_provider_name(),
                error=str(e),
                filters=filters
            )
            raise
    
    def _search_properties(self, **filters) -> List[Dict[str, Any]]:
        """Search for properties using MercadoLibre API.
        
        Args:
            **filters: Search filters
            
        Returns:
            List of property dictionaries from API
        """
        all_properties = []
        offset = 0
        max_results = filters.get("max_results", 200)  # Default reasonable limit
        
        while len(all_properties) < max_results:
            # Build search URL with parameters
            search_url = self._build_search_url(offset=offset, **filters)
            
            # Make API request with retry logic
            response_data = self._retry_with_backoff(self._make_api_request, search_url)
            
            # Extract properties from response
            properties = response_data.get("results", [])
            if not properties:
                self.logger.debug(
                    "No more properties in response",
                    provider=self.get_provider_name(),
                    offset=offset
                )
                break
            
            all_properties.extend(properties)
            
            # Check pagination
            paging = response_data.get("paging", {})
            total_results = paging.get("total", 0)
            current_limit = paging.get("limit", self.max_results_per_request)
            
            self.logger.debug(
                "Fetched page of results",
                provider=self.get_provider_name(),
                page_results=len(properties),
                total_fetched=len(all_properties),
                total_available=total_results,
                offset=offset
            )
            
            # Check if we have all results or reached the limit
            if len(properties) < current_limit or len(all_properties) >= max_results:
                break
            
            offset += current_limit
        
        # Trim to max_results if we fetched more
        if len(all_properties) > max_results:
            all_properties = all_properties[:max_results]
        
        return all_properties
    
    def _build_search_url(self, offset: int = 0, **filters) -> str:
        """Build MercadoLibre search URL with parameters.
        
        Args:
            offset: Pagination offset
            **filters: Search filters
            
        Returns:
            Complete search URL with parameters
        """
        params = {
            "limit": self.max_results_per_request,
            "offset": offset,
        }
        
        # Add category filter for property type
        if "property_type" in filters:
            category_id = self.CATEGORY_MAPPING[filters["property_type"]]
            params["category"] = category_id
        else:
            # Default to real estate root category
            params["category"] = "MLA1459"  # Inmuebles
        
        # Add location filter if provided
        if "location" in filters and filters["location"]:
            location_id = self._resolve_location_id(filters["location"])
            if location_id:
                # Use specific location ID for more accurate results
                if location_id.startswith("neighborhood_"):
                    params["neighborhood"] = location_id.replace("neighborhood_", "")
                elif location_id.startswith("city_"):
                    params["city"] = location_id.replace("city_", "")
                elif location_id.startswith("state_"):
                    params["state"] = location_id.replace("state_", "")
                else:
                    # Fallback to search query if ID format is unknown
                    params["q"] = filters["location"]
            else:
                # Fallback to search query if location ID not found
                params["q"] = filters["location"]
        
        # Add operation type as search query modifier
        if "operation_type" in filters:
            operation = self.OPERATION_MAPPING[filters["operation_type"]]
            if "q" in params:
                params["q"] = f"{params['q']} {operation}"
            else:
                params["q"] = operation
        
        # Build final URL
        query_string = urlencode(params)
        url = f"{self.BASE_URL}{self.SEARCH_ENDPOINT}?{query_string}"
        
        self.logger.debug(
            "Built search URL",
            provider=self.get_provider_name(),
            url=url,
            params=params
        )
        
        return url
    
    def _make_api_request(self, url: str) -> Dict[str, Any]:
        """Make HTTP request to MercadoLibre API.
        
        Args:
            url: API endpoint URL
            
        Returns:
            Parsed JSON response
            
        Raises:
            ProviderAPIError: If request fails
            ProviderRateLimitError: If rate limited
        """
        # Apply rate limiting
        self._rate_limit()
        
        self.logger.debug(
            "Making API request",
            provider=self.get_provider_name(),
            url=url
        )
        
        try:
            response = self.session.get(url)
            
            # Handle rate limiting
            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                if retry_after:
                    wait_time = int(retry_after)
                    self.logger.warning(
                        "Rate limited by API",
                        provider=self.get_provider_name(),
                        retry_after_seconds=wait_time
                    )
                    time.sleep(wait_time)
                    raise ProviderRateLimitError(
                        f"Rate limited. Retry after {wait_time} seconds."
                    )
                else:
                    raise ProviderRateLimitError("Rate limited by API")
            
            # Handle other HTTP errors
            if not response.ok:
                error_msg = f"API request failed with status {response.status_code}"
                try:
                    error_data = response.json()
                    if "message" in error_data:
                        error_msg += f": {error_data['message']}"
                except:
                    pass
                
                self.logger.error(
                    "API request failed",
                    provider=self.get_provider_name(),
                    status_code=response.status_code,
                    url=url,
                    error=error_msg
                )
                raise ProviderAPIError(error_msg)
            
            # Parse JSON response
            try:
                data = response.json()
                self.logger.debug(
                    "API request successful",
                    provider=self.get_provider_name(),
                    results_count=len(data.get("results", [])),
                    total_results=data.get("paging", {}).get("total", 0)
                )
                return data
                
            except ValueError as e:
                raise ProviderAPIError(f"Invalid JSON response: {e}")
                
        except requests.exceptions.Timeout:
            raise ProviderAPIError(f"Request timeout after {self.timeout_seconds} seconds")
        except requests.exceptions.ConnectionError as e:
            raise ProviderAPIError(f"Connection error: {e}")
        except requests.exceptions.RequestException as e:
            raise ProviderAPIError(f"Request failed: {e}")
    
    def _normalize_to_schema(self, raw_data: List[Dict[str, Any]]) -> pd.DataFrame:
        """Convert MercadoLibre data to unified schema.
        
        Args:
            raw_data: List of property dictionaries from MercadoLibre API
            
        Returns:
            DataFrame with unified schema
        """
        if not raw_data:
            return self._empty_dataframe()
        
        normalized_properties = []
        
        for item in raw_data:
            try:
                property_data = self._extract_property_data(item)
                if property_data:
                    normalized_properties.append(property_data)
            except Exception as e:
                self.logger.warning(
                    "Failed to extract property data",
                    provider=self.get_provider_name(),
                    property_id=item.get("id", "unknown"),
                    error=str(e)
                )
                continue
        
        if not normalized_properties:
            return self._empty_dataframe()
        
        # Create DataFrame and ensure proper schema
        df = pd.DataFrame(normalized_properties)
        return super()._normalize_to_schema(normalized_properties)
    
    def _extract_property_data(self, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Extract property data from MercadoLibre item.
        
        Args:
            item: Property item from MercadoLibre API response
            
        Returns:
            Dictionary with normalized property data or None if extraction fails
        """
        try:
            # Extract basic information
            property_id = item.get("id")
            if not property_id:
                return None
            
            title = item.get("title", "")
            price = item.get("price")
            currency = item.get("currency_id", "")
            
            # Extract location information
            location_data = item.get("location", {})
            latitude = location_data.get("latitude")
            longitude = location_data.get("longitude")
            
            address_info = item.get("address", {})
            city_name = address_info.get("city_name", "")
            state_name = address_info.get("state_name", "")
            
            # Build address string
            address_parts = [part for part in [city_name, state_name] if part]
            address = ", ".join(address_parts) if address_parts else ""
            
            # Extract attributes
            attributes = {}
            for attr in item.get("attributes", []):
                attr_id = attr.get("id")
                attr_value = attr.get("value_name") or attr.get("value_struct", {}).get("number")
                if attr_id and attr_value is not None:
                    attributes[attr_id] = attr_value
            
            # Parse property attributes
            rooms = self._parse_numeric(attributes.get("BEDROOMS"))
            bathrooms = self._parse_numeric(attributes.get("BATHROOMS"))
            surface = self._parse_surface(attributes.get("TOTAL_AREA"))
            
            # Determine property and operation types
            property_type = self._extract_property_type(item)
            operation_type = self._extract_operation_type(item, title)
            
            # Convert prices to USD and ARS
            price_usd, price_ars = self._convert_prices(price, currency)
            
            return {
                "id": str(property_id),
                "title": title,
                "price_usd": price_usd,
                "price_ars": price_ars,
                "address": address,
                "latitude": latitude,
                "longitude": longitude,
                "property_type": property_type,
                "operation_type": operation_type,
                "rooms": rooms,
                "bathrooms": bathrooms,
                "surface_m2": surface,
                "listing_url": item.get("permalink", ""),
                "source": self.get_provider_name()
            }
            
        except Exception as e:
            self.logger.warning(
                "Error extracting property data",
                provider=self.get_provider_name(),
                property_id=item.get("id", "unknown"),
                error=str(e)
            )
            return None
    
    def _extract_property_type(self, item: Dict[str, Any]) -> Optional[str]:
        """Extract and normalize property type from MercadoLibre item.
        
        Args:
            item: Property item from API
            
        Returns:
            Normalized property type or None
        """
        # Try to get category from item
        category_id = item.get("category_id", "")
        
        # Map MercadoLibre category to our standard types
        reverse_mapping = {v: k for k, v in self.CATEGORY_MAPPING.items()}
        
        if category_id in reverse_mapping:
            return reverse_mapping[category_id]
        
        # Fallback: try to infer from title
        title = item.get("title", "").lower()
        
        if any(word in title for word in ["departamento", "depto", "apartment"]):
            return "apartment"
        elif any(word in title for word in ["casa", "house"]):
            return "house"
        elif any(word in title for word in ["terreno", "lote", "land"]):
            return "land"
        elif any(word in title for word in ["local", "comercial", "commercial"]):
            return "commercial"
        elif any(word in title for word in ["oficina", "office"]):
            return "office"
        
        return None
    
    def _extract_operation_type(self, item: Dict[str, Any], title: str) -> Optional[str]:
        """Extract and normalize operation type from MercadoLibre item.
        
        Args:
            item: Property item from API
            title: Property title
            
        Returns:
            Normalized operation type or None
        """
        title_lower = title.lower()
        
        # Check for operation type keywords in title
        if any(word in title_lower for word in ["alquiler temporal", "temp", "temporario"]):
            return "temporary_rent"
        elif any(word in title_lower for word in ["alquiler", "rent", "rental"]):
            return "rent"
        elif any(word in title_lower for word in ["venta", "sale", "sell"]):
            return "sale"
        
        # Default to sale if not specified
        return "sale"
    
    def _convert_prices(self, price: Any, currency: str) -> Tuple[Optional[float], Optional[float]]:
        """Convert price to both USD and ARS.
        
        Args:
            price: Price value from API
            currency: Currency code (USD, ARS, etc.)
            
        Returns:
            Tuple of (price_usd, price_ars)
        """
        if price is None:
            return None, None
        
        try:
            price_float = float(price)
        except (ValueError, TypeError):
            return None, None
        
        if currency == "USD":
            return price_float, None  # ARS conversion would need exchange rate
        elif currency == "ARS":
            return None, price_float  # USD conversion would need exchange rate
        else:
            # Unknown currency, log warning and return as-is
            self.logger.warning(
                "Unknown currency in price conversion",
                provider=self.get_provider_name(),
                currency=currency,
                price=price
            )
            return None, price_float  # Assume ARS as default for Argentina
    
    def _resolve_location_id(self, location_name: str) -> Optional[str]:
        """Resolve location name to MercadoLibre location ID.
        
        Args:
            location_name: Human-readable location name (e.g., "Palermo", "Capital Federal")
            
        Returns:
            Location ID string with prefix (e.g., "neighborhood_TUxBQlBBTDI1MTVa") or None if not found
        """
        if not location_name or not location_name.strip():
            return None
        
        location_name = location_name.strip().lower()
        
        # Check cache first
        cached_id = self._get_cached_location_id(location_name)
        if cached_id:
            return cached_id
        
        # Search for location using MercadoLibre API
        try:
            location_id = self._search_location_api(location_name)
            if location_id:
                # Cache the result for future use
                self._cache_location_id(location_name, location_id)
                return location_id
        except Exception as e:
            self.logger.warning(
                "Failed to resolve location ID",
                provider=self.get_provider_name(),
                location_name=location_name,
                error=str(e)
            )
        
        return None
    
    def _get_cached_location_id(self, location_name: str) -> Optional[str]:
        """Get cached location ID for a location name.
        
        Args:
            location_name: Normalized location name
            
        Returns:
            Cached location ID or None if not found/expired
        """
        cache_file = self.cache_dir / "location_mappings.json"
        
        if not cache_file.exists():
            return None
        
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            
            # Check if location exists in cache and is fresh
            if location_name in cache_data:
                entry = cache_data[location_name]
                cached_time = datetime.fromisoformat(entry['timestamp'])
                
                # Use same TTL as other cached data
                if datetime.now() - cached_time < timedelta(hours=self.cache_ttl_hours):
                    self.logger.debug(
                        "Found cached location ID",
                        provider=self.get_provider_name(),
                        location_name=location_name,
                        location_id=entry['location_id']
                    )
                    return entry['location_id']
                else:
                    self.logger.debug(
                        "Cached location ID expired",
                        provider=self.get_provider_name(),
                        location_name=location_name
                    )
        
        except Exception as e:
            self.logger.warning(
                "Failed to read location cache",
                provider=self.get_provider_name(),
                error=str(e)
            )
        
        return None
    
    def _cache_location_id(self, location_name: str, location_id: str) -> None:
        """Cache location ID mapping.
        
        Args:
            location_name: Normalized location name
            location_id: MercadoLibre location ID with prefix
        """
        cache_file = self.cache_dir / "location_mappings.json"
        
        try:
            # Load existing cache or create new
            cache_data = {}
            if cache_file.exists():
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
            
            # Add new mapping
            cache_data[location_name] = {
                'location_id': location_id,
                'timestamp': datetime.now().isoformat()
            }
            
            # Save updated cache
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
            
            self.logger.debug(
                "Cached location ID mapping",
                provider=self.get_provider_name(),
                location_name=location_name,
                location_id=location_id
            )
        
        except Exception as e:
            self.logger.warning(
                "Failed to cache location ID",
                provider=self.get_provider_name(),
                location_name=location_name,
                location_id=location_id,
                error=str(e)
            )
    
    def _search_location_api(self, location_name: str) -> Optional[str]:
        """Search for location using MercadoLibre locations API.
        
        Args:
            location_name: Location name to search for
            
        Returns:
            Location ID with prefix or None if not found
        """
        # Try different search strategies
        search_strategies = [
            self._search_neighborhoods,
            self._search_cities,
            self._search_states
        ]
        
        for search_func in search_strategies:
            try:
                location_id = search_func(location_name)
                if location_id:
                    return location_id
            except Exception as e:
                self.logger.debug(
                    "Location search strategy failed",
                    provider=self.get_provider_name(),
                    strategy=search_func.__name__,
                    location_name=location_name,
                    error=str(e)
                )
                continue
        
        return None
    
    def _search_neighborhoods(self, location_name: str) -> Optional[str]:
        """Search for neighborhood by name in Capital Federal.
        
        Searches through neighborhoods in Capital Federal (Buenos Aires) to find
        a match for the given location name. Uses partial matching to handle
        variations in neighborhood names.
        
        Args:
            location_name: Neighborhood name to search for (e.g., "palermo", "recoleta")
            
        Returns:
            Neighborhood ID with "neighborhood_" prefix or None if not found
            
        Example:
            >>> provider._search_neighborhoods("palermo")
            "neighborhood_TUxBQlBBTDI1MTVa"
        """
        # Search in Capital Federal neighborhoods (most common case)
        # First get the city info which contains neighborhoods
        city_id = "TUxBQ0NBUGZlZG1sYQ"  # Capital Federal city ID
        url = f"{self.BASE_URL}{self.LOCATIONS_ENDPOINT}/cities/{city_id}"
        
        try:
            response_data = self._retry_with_backoff(self._make_api_request, url)
            neighborhoods = response_data.get("neighborhoods", [])
            
            # Look for exact or partial matches
            for neighborhood in neighborhoods:
                name = neighborhood.get("name", "").lower()
                if location_name in name or name in location_name:
                    neighborhood_id = neighborhood.get("id")
                    if neighborhood_id:
                        self.logger.info(
                            "Found neighborhood match",
                            provider=self.get_provider_name(),
                            search_term=location_name,
                            matched_name=neighborhood.get("name"),
                            neighborhood_id=neighborhood_id
                        )
                        return f"neighborhood_{neighborhood_id}"
        
        except Exception as e:
            self.logger.debug(
                "Neighborhood search failed",
                provider=self.get_provider_name(),
                location_name=location_name,
                error=str(e)
            )
        
        return None
    
    def _search_cities(self, location_name: str) -> Optional[str]:
        """Search for city by name across all Argentine states.
        
        Iterates through all states in Argentina and searches their cities
        for a match with the given location name. Uses partial matching
        to handle variations in city names.
        
        Args:
            location_name: City name to search for (e.g., "capital federal", "cordoba")
            
        Returns:
            City ID with "city_" prefix or None if not found
            
        Example:
            >>> provider._search_cities("capital federal")
            "city_TUxBQ0NBUGZlZG1sYQ"
        """
        # Search in Argentina states to find cities
        # First get all states, then search their cities
        url = f"{self.BASE_URL}{self.LOCATIONS_ENDPOINT}/countries/AR"
        
        try:
            response_data = self._retry_with_backoff(self._make_api_request, url)
            states = response_data.get("states", [])
            
            # Search through states to find cities
            for state in states:
                state_id = state.get("id")
                if not state_id:
                    continue
                
                try:
                    # Get state details which include cities
                    state_url = f"{self.BASE_URL}{self.LOCATIONS_ENDPOINT}/states/{state_id}"
                    state_data = self._retry_with_backoff(self._make_api_request, state_url)
                    cities = state_data.get("cities", [])
                    
                    # Look for matching city
                    for city in cities:
                        name = city.get("name", "").lower()
                        if location_name in name or name in location_name:
                            city_id = city.get("id")
                            if city_id:
                                self.logger.info(
                                    "Found city match",
                                    provider=self.get_provider_name(),
                                    search_term=location_name,
                                    matched_name=city.get("name"),
                                    city_id=city_id,
                                    state_name=state.get("name")
                                )
                                return f"city_{city_id}"
                
                except Exception as state_e:
                    self.logger.debug(
                        "Failed to search state for cities",
                        provider=self.get_provider_name(),
                        state_id=state_id,
                        error=str(state_e)
                    )
                    continue
        
        except Exception as e:
            self.logger.debug(
                "City search failed",
                provider=self.get_provider_name(),
                location_name=location_name,
                error=str(e)
            )
        
        return None
    
    def _search_states(self, location_name: str) -> Optional[str]:
        """Search for state by name in Argentina.
        
        Searches through all Argentine states to find a match for the given
        location name. Uses partial matching to handle variations in state names.
        
        Args:
            location_name: State name to search for (e.g., "capital federal", "buenos aires")
            
        Returns:
            State ID with "state_" prefix or None if not found
            
        Example:
            >>> provider._search_states("capital federal")
            "state_TUxBUENBUGw3M2E1"
        """
        # Search in Argentina states
        url = f"{self.BASE_URL}{self.LOCATIONS_ENDPOINT}/countries/AR"
        
        try:
            response_data = self._retry_with_backoff(self._make_api_request, url)
            states = response_data.get("states", [])
            
            # Look for exact or partial matches
            for state in states:
                name = state.get("name", "").lower()
                if location_name in name or name in location_name:
                    state_id = state.get("id")
                    if state_id:
                        self.logger.info(
                            "Found state match",
                            provider=self.get_provider_name(),
                            search_term=location_name,
                            matched_name=state.get("name"),
                            state_id=state_id
                        )
                        return f"state_{state_id}"
        
        except Exception as e:
            self.logger.debug(
                "State search failed",
                provider=self.get_provider_name(),
                location_name=location_name,
                error=str(e)
            )
        
        return None