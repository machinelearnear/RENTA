"""
Synchronous wrapper for ZonapropUndetectedClient.

Provides a simple synchronous interface for scraping Zonaprop using undetected-chromedriver.
"""

import pandas as pd
from ..config import ConfigManager
from ..zonaprop_undetected_client import ZonapropUndetectedClient


def scrape_zonaprop_undetected(url: str, config: ConfigManager) -> pd.DataFrame:
    """
    Scrape Zonaprop using undetected-chromedriver (synchronous).

    This is a wrapper around ZonapropUndetectedClient for easy integration
    with the rest of the application.

    Args:
        url: Zonaprop search URL to scrape
        config: ConfigManager instance

    Returns:
        DataFrame of normalized property listings

    Raises:
        ZonapropAntiBotError: If Cloudflare cannot be bypassed
        ScrapingError: If scraping fails
    """
    with ZonapropUndetectedClient(config) as client:
        return client.scrape_search_results(url)
