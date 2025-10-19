"""Zonaprop provider for real estate data.

This module provides a wrapper around the existing ZonapropScraper class
to implement the RealEstateProvider interface, enabling Zonaprop to be used
as a pluggable data source in the provider architecture.
"""

import re
from typing import Dict, Optional, Any
import pandas as pd
import structlog

from .base import BaseRealEstateProvider
from ..ingestion import ZonapropScraper
from ..exceptions import ProviderError

logger = structlog.get_logger()


class ZonapropProvider(BaseRealEstateProvider):
    """Provider for Zonaprop real estate data.
    
    Wraps the existing ZonapropScraper class to implement the RealEstateProvider
    interface, allowing Zonaprop to be used through the unified provider system
    while maintaining full backward compatibility with existing code.
    
    This provider uses web scraping with Playwright to extract property data
    from Zonaprop.com.ar, Argentina's leading real estate website. It includes
    Cloudflare bypass capabilities and robust error handling.
    
    Key features:
    - Playwright-based web scraping with stealth techniques
    - Cloudflare anti-bot protection bypass
    - Comprehensive property coverage across Argentina
    - Backward compatibility with direct URL scraping
    - Automatic property/operation type inference from URLs
    
    Supported property types:
    - apartment: Departamentos
    - house: Casas
    - land: Terrenos
    - commercial: Locales
    - office: Oficinas
    - ph: PH (Propiedad Horizontal)
    - quinta: Quintas
    - cochera: Cocheras
    - deposito: Depósitos
    
    Supported operation types:
    - sale: Venta
    - rent: Alquiler
    - temporary_rent: Alquiler temporal
    
    Example:
        >>> from renta.providers.zonaprop import ZonapropProvider
        >>> from renta.config import ConfigManager
        >>> 
        >>> config = ConfigManager()
        >>> provider = ZonapropProvider(config)
        >>> 
        >>> # Fetch houses for sale in Recoleta
        >>> properties = provider.fetch_properties(
        ...     location="recoleta",
        ...     property_type="house",
        ...     operation_type="sale",
        ...     max_results=50
        ... )
        >>> 
        >>> # Or use direct URL (backward compatibility)
        >>> properties = provider.fetch_properties(
        ...     url="https://www.zonaprop.com.ar/casas-venta-recoleta.html"
        ... )
    """
    
    def __init__(self, config):
        """Initialize ZonapropProvider.
        
        Args:
            config: ConfigManager instance
        """
        super().__init__(config)
        self.scraper = ZonapropScraper(config)
        
        # Property type mappings from generic to Zonaprop URL format
        self.property_type_mapping = {
            'apartment': 'departamentos',
            'house': 'casas',
            'land': 'terrenos',
            'commercial': 'locales',
            'office': 'oficinas',
            'ph': 'ph',
            'quinta': 'quintas',
            'cochera': 'cocheras',
            'deposito': 'depositos'
        }
        
        # Operation type mappings from generic to Zonaprop URL format
        self.operation_type_mapping = {
            'sale': 'venta',
            'rent': 'alquiler',
            'temporary_rent': 'alquiler-temporal'
        }
    
    def get_provider_name(self) -> str:
        """Return the unique name of this provider.
        
        Returns:
            Provider name string
        """
        return "zonaprop"
    
    def validate_filters(self, **filters) -> Dict[str, Any]:
        """Validate and normalize filter parameters.
        
        Args:
            **filters: Filter parameters to validate
            
        Returns:
            Dictionary of validated filters
            
        Raises:
            ProviderError: If filters are invalid
        """
        validated = {}
        
        # Validate location (optional)
        location = filters.get('location')
        if location is not None:
            if not isinstance(location, str) or not location.strip():
                raise ProviderError("Location must be a non-empty string")
            validated['location'] = location.strip().lower()
        
        # Validate property_type (optional)
        property_type = filters.get('property_type')
        if property_type is not None:
            if property_type not in self.property_type_mapping:
                available_types = list(self.property_type_mapping.keys())
                raise ProviderError(
                    f"Invalid property_type: {property_type}. "
                    f"Available types: {available_types}"
                )
            validated['property_type'] = property_type
        
        # Validate operation_type (optional)
        operation_type = filters.get('operation_type')
        if operation_type is not None:
            if operation_type not in self.operation_type_mapping:
                available_operations = list(self.operation_type_mapping.keys())
                raise ProviderError(
                    f"Invalid operation_type: {operation_type}. "
                    f"Available operations: {available_operations}"
                )
            validated['operation_type'] = operation_type
        
        # Validate max_results (optional)
        max_results = filters.get('max_results')
        if max_results is not None:
            try:
                max_results = int(max_results)
                if max_results <= 0:
                    raise ProviderError("max_results must be a positive integer")
                validated['max_results'] = max_results
            except (ValueError, TypeError):
                raise ProviderError("max_results must be a valid integer")
        
        # Pass through URL for backward compatibility
        url = filters.get('url')
        if url is not None:
            if not isinstance(url, str) or not url.strip():
                raise ProviderError("URL must be a non-empty string")
            validated['url'] = url.strip()
        
        return validated
    
    def fetch_properties(
        self,
        location: Optional[str] = None,
        property_type: Optional[str] = None,
        operation_type: Optional[str] = None,
        max_results: Optional[int] = None,
        url: Optional[str] = None,  # For backward compatibility
        **kwargs
    ) -> pd.DataFrame:
        """Fetch properties from Zonaprop.
        
        Args:
            location: Location filter (neighborhood, city, etc.)
            property_type: Type of property (apartment, house, etc.)
            operation_type: Operation type (sale, rent, etc.)
            max_results: Maximum number of results to return
            url: Direct URL for backward compatibility
            **kwargs: Additional provider-specific parameters
            
        Returns:
            DataFrame with normalized property data
        """
        # Validate filters
        filters = {
            'location': location,
            'property_type': property_type,
            'operation_type': operation_type,
            'max_results': max_results,
            'url': url,
            **kwargs
        }
        validated_filters = self.validate_filters(**filters)
        
        # Check cache first (unless force refresh is requested)
        force_refresh = kwargs.get('force_refresh', False)
        if not force_refresh:
            cache_key = self._get_cache_key(**validated_filters)
            cached_data = self._get_cached_data(cache_key)
            if cached_data is not None:
                return cached_data
        
        try:
            # Use direct URL if provided (backward compatibility)
            if validated_filters.get('url'):
                search_url = validated_filters['url']
                self.logger.info(
                    "Fetching Zonaprop properties from direct URL",
                    url=search_url,
                    provider=self.get_provider_name()
                )
            else:
                # Build URL from filters
                search_url = self._build_search_url(
                    validated_filters.get('location'),
                    validated_filters.get('property_type'),
                    validated_filters.get('operation_type')
                )
                self.logger.info(
                    "Fetching Zonaprop properties from filters",
                    location=location,
                    property_type=property_type,
                    operation_type=operation_type,
                    url=search_url,
                    provider=self.get_provider_name()
                )
            
            # Fetch data using existing scraper
            raw_data = self.scraper.scrape_search_results(search_url)
            
            # Convert to unified schema
            normalized_data = self._convert_to_unified_schema(raw_data)
            
            # Apply max_results limit if specified
            max_results = validated_filters.get('max_results')
            if max_results and len(normalized_data) > max_results:
                normalized_data = normalized_data.head(max_results)
            
            # Cache the results
            if not force_refresh:
                cache_key = self._get_cache_key(**validated_filters)
                self._save_to_cache(cache_key, normalized_data)
            
            self.logger.info(
                "Successfully fetched Zonaprop properties",
                properties_count=len(normalized_data),
                provider=self.get_provider_name()
            )
            
            return normalized_data
            
        except Exception as e:
            self.logger.error(
                "Failed to fetch Zonaprop properties",
                error=str(e),
                provider=self.get_provider_name(),
                filters=validated_filters
            )
            raise ProviderError(f"Failed to fetch Zonaprop properties: {e}") from e
    
    def _build_search_url(
        self,
        location: Optional[str],
        property_type: Optional[str],
        operation_type: Optional[str]
    ) -> str:
        """Build Zonaprop search URL from filters.
        
        Args:
            location: Location filter (neighborhood, city, etc.)
            property_type: Type of property (apartment, house, etc.)
            operation_type: Operation type (sale, rent, etc.)
            
        Returns:
            Zonaprop search URL
        """
        base_url = "https://www.zonaprop.com.ar"
        
        # Start building URL components
        url_parts = []
        
        # Add property type if specified
        if property_type:
            zonaprop_type = self.property_type_mapping.get(property_type)
            if zonaprop_type:
                url_parts.append(zonaprop_type)
        
        # Add operation type if specified
        if operation_type:
            zonaprop_operation = self.operation_type_mapping.get(operation_type)
            if zonaprop_operation:
                url_parts.append(zonaprop_operation)
        
        # Add location if specified
        if location:
            # Normalize location for URL (remove accents, spaces, etc.)
            normalized_location = self._normalize_location_for_url(location)
            if normalized_location:
                url_parts.append(normalized_location)
        
        # Build final URL
        if url_parts:
            url_path = "-".join(url_parts) + ".html"
            search_url = f"{base_url}/{url_path}"
        else:
            # Default to general properties search if no filters
            search_url = f"{base_url}/propiedades.html"
        
        self.logger.debug(
            "Built Zonaprop search URL",
            location=location,
            property_type=property_type,
            operation_type=operation_type,
            url=search_url,
            provider=self.get_provider_name()
        )
        
        return search_url
    
    def _normalize_location_for_url(self, location: str) -> str:
        """Normalize location string for use in Zonaprop URLs.
        
        Args:
            location: Raw location string
            
        Returns:
            Normalized location string suitable for URLs
        """
        if not location:
            return ""
        
        # Convert to lowercase
        normalized = location.lower().strip()
        
        # Remove common prefixes/suffixes
        prefixes_to_remove = ['barrio ', 'b° ', 'zona ', 'área ']
        for prefix in prefixes_to_remove:
            if normalized.startswith(prefix):
                normalized = normalized[len(prefix):]
        
        # Replace spaces and special characters with hyphens
        normalized = re.sub(r'[^\w\s-]', '', normalized)  # Remove special chars except hyphens
        normalized = re.sub(r'\s+', '-', normalized)      # Replace spaces with hyphens
        normalized = re.sub(r'-+', '-', normalized)       # Collapse multiple hyphens
        normalized = normalized.strip('-')                # Remove leading/trailing hyphens
        
        # Handle common location mappings
        location_mappings = {
            'capital-federal': 'capital-federal',
            'caba': 'capital-federal',
            'ciudad-autonoma-de-buenos-aires': 'capital-federal',
            'buenos-aires': 'capital-federal',
            'palermo': 'palermo',
            'recoleta': 'recoleta',
            'belgrano': 'belgrano',
            'puerto-madero': 'puerto-madero',
            'san-telmo': 'san-telmo',
            'la-boca': 'la-boca',
            'barracas': 'barracas',
            'villa-crespo': 'villa-crespo',
            'caballito': 'caballito',
            'flores': 'flores',
            'almagro': 'almagro',
            'once': 'once',
            'balvanera': 'balvanera'
        }
        
        return location_mappings.get(normalized, normalized)
    
    def _convert_to_unified_schema(self, zonaprop_data: pd.DataFrame) -> pd.DataFrame:
        """Convert Zonaprop data format to unified provider schema.
        
        Args:
            zonaprop_data: DataFrame from ZonapropScraper
            
        Returns:
            DataFrame with unified schema
        """
        if zonaprop_data.empty:
            return self._empty_dataframe()
        
        # Create a copy to avoid modifying original data
        df = zonaprop_data.copy()
        
        # Map Zonaprop columns to unified schema
        column_mapping = {
            'id': 'id',
            'title': 'title',
            'price_ars': 'price_ars',
            'price_usd': 'price_usd',
            'address': 'address',
            'latitude': 'latitude',
            'longitude': 'longitude',
            'rooms': 'rooms',
            'bathrooms': 'bathrooms',
            'surface_m2': 'surface_m2',
            'listing_url': 'listing_url'
        }
        
        # Rename columns that exist
        for zonaprop_col, unified_col in column_mapping.items():
            if zonaprop_col in df.columns and zonaprop_col != unified_col:
                df = df.rename(columns={zonaprop_col: unified_col})
        
        # Add missing columns with default values
        required_columns = [
            'id', 'title', 'price_usd', 'price_ars', 'address',
            'latitude', 'longitude', 'property_type', 'operation_type',
            'rooms', 'bathrooms', 'surface_m2', 'listing_url', 'source'
        ]
        
        for col in required_columns:
            if col not in df.columns:
                if col == 'source':
                    df[col] = self.get_provider_name()
                elif col in ['property_type', 'operation_type']:
                    df[col] = None  # Will be inferred from URL if possible
                else:
                    df[col] = None
        
        # Set source column
        df['source'] = self.get_provider_name()
        
        # Try to infer property_type and operation_type from listing URLs if available
        if 'listing_url' in df.columns:
            df['property_type'] = df['listing_url'].apply(self._infer_property_type_from_url)
            df['operation_type'] = df['listing_url'].apply(self._infer_operation_type_from_url)
        
        # Ensure correct data types using parent class method
        return self._normalize_to_schema(df.to_dict('records'))
    
    def _infer_property_type_from_url(self, url: str) -> Optional[str]:
        """Infer property type from Zonaprop URL.
        
        Args:
            url: Zonaprop listing URL
            
        Returns:
            Inferred property type or None
        """
        if not url or not isinstance(url, str):
            return None
        
        # Reverse mapping from Zonaprop URL format to generic types
        url_to_type = {
            'departamentos': 'apartment',
            'casas': 'house',
            'terrenos': 'land',
            'locales': 'commercial',
            'oficinas': 'office',
            'ph': 'ph',
            'quintas': 'quinta',
            'cocheras': 'cochera',
            'depositos': 'deposito'
        }
        
        url_lower = url.lower()
        for zonaprop_type, generic_type in url_to_type.items():
            if zonaprop_type in url_lower:
                return generic_type
        
        return None
    
    def _infer_operation_type_from_url(self, url: str) -> Optional[str]:
        """Infer operation type from Zonaprop URL.
        
        Args:
            url: Zonaprop listing URL
            
        Returns:
            Inferred operation type or None
        """
        if not url or not isinstance(url, str):
            return None
        
        # Reverse mapping from Zonaprop URL format to generic types
        url_to_operation = {
            'venta': 'sale',
            'alquiler-temporal': 'temporary_rent',  # Check this first (more specific)
            'alquiler': 'rent'
        }
        
        url_lower = url.lower()
        for zonaprop_operation, generic_operation in url_to_operation.items():
            if zonaprop_operation in url_lower:
                return generic_operation
        
        return None