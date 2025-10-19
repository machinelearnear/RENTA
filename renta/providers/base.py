"""Base classes and interfaces for real estate data providers."""

import os
import time
import json
from abc import ABC, abstractmethod
from typing import Dict, Optional, List, Any
from pathlib import Path
import pandas as pd
import structlog
from datetime import datetime, timedelta

from ..config import ConfigManager
from ..exceptions import (
    RentaError, 
    ProviderError, 
    ProviderNotFoundError, 
    ProviderAPIError, 
    ProviderRateLimitError
)


class RealEstateProvider(ABC):
    """Abstract interface for real estate data providers.
    
    This interface defines the contract that all real estate data providers
    must implement to be compatible with the RENTA system.
    """
    
    @abstractmethod
    def fetch_properties(
        self,
        location: Optional[str] = None,
        property_type: Optional[str] = None,
        operation_type: Optional[str] = None,
        max_results: Optional[int] = None,
        **kwargs
    ) -> pd.DataFrame:
        """Fetch property listings from the provider.
        
        Args:
            location: Location filter (neighborhood, city, etc.)
            property_type: Type of property (apartment, house, etc.)
            operation_type: Operation type (sale, rent, etc.)
            max_results: Maximum number of results to return
            **kwargs: Provider-specific parameters
            
        Returns:
            DataFrame with normalized property data following the unified schema:
            - id (str): Unique property identifier
            - title (str): Property title/description
            - price_usd (float): Price in USD
            - price_ars (float): Price in ARS
            - address (str): Property address
            - latitude (float): Latitude coordinate
            - longitude (float): Longitude coordinate
            - property_type (str): apartment, house, land, commercial, office
            - operation_type (str): sale, rent, temporary_rent
            - rooms (float): Number of rooms/bedrooms
            - bathrooms (float): Number of bathrooms
            - surface_m2 (float): Surface area in square meters
            - listing_url (str): URL to the listing
            - source (str): Provider name
        """
        pass
    
    @abstractmethod
    def get_provider_name(self) -> str:
        """Return the unique name of this provider.
        
        Returns:
            String identifier for this provider (e.g., 'zonaprop', 'mercadolibre')
        """
        pass
    
    @abstractmethod
    def validate_filters(self, **filters) -> Dict[str, Any]:
        """Validate and normalize filter parameters.
        
        Args:
            **filters: Filter parameters to validate
            
        Returns:
            Dictionary of validated and normalized filters
            
        Raises:
            ProviderError: If filters are invalid
        """
        pass


