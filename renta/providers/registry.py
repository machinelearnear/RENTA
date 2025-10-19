"""Provider registry for real estate data sources.

This module manages the registration and discovery of real estate data providers,
allowing the system to dynamically load and use different data sources.
"""

from typing import Dict, Type, List
from ..config import ConfigManager
from ..exceptions import ProviderNotFoundError
from .base import RealEstateProvider


class ProviderRegistry:
    """Registry for real estate data providers.
    
    Central registry that manages provider registration and provides a factory
    interface for creating provider instances. Providers are automatically
    registered when their modules are imported, making the system easily
    extensible.
    
    The registry acts as a service locator pattern, allowing the main analyzer
    to request providers by name without knowing their implementation details.
    This enables loose coupling between the core system and data sources.
    
    Key features:
    - Automatic provider registration on module import
    - Factory pattern for provider instantiation
    - Provider discovery and listing capabilities
    - Type-safe provider management
    
    Example:
        >>> from renta.providers.registry import ProviderRegistry
        >>> from renta.config import ConfigManager
        >>> 
        >>> # List available providers
        >>> providers = ProviderRegistry.list_providers()
        >>> print(f"Available providers: {providers}")
        >>> # Output: ['zonaprop', 'mercadolibre']
        >>> 
        >>> # Get a provider instance
        >>> config = ConfigManager()
        >>> ml_provider = ProviderRegistry.get_provider("mercadolibre", config)
        >>> 
        >>> # Check if a provider is registered
        >>> if ProviderRegistry.is_registered("custom_provider"):
        ...     provider = ProviderRegistry.get_provider("custom_provider", config)
        
        Adding a new provider:
        >>> from renta.providers.base import BaseRealEstateProvider
        >>> 
        >>> class MyProvider(BaseRealEstateProvider):
        ...     def get_provider_name(self):
        ...         return "myprovider"
        ...     # ... implement other methods
        >>> 
        >>> # Register the provider
        >>> ProviderRegistry.register("myprovider", MyProvider)
    """
    
    _providers: Dict[str, Type[RealEstateProvider]] = {}
    
    @classmethod
    def register(cls, name: str, provider_class: Type[RealEstateProvider]) -> None:
        """Register a provider class.
        
        Args:
            name: Unique provider name (e.g., 'zonaprop', 'mercadolibre')
            provider_class: Provider class that implements RealEstateProvider
        """
        cls._providers[name] = provider_class
    
    @classmethod
    def get_provider(cls, name: str, config: ConfigManager) -> RealEstateProvider:
        """Get an instance of a registered provider.
        
        Args:
            name: Provider name
            config: Configuration manager instance
            
        Returns:
            Provider instance
            
        Raises:
            ProviderNotFoundError: If provider is not registered
        """
        if name not in cls._providers:
            available = list(cls._providers.keys())
            raise ProviderNotFoundError(
                f"Unknown provider: {name}. Available providers: {available}"
            )
        
        provider_class = cls._providers[name]
        return provider_class(config)
    
    @classmethod
    def list_providers(cls) -> List[str]:
        """List all registered provider names.
        
        Returns:
            List of provider names
        """
        return list(cls._providers.keys())
    
    @classmethod
    def is_registered(cls, name: str) -> bool:
        """Check if a provider is registered.
        
        Args:
            name: Provider name to check
            
        Returns:
            True if provider is registered, False otherwise
        """
        return name in cls._providers