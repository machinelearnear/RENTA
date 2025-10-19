"""
Async wrapper for Zonaprop scraping with Playwright support.

Provides a unified interface to choose between cloudscraper and Playwright approaches.
"""

import asyncio
import pandas as pd
from typing import Optional

from ..config import ConfigManager
from ..exceptions import ScrapingError
import structlog


logger = structlog.get_logger(__name__)


async def scrape_zonaprop_async(
    search_url: str,
    config: ConfigManager,
    max_pages: Optional[int] = None
) -> pd.DataFrame:
    """
    Scrape Zonaprop using the configured method (Playwright or cloudscraper).

    Args:
        search_url: Zonaprop search URL to scrape
        config: ConfigManager instance
        max_pages: Maximum pages to scrape (optional override)

    Returns:
        DataFrame of normalized property listings

    Raises:
        ScrapingError: If scraping fails with both methods
    """
    use_playwright = config.get("zonaprop.scraping.use_playwright", False)

    if use_playwright:
        logger.info("Using Playwright scraper", url=search_url)
        from ..zonaprop_playwright_client import ZonapropPlaywrightClient

        async with ZonapropPlaywrightClient(config) as client:
            return await client.scrape_search_results(search_url, max_pages=max_pages)
    else:
        logger.info("Using cloudscraper scraper (sync)", url=search_url)
        # Run sync scraper in thread pool
        from ..ingestion import ZonapropScraper
        scraper = ZonapropScraper(config)

        # Run in executor to not block event loop
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: scraper.scrape_search_results(search_url)
        )


def scrape_zonaprop_sync(
    search_url: str,
    config: ConfigManager,
    max_pages: Optional[int] = None
) -> pd.DataFrame:
    """
    Synchronous wrapper for scraping Zonaprop.

    This function creates an event loop and runs the async scraper.
    Use this when calling from synchronous code.

    Args:
        search_url: Zonaprop search URL to scrape
        config: ConfigManager instance
        max_pages: Maximum pages to scrape (optional override)

    Returns:
        DataFrame of normalized property listings

    Raises:
        ScrapingError: If scraping fails
    """
    try:
        # Check if there's already an event loop running
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # We're in an async context, can't use asyncio.run()
            raise RuntimeError(
                "Cannot use sync wrapper from within async context. "
                "Use scrape_zonaprop_async() instead."
            )
    except RuntimeError:
        # No event loop, create one
        pass

    return asyncio.run(scrape_zonaprop_async(search_url, config, max_pages))