class BaseRealEstateProvider(RealEstateProvider):
    """Base class with common provider functionality.
    
    Provides shared functionality that all providers can inherit:
    - Caching mechanism with configurable TTL
    - Rate limiting with exponential backoff
    - Retry logic for transient failures
    - Data normalization helpers
    - Logging and error handling
    """
    
    def __init__(self, config: ConfigManager):
        """Initialize the base provider.
        
        Args:
            config: Configuration manager instance
        """
        self.config = config
        self.cache_dir = self._setup_cache_dir()
        self.logger = structlog.get_logger()
        
        # Load provider-specific configuration
        provider_name = self.get_provider_name()
        self.provider_config = config.get(
            f"real_estate.providers.{provider_name}", 
            {}
        )
        
        # Common configuration with defaults
        self.rate_limit_seconds = self.provider_config.get("rate_limit_seconds", 1.0)
        self.max_retries = self.provider_config.get("max_retries", 3)
        self.timeout_seconds = self.provider_config.get("timeout_seconds", 30)
        self.cache_ttl_hours = self.provider_config.get("cache_ttl_hours", 24)
        
        self._last_request_time = 0
    
    def _setup_cache_dir(self) -> Path:
        """Set up cache directory for this provider.
        
        Returns:
            Path to the provider's cache directory
        """
        cache_base = Path(self.config.get("data.cache_dir", "~/.renta/cache")).expanduser()
        provider_cache = cache_base / "providers" / self.get_provider_name()
        provider_cache.mkdir(parents=True, exist_ok=True)
        return provider_cache
    
    def _get_cache_key(self, **filters) -> str:
        """Generate cache key from filter parameters.
        
        Args:
            **filters: Filter parameters
            
        Returns:
            String cache key
        """
        # Sort filters for consistent cache keys
        sorted_filters = sorted(filters.items())
        filter_str = "_".join(f"{k}={v}" for k, v in sorted_filters if v is not None)
        return filter_str or "default"
    
    def _get_cached_data(self, cache_key: str) -> Optional[pd.DataFrame]:
        """Load data from cache if fresh.
        
        Args:
            cache_key: Cache key to look up
            
        Returns:
            Cached DataFrame if fresh, None otherwise
        """
        cache_file = self.cache_dir / f"{cache_key}.csv"
        
        if not cache_file.exists():
            return None
        
        if not self._is_cache_fresh(cache_file):
            self.logger.debug(
                "Cache file exists but is stale",
                cache_file=str(cache_file),
                provider=self.get_provider_name()
            )
            return None
        
        try:
            df = pd.read_csv(cache_file)
            self.logger.info(
                "Loaded data from cache",
                cache_file=str(cache_file),
                records=len(df),
                provider=self.get_provider_name()
            )
            return df
        except Exception as e:
            self.logger.warning(
                "Failed to load cached data",
                cache_file=str(cache_file),
                error=str(e),
                provider=self.get_provider_name()
            )
            return None
    
    def _save_to_cache(self, cache_key: str, data: pd.DataFrame) -> None:
        """Save data to cache with timestamp.
        
        Args:
            cache_key: Cache key to save under
            data: DataFrame to cache
        """
        cache_file = self.cache_dir / f"{cache_key}.csv"
        
        try:
            data.to_csv(cache_file, index=False)
            self.logger.info(
                "Saved data to cache",
                cache_file=str(cache_file),
                records=len(data),
                provider=self.get_provider_name()
            )
        except Exception as e:
            self.logger.warning(
                "Failed to save data to cache",
                cache_file=str(cache_file),
                error=str(e),
                provider=self.get_provider_name()
            )
    
    def _is_cache_fresh(self, cache_file: Path) -> bool:
        """Check if cached data is within freshness threshold.
        
        Args:
            cache_file: Path to cache file
            
        Returns:
            True if cache is fresh, False otherwise
        """
        try:
            file_time = datetime.fromtimestamp(cache_file.stat().st_mtime)
            threshold = datetime.now() - timedelta(hours=self.cache_ttl_hours)
            return file_time > threshold
        except Exception:
            return False
    
    def _rate_limit(self) -> None:
        """Sleep to respect rate limits."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.rate_limit_seconds:
            sleep_time = self.rate_limit_seconds - elapsed
            self.logger.debug(
                "Rate limiting",
                sleep_seconds=sleep_time,
                provider=self.get_provider_name()
            )
            time.sleep(sleep_time)
        
        self._last_request_time = time.time()
    
    def _retry_with_backoff(self, func, *args, **kwargs):
        """Execute function with exponential backoff retry.
        
        Args:
            func: Function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments
            
        Returns:
            Function result
            
        Raises:
            ProviderAPIError: If all retries fail
        """
        last_exception = None
        
        for attempt in range(self.max_retries):
            try:
                return func(*args, **kwargs)
            except ProviderRateLimitError as e:
                # Don't retry rate limit errors immediately
                self.logger.warning(
                    "Rate limit exceeded",
                    attempt=attempt + 1,
                    provider=self.get_provider_name(),
                    error=str(e)
                )
                raise
            except Exception as e:
                last_exception = e
                if attempt < self.max_retries - 1:
                    backoff_time = 2 ** attempt
                    self.logger.warning(
                        "Request failed, retrying",
                        attempt=attempt + 1,
                        max_retries=self.max_retries,
                        backoff_seconds=backoff_time,
                        provider=self.get_provider_name(),
                        error=str(e)
                    )
                    time.sleep(backoff_time)
                else:
                    self.logger.error(
                        "All retry attempts failed",
                        attempts=self.max_retries,
                        provider=self.get_provider_name(),
                        error=str(e)
                    )
        
        raise ProviderAPIError(
            f"Request failed after {self.max_retries} attempts: {last_exception}"
        )
    
    def _normalize_to_schema(self, raw_data: List[Dict[str, Any]]) -> pd.DataFrame:
        """Convert provider-specific data to unified schema.
        
        Args:
            raw_data: List of property dictionaries from provider
            
        Returns:
            DataFrame with unified schema
        """
        if not raw_data:
            return self._empty_dataframe()
        
        df = pd.DataFrame(raw_data)
        
        # Ensure all required columns exist
        required_columns = [
            'id', 'title', 'price_usd', 'price_ars', 'address',
            'latitude', 'longitude', 'property_type', 'operation_type',
            'rooms', 'bathrooms', 'surface_m2', 'listing_url', 'source'
        ]
        
        for col in required_columns:
            if col not in df.columns:
                df[col] = None
        
        # Ensure correct data types
        numeric_columns = ['price_usd', 'price_ars', 'latitude', 'longitude', 
                          'rooms', 'bathrooms', 'surface_m2']
        for col in numeric_columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # Ensure string columns
        string_columns = ['id', 'title', 'address', 'property_type', 
                         'operation_type', 'listing_url', 'source']
        for col in string_columns:
            df[col] = df[col].astype(str)
        
        return df[required_columns]
    
    def _empty_dataframe(self) -> pd.DataFrame:
        """Return empty DataFrame with unified schema.
        
        Returns:
            Empty DataFrame with all required columns
        """
        columns = [
            'id', 'title', 'price_usd', 'price_ars', 'address',
            'latitude', 'longitude', 'property_type', 'operation_type',
            'rooms', 'bathrooms', 'surface_m2', 'listing_url', 'source'
        ]
        return pd.DataFrame(columns=columns)
    
    def _parse_numeric(self, value: Any) -> Optional[float]:
        """Parse numeric value safely.
        
        Args:
            value: Value to parse
            
        Returns:
            Float value or None if parsing fails
        """
        if value is None:
            return None
        
        try:
            # Handle string values with units (e.g., "2 rooms", "45 m²")
            if isinstance(value, str):
                # Extract first number from string
                import re
                match = re.search(r'(\d+(?:\.\d+)?)', value)
                if match:
                    return float(match.group(1))
                return None
            
            return float(value)
        except (ValueError, TypeError):
            return None
    
    def _parse_surface(self, value: Any) -> Optional[float]:
        """Parse surface area value safely.
        
        Args:
            value: Surface value to parse (may include units like "m²")
            
        Returns:
            Float value in square meters or None if parsing fails
        """
        if value is None:
            return None
        
        try:
            if isinstance(value, str):
                # Remove common surface units and extract number
                import re
                # Match patterns like "45 m²", "45m2", "45 sq m", etc.
                match = re.search(r'(\d+(?:\.\d+)?)', value.replace(',', '.'))
                if match:
                    return float(match.group(1))
                return None
            
            return float(value)
        except (ValueError, TypeError):
            return None