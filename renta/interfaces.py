"""
Base interfaces and abstract classes for RENTA extensibility.

These interfaces define contracts for pluggable components that can be
extended or replaced by library consumers.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union
import pandas as pd


class ExchangeRateProvider(ABC):
    """Abstract base class for exchange rate providers.

    Allows pluggable exchange rate sources for currency conversion.
    """

    @abstractmethod
    def get_rate(self, from_currency: str, to_currency: str) -> float:
        """Get exchange rate between two currencies.

        Args:
            from_currency: Source currency code (e.g., 'ARS')
            to_currency: Target currency code (e.g., 'USD')

        Returns:
            Exchange rate as float

        Raises:
            RentaError: If rate cannot be retrieved
        """
        pass

    @abstractmethod
    def is_rate_fresh(self, from_currency: str, to_currency: str) -> bool:
        """Check if cached rate is still fresh.

        Args:
            from_currency: Source currency code
            to_currency: Target currency code

        Returns:
            True if rate is fresh, False if needs refresh
        """
        pass


class MatchingStrategy(ABC):
    """Abstract base class for property-Airbnb matching strategies.

    Allows custom matching logic beyond the default spatial matching.
    """

    @abstractmethod
    def match_properties(
        self, properties: pd.DataFrame, airbnb_listings: pd.DataFrame, config: Dict[str, Any]
    ) -> pd.DataFrame:
        """Match properties with Airbnb listings.

        Args:
            properties: DataFrame of property listings
            airbnb_listings: DataFrame of Airbnb listings
            config: Configuration dictionary for matching parameters

        Returns:
            DataFrame with matched property-Airbnb pairs

        Raises:
            MatchingError: If matching fails
        """
        pass

    @abstractmethod
    def calculate_match_score(self, property_row: pd.Series, airbnb_row: pd.Series) -> float:
        """Calculate match score between a property and Airbnb listing.

        Args:
            property_row: Single property record
            airbnb_row: Single Airbnb listing record

        Returns:
            Match score as float (higher = better match)
        """
        pass


class DataExporter(ABC):
    """Abstract base class for data exporters.

    Allows pluggable export formats beyond the built-in ones.
    """

    @abstractmethod
    def export(self, data: pd.DataFrame, path: Optional[str] = None, **kwargs) -> Union[str, Any]:
        """Export data in specific format.

        Args:
            data: DataFrame to export
            path: Optional file path for export
            **kwargs: Format-specific export options

        Returns:
            File path if exported to file, or in-memory object

        Raises:
            ExportFormatError: If export fails
        """
        pass

    @abstractmethod
    def get_file_extension(self) -> str:
        """Get file extension for this export format.

        Returns:
            File extension including dot (e.g., '.csv')
        """
        pass
