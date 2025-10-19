#!/usr/bin/env python3
"""
Basic MercadoLibre Usage Example

This script demonstrates how to use RENTA with the MercadoLibre provider:
1. Initialize analyzer with MercadoLibre provider
2. Fetch property listings from MercadoLibre API
3. Display basic property information
4. Export results

Prerequisites:
- Internet connection for MercadoLibre API access
- RENTA installed and configured
"""

import os
import sys
import logging
from pathlib import Path

# Add RENTA to path if running from source
sys.path.insert(0, str(Path(__file__).parent.parent))

from renta import RealEstateAnalyzer
from renta.exceptions import (
    ConfigurationError,
    ScrapingError,
    ProviderNotFoundError,
    ProviderAPIError,
    ExportFormatError,
)

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def main():
    """Run basic MercadoLibre analysis pipeline."""

    logger.info("Starting RENTA MercadoLibre basic usage example")

    try:
        # Step 1: Initialize analyzer
        logger.info("Initializing RealEstateAnalyzer...")
        analyzer = RealEstateAnalyzer()
        logger.info("✓ Analyzer initialized successfully")

        # Step 2: Fetch properties from MercadoLibre
        logger.info("Fetching properties from MercadoLibre...")
        try:
            # Basic search for apartments in Palermo, Buenos Aires
            properties = analyzer.fetch_properties(
                provider="mercadolibre",
                location="palermo",
                property_type="apartment",
                operation_type="sale",
                max_results=20
            )
            
            logger.info(f"✓ Properties fetched: {len(properties)} listings")

            # Display basic statistics
            if len(properties) > 0:
                logger.info("Property Statistics:")
                logger.info(f"  Total properties: {len(properties)}")
                logger.info(f"  Price range (USD): ${properties['price_usd'].min():.0f} - ${properties['price_usd'].max():.0f}")
                logger.info(f"  Average price (USD): ${properties['price_usd'].mean():.0f}")
                
                # Show sample properties
                logger.info("\nSample Properties:")
                for i, (_, prop) in enumerate(properties.head(3).iterrows()):
                    logger.info(f"  {i+1}. {prop.get('title', 'N/A')}")
                    logger.info(f"     Price: USD ${prop.get('price_usd', 'N/A'):,.0f}")
                    logger.info(f"     Location: {prop.get('address', 'N/A')}")
                    logger.info(f"     Rooms: {prop.get('rooms', 'N/A')}")
                    logger.info(f"     Surface: {prop.get('surface_m2', 'N/A')} m²")
                    logger.info(f"     URL: {prop.get('listing_url', 'N/A')}")
                    logger.info("")

        except ProviderAPIError as e:
            logger.error(f"MercadoLibre API error: {e}")
            logger.info("This might be due to rate limiting or API issues")
            return

        except ProviderNotFoundError as e:
            logger.error(f"Provider error: {e}")
            logger.info("Make sure MercadoLibre provider is properly installed")
            return

        except ScrapingError as e:
            logger.error(f"Data fetching failed: {e}")
            return

        # Step 3: Export results
        if len(properties) > 0:
            logger.info("Exporting results...")
            try:
                # Export as CSV
                csv_path = analyzer.export(properties, format="csv", filename="mercadolibre_basic")
                logger.info(f"✓ Results exported to CSV: {csv_path}")

                # Export as JSON for API integration
                json_path = analyzer.export(properties, format="json", filename="mercadolibre_basic")
                logger.info(f"✓ Results exported to JSON: {json_path}")

            except ExportFormatError as e:
                logger.error(f"Export failed: {e}")
                logger.info("Results available in memory as DataFrame")

        # Step 4: Show provider information
        logger.info("\nProvider Information:")
        logger.info(f"  Data source: MercadoLibre API")
        logger.info(f"  Provider name: mercadolibre")
        logger.info(f"  Data freshness: Real-time from API")
        
        # Show available providers
        from renta.providers import ProviderRegistry
        available_providers = ProviderRegistry.list_providers()
        logger.info(f"  Available providers: {', '.join(available_providers)}")

    except ConfigurationError as e:
        logger.error(f"Configuration error: {e}")
        logger.info("Check your configuration file or use default settings")

    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        logger.info("Check logs for details")

    finally:
        # Clean up resources
        if "analyzer" in locals():
            analyzer.close()
            logger.info("✓ Resources cleaned up")

    logger.info("MercadoLibre basic usage example completed")


if __name__ == "__main__":
    # Show usage information
    logger.info("RENTA MercadoLibre Basic Usage Example")
    logger.info("=====================================")
    logger.info("This example demonstrates basic property fetching from MercadoLibre")
    logger.info("No AWS credentials required for this example")
    logger.info("")

    main()