# Real Estate Providers API

The RENTA provider system enables fetching real estate data from multiple sources through a unified interface. This document describes the provider architecture, available implementations, and how to extend the system.

## Core Interfaces

### RealEstateProvider

The abstract base class that defines the contract for all real estate providers.

```python
from abc import ABC, abstractmethod
from typing import Dict, Optional
import pandas as pd

class RealEstateProvider(ABC):
    """Abstract interface for real estate data providers."""
    
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
            DataFrame with normalized property data following the unified schema
            
        Raises:
            ProviderError: When provider encounters an error
            ProviderAPIError: When API calls fail
            ProviderRateLimitError: When rate limits are exceeded
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
    def validate_filters(self, **filters) -> Dict:
        """Validate and normalize filter parameters.
        
        Args:
            **filters: Filter parameters to validate
            
        Returns:
            Dictionary of validated and normalized filters
            
        Raises:
            ValueError: When filters are invalid or unsupported
        """
        pass
```

### BaseRealEstateProvider

Base implementation providing common functionality for all providers.

```python
class BaseRealEstateProvider(RealEstateProvider):
    """Base class with common provider functionality.
    
    Provides shared implementations for:
    - Caching mechanism with configurable TTL
    - Rate limiting with exponential backoff
    - Retry logic for transient failures
    - Data normalization helpers
    - Structured logging and error handling
    """
    
    def __init__(self, config: ConfigManager):
        """Initialize base provider.
        
        Args:
            config: Configuration manager instance
        """
        self.config = config
        self.cache_dir = self._setup_cache_dir()
        self.logger = structlog.get_logger()
        
    def _get_cached_data(self, cache_key: str) -> Optional[pd.DataFrame]:
        """Load data from cache if fresh.
        
        Args:
            cache_key: Unique identifier for cached data
            
        Returns:
            Cached DataFrame if available and fresh, None otherwise
        """
        
    def _save_to_cache(self, cache_key: str, data: pd.DataFrame):
        """Save data to cache with timestamp.
        
        Args:
            cache_key: Unique identifier for cached data
            data: DataFrame to cache
        """
        
    def _is_cache_fresh(self, cache_key: str) -> bool:
        """Check if cached data is within freshness threshold.
        
        Args:
            cache_key: Cache identifier to check
            
        Returns:
            True if cache is fresh, False otherwise
        """
        
    def _rate_limit(self, delay_seconds: float):
        """Sleep to respect rate limits.
        
        Args:
            delay_seconds: Number of seconds to wait
        """
        
    def _retry_with_backoff(self, func, max_retries: int = 3):
        """Execute function with exponential backoff retry.
        
        Args:
            func: Function to execute
            max_retries: Maximum number of retry attempts
            
        Returns:
            Function result
            
        Raises:
            Exception: Last exception if all retries fail
        """
        
    def _normalize_to_schema(self, raw_data: List[Dict]) -> pd.DataFrame:
        """Convert provider-specific data to unified schema.
        
        Args:
            raw_data: List of property dictionaries from provider
            
        Returns:
            DataFrame with standardized columns and data types
        """
```

## Provider Implementations

### MercadoLibreProvider

Provider for fetching data from MercadoLibre's official API.

```python
class MercadoLibreProvider(BaseRealEstateProvider):
    """Provider for MercadoLibre real estate data.
    
    Fetches property listings from MercadoLibre's public API with support for:
    - Category-based filtering (apartments, houses, land, etc.)
    - Location-based search (state, city, neighborhood)
    - Operation type filtering (sale, rent, temporary rent)
    - Automatic pagination handling
    - Rate limiting and retry logic
    - Response caching
    """
    
    def __init__(self, config: ConfigManager):
        """Initialize MercadoLibre provider.
        
        Args:
            config: Configuration manager with MercadoLibre settings
        """
        
    def fetch_properties(
        self,
        location: Optional[str] = None,
        property_type: Optional[str] = None,
        operation_type: Optional[str] = None,
        max_results: Optional[int] = None,
        state: Optional[str] = None,
        city: Optional[str] = None,
        price_min: Optional[float] = None,
        price_max: Optional[float] = None,
        **kwargs
    ) -> pd.DataFrame:
        """Fetch properties from MercadoLibre API.
        
        Args:
            location: Location name to search (resolved to MercadoLibre location ID)
            property_type: Property type ('apartment', 'house', 'land', 'commercial', 'office')
            operation_type: Operation type ('sale', 'rent', 'temporary_rent')
            max_results: Maximum number of properties to fetch
            state: MercadoLibre state ID (e.g., 'TUxBUENBUGw3M2E1' for Capital Federal)
            city: MercadoLibre city ID
            price_min: Minimum price filter
            price_max: Maximum price filter
            **kwargs: Additional MercadoLibre API parameters
            
        Returns:
            DataFrame with property listings in unified schema
            
        Raises:
            ProviderAPIError: When API requests fail
            ProviderRateLimitError: When rate limits are exceeded
        """
        
    def get_provider_name(self) -> str:
        """Return provider name."""
        return "mercadolibre"
        
    def validate_filters(self, **filters) -> Dict:
        """Validate MercadoLibre-specific filters.
        
        Validates:
        - Property types against supported categories
        - Operation types against MercadoLibre operations
        - Location parameters
        - Price ranges
        
        Args:
            **filters: Filter parameters to validate
            
        Returns:
            Dictionary of validated filters
            
        Raises:
            ValueError: When filters are invalid
        """
```

