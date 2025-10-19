"""Real estate data providers package.

This package contains implementations of real estate data providers that
fetch property listings from various sources and normalize them to a
unified schema.
"""

from .base import RealEstateProvider, BaseRealEstateProvider
from .registry import ProviderRegistry
from .mercadolibre import MercadoLibreProvider

# Auto-register providers
ProviderRegistry.register("mercadolibre", MercadoLibreProvider)

# Import Zonaprop provider
from .zonaprop import ZonapropProvider
ProviderRegistry.register("zonaprop", ZonapropProvider)

__all__ = [
    "RealEstateProvider",
    "BaseRealEstateProvider", 
    "ProviderRegistry",
    "MercadoLibreProvider",
    "ZonapropProvider",
]