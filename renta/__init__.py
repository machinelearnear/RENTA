"""
RENTA (Real Estate Network and Trend Analyzer)

A Python library for real estate investment analysis in Buenos Aires,
combining Airbnb rental data, Zonaprop property listings, and AI-powered
investment summaries.

LEGAL NOTICE: This library involves web scraping and data processing activities.
Users are responsible for ensuring compliance with all applicable laws,
regulations, and terms of service. See LEGAL_COMPLIANCE.md for detailed guidance.
"""

__version__ = "0.1.1"
__author__ = "RENTA Development Team"
__email__ = "contact@renta.dev"
__license__ = "MIT"

import os
import warnings
from pathlib import Path


def show_legal_notice():
    """Display legal notice for RENTA usage."""
    notice = """
    ╔══════════════════════════════════════════════════════════════════════════════╗
    ║                              RENTA LEGAL NOTICE                              ║
    ╠══════════════════════════════════════════════════════════════════════════════╣
    ║                                                                              ║
    ║  This library performs web scraping and data processing activities.          ║
    ║  Users are responsible for ensuring compliance with:                         ║
    ║                                                                              ║
    ║  • Website terms of service and robots.txt files                            ║
    ║  • Data protection laws (GDPR, CCPA, Argentina Ley 25.326, etc.)           ║
    ║  • Copyright and intellectual property rights                                ║
    ║  • AWS service terms and data processing agreements                          ║
    ║                                                                              ║
    ║  See LEGAL_COMPLIANCE.md for comprehensive guidance.                         ║
    ║                                                                              ║
    ║  By using this library, you acknowledge responsibility for legal compliance. ║
    ║                                                                              ║
    ╚══════════════════════════════════════════════════════════════════════════════╝
    """

    # Check if user has acknowledged the notice
    ack_file = Path.home() / ".renta" / "legal_notice_acknowledged"

    if not ack_file.exists():
        print(notice)
        print("\nTo suppress this notice in future sessions, set environment variable:")
        print("export RENTA_LEGAL_NOTICE_ACKNOWLEDGED=true")
        print("\nOr create file: ~/.renta/legal_notice_acknowledged")

        # Create acknowledgment file if directory exists
        if ack_file.parent.exists():
            try:
                ack_file.touch()
            except:
                pass  # Ignore errors creating acknowledgment file


def get_legal_notice_text():
    """Get the legal notice text for programmatic access."""
    try:
        notice_path = Path(__file__).resolve().parent / "data" / "legal_notice.md"
        with open(notice_path, "r", encoding="utf-8") as f:
            return f.read()
    except:
        return (
            "Legal notice not available. Please see LEGAL_COMPLIANCE.md in the project repository."
        )


# Show legal notice on import unless suppressed
if not os.getenv("RENTA_LEGAL_NOTICE_ACKNOWLEDGED"):
    ack_file = Path.home() / ".renta" / "legal_notice_acknowledged"
    if not ack_file.exists():
        show_legal_notice()

# Main exports
from .analyzer import RealEstateAnalyzer
from .config import ConfigManager
from .exceptions import (
    RentaError,
    ConfigurationError,
    AirbnbDataError,
    ScrapingError,
    ZonapropAntiBotError,
    MatchingError,
    AIServiceConfigurationError,
    ExportFormatError,
    ProviderError,
    ProviderNotFoundError,
    ProviderAPIError,
    ProviderRateLimitError,
)
from .ingestion import (
    AirbnbIngester,
    ZonapropScraper,
    DataProcessor,
    ExchangeRateProvider,
)
from .spatial import (
    SpatialMatcher,
    EnrichmentEngine,
    DefaultMatchingStrategy,
    MatchingStrategyRegistry,
    register_matching_strategy,
    get_matching_strategy,
    list_matching_strategies,
    get_default_matching_strategy,
)
from .export import (
    ExportManager,
    BaseExporter,
    DataFrameExporter,
    CSVExporter,
    JSONExporter,
)
from .security import (
    SecurityManager,
    CredentialManager,
    PIIScrubber,
    ConfigurationSanitizer,
)
from .providers import (
    RealEstateProvider,
    BaseRealEstateProvider,
    ProviderRegistry,
)

# CLI is available but not exported by default
try:
    from . import cli
except ImportError:
    cli = None

__all__ = [
    "RealEstateAnalyzer",
    "ConfigManager",
    "RentaError",
    "ConfigurationError",
    "AirbnbDataError",
    "ScrapingError",
    "ZonapropAntiBotError",
    "MatchingError",
    "AIServiceConfigurationError",
    "ExportFormatError",
    "ProviderError",
    "ProviderNotFoundError",
    "ProviderAPIError",
    "ProviderRateLimitError",
    "AirbnbIngester",
    "ZonapropScraper",
    "DataProcessor",
    "ExchangeRateProvider",
    "SpatialMatcher",
    "EnrichmentEngine",
    "DefaultMatchingStrategy",
    "MatchingStrategyRegistry",
    "register_matching_strategy",
    "get_matching_strategy",
    "list_matching_strategies",
    "get_default_matching_strategy",
    "ExportManager",
    "BaseExporter",
    "DataFrameExporter",
    "CSVExporter",
    "JSONExporter",
    "SecurityManager",
    "CredentialManager",
    "PIIScrubber",
    "ConfigurationSanitizer",
    "RealEstateProvider",
    "BaseRealEstateProvider",
    "ProviderRegistry",
    "show_legal_notice",
    "get_legal_notice_text",
]