#### MercadoLibre API Details

**Base URL**: `https://api.mercadolibre.com`

**Key Endpoints**:
- Search: `GET /sites/MLA/search`
- Item Details: `GET /items/{item_id}`
- Categories: `GET /categories/{category_id}`
- Locations: `GET /classified_locations/countries/AR`

**Category Mapping**:
| Property Type | Category ID | Description |
|---------------|-------------|-------------|
| apartment | MLA1472 | Departamentos |
| house | MLA1466 | Casas |
| land | MLA1493 | Terrenos y Lotes |
| commercial | MLA79242 | Locales |
| office | MLA50538 | Oficinas |

**Rate Limits**: 
- Default: 1 request per second
- Configurable via `real_estate.providers.mercadolibre.rate_limit_seconds`

### ZonapropProvider

Provider wrapping the existing Zonaprop scraper functionality.

```python
class ZonapropProvider(BaseRealEstateProvider):
    """Provider for Zonaprop real estate data.
    
    Wraps the existing ZonapropScraper with the provider interface:
    - Playwright-based web scraping
    - Cloudflare bypass capabilities
    - URL-based and filter-based search
    - Backward compatibility with existing code
    """
    
    def __init__(self, config: ConfigManager):
        """Initialize Zonaprop provider.
        
        Args:
            config: Configuration manager with Zonaprop settings
        """
        
    def fetch_properties(
        self,
        location: Optional[str] = None,
        property_type: Optional[str] = None,
        operation_type: Optional[str] = None,
        max_results: Optional[int] = None,
        url: Optional[str] = None,
        rooms_min: Optional[int] = None,
        rooms_max: Optional[int] = None,
        **kwargs
    ) -> pd.DataFrame:
        """Fetch properties from Zonaprop.
        
        Args:
            location: Location name (mapped to Zonaprop URL format)
            property_type: Property type ('apartment', 'house', etc.)
            operation_type: Operation type ('sale', 'rent')
            max_results: Maximum number of properties to fetch
            url: Direct Zonaprop URL (for backward compatibility)
            rooms_min: Minimum number of rooms
            rooms_max: Maximum number of rooms
            **kwargs: Additional parameters
            
        Returns:
            DataFrame with property listings in unified schema
            
        Raises:
            ScrapingError: When scraping fails
            ZonapropAntiBotError: When anti-bot measures are encountered
        """
        
    def get_provider_name(self) -> str:
        """Return provider name."""
        return "zonaprop"
        
    def validate_filters(self, **filters) -> Dict:
        """Validate Zonaprop-specific filters."""
```

## Provider Registry

Central registry for managing provider discovery and instantiation.

```python
class ProviderRegistry:
    """Registry for real estate data providers.
    
    Manages provider registration, discovery, and instantiation.
    Providers are automatically registered when their modules are imported.
    """
    
    _providers: Dict[str, Type[RealEstateProvider]] = {}
    
    @classmethod
    def register(cls, name: str, provider_class: Type[RealEstateProvider]):
        """Register a provider class.
        
        Args:
            name: Unique provider name
            provider_class: Provider class implementing RealEstateProvider
            
        Raises:
            ValueError: If provider name is already registered
        """
        
    @classmethod
    def get_provider(
        cls, 
        name: str, 
        config: ConfigManager
    ) -> RealEstateProvider:
        """Get an instance of a registered provider.
        
        Args:
            name: Provider name to instantiate
            config: Configuration manager instance
            
        Returns:
            Configured provider instance
            
        Raises:
            ProviderNotFoundError: If provider name is not registered
        """
        
    @classmethod
    def list_providers(cls) -> List[str]:
        """List all registered provider names.
        
        Returns:
            List of available provider names
        """
        
    @classmethod
    def is_registered(cls, name: str) -> bool:
        """Check if a provider is registered.
        
        Args:
            name: Provider name to check
            
        Returns:
            True if provider is registered, False otherwise
        """
```

## Data Schema

All providers must return data conforming to the unified schema:

| Column | Type | Required | Description |
|--------|------|----------|-------------|
| `id` | str | Yes | Unique property identifier |
| `title` | str | Yes | Property title/description |
| `price_usd` | float | No | Price in USD |
| `price_ars` | float | No | Price in ARS |
| `address` | str | No | Property address |
| `latitude` | float | No | Latitude coordinate |
| `longitude` | float | No | Longitude coordinate |
| `property_type` | str | No | Property type (apartment, house, etc.) |
| `operation_type` | str | No | Operation type (sale, rent, etc.) |
| `rooms` | float | No | Number of rooms |
| `bathrooms` | float | No | Number of bathrooms |
| `surface_m2` | float | No | Surface area in square meters |
| `listing_url` | str | No | URL to the original listing |
| `source` | str | Yes | Provider name |

## Exception Hierarchy

```python
class ProviderError(RentaError):
    """Base exception for provider errors."""
    pass

class ProviderNotFoundError(ProviderError):
    """Raised when requested provider doesn't exist."""
    pass

class ProviderAPIError(ProviderError):
    """Raised when provider API returns an error."""
    pass

class ProviderRateLimitError(ProviderAPIError):
    """Raised when provider rate limit is exceeded."""
    pass
```

## Usage Examples

### Basic Provider Usage

```python
from renta import RealEstateAnalyzer

analyzer = RealEstateAnalyzer()

# Fetch from MercadoLibre
properties = analyzer.fetch_properties(
    provider="mercadolibre",
    location="palermo",
    property_type="apartment",
    operation_type="rent"
)

# Fetch from Zonaprop
properties = analyzer.fetch_properties(
    provider="zonaprop",
    location="recoleta",
    property_type="house",
    operation_type="sale"
)
```

### Direct Provider Usage

```python
from renta.providers.registry import ProviderRegistry
from renta.config import ConfigManager

config = ConfigManager()

# Get MercadoLibre provider
ml_provider = ProviderRegistry.get_provider("mercadolibre", config)
properties = ml_provider.fetch_properties(
    location="palermo",
    property_type="apartment",
    max_results=100
)

# List available providers
providers = ProviderRegistry.list_providers()
print(f"Available providers: {providers}")
```

### Adding Custom Providers

```python
from renta.providers.base import BaseRealEstateProvider
from renta.providers.registry import ProviderRegistry

class CustomProvider(BaseRealEstateProvider):
    def fetch_properties(self, **filters):
        # Implement custom data fetching
        raw_data = self._fetch_from_custom_source(filters)
        return self._normalize_to_schema(raw_data)
    
    def get_provider_name(self):
        return "custom"
    
    def validate_filters(self, **filters):
        # Validate custom filters
        return filters

# Register the provider
ProviderRegistry.register("custom", CustomProvider)

# Use the custom provider
analyzer = RealEstateAnalyzer()
properties = analyzer.fetch_properties(provider="custom", location="test")
```

## Configuration

Provider-specific configuration is managed through the `real_estate.providers` section:

```yaml
real_estate:
  default_provider: "mercadolibre"
  providers:
    mercadolibre:
      rate_limit_seconds: 1.0
      max_retries: 3
      timeout_seconds: 30
      max_results_per_request: 50
      cache_ttl_hours: 24
      defaults:
        country: "AR"
        state: "TUxBUENBUGw3M2E1"
    zonaprop:
      rate_limit_seconds: 5.0
      max_retries: 3
      timeout_seconds: 30
      cache_ttl_hours: 24
```

Each provider can access its configuration through the `ConfigManager` instance passed during initialization.