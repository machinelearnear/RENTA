#!/usr/bin/env python3
"""
Advanced MercadoLibre Usage Example

This script demonstrates advanced MercadoLibre provider features:
1. Advanced filtering options
2. Pagination handling for large datasets
3. Location-based searches
4. Property type filtering
5. Price range analysis
6. Data caching and performance optimization

Prerequisites:
- Internet connection for MercadoLibre API access
- RENTA installed and configured
"""

import os
import sys
import logging
import time
from pathlib import Path
import pandas as pd
import numpy as np

# Add RENTA to path if running from source
sys.path.insert(0, str(Path(__file__).parent.parent))

from renta import RealEstateAnalyzer
from renta.exceptions import (
    ConfigurationError,
    ScrapingError,
    ProviderNotFoundError,
    ProviderAPIError,
    ProviderRateLimitError,
)

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def search_by_location(analyzer, locations):
    """Demonstrate location-based searches."""
    logger.info("\n=== Location-Based Search Demo ===")
    
    location_results = {}
    
    for location in locations:
        logger.info(f"\nSearching in {location}...")
        try:
            properties = analyzer.fetch_properties(
                provider="mercadolibre",
                location=location,
                property_type="apartment",
                operation_type="sale",
                max_results=30
            )
            
            location_results[location] = properties
            
            if len(properties) > 0:
                avg_price = properties["price_usd"].mean()
                price_range = f"${properties['price_usd'].min():,.0f} - ${properties['price_usd'].max():,.0f}"
                logger.info(f"  ✓ {len(properties)} properties found")
                logger.info(f"  Average price: ${avg_price:,.0f}")
                logger.info(f"  Price range: {price_range}")
            else:
                logger.info(f"  No properties found in {location}")
                
        except Exception as e:
            logger.warning(f"  Error searching {location}: {e}")
            location_results[location] = pd.DataFrame()
    
    return location_results


def search_by_property_type(analyzer, property_types):
    """Demonstrate property type filtering."""
    logger.info("\n=== Property Type Search Demo ===")
    
    type_results = {}
    
    for prop_type in property_types:
        logger.info(f"\nSearching for {prop_type}s...")
        try:
            properties = analyzer.fetch_properties(
                provider="mercadolibre",
                location="capital federal",
                property_type=prop_type,
                operation_type="sale",
                max_results=25
            )
            
            type_results[prop_type] = properties
            
            if len(properties) > 0:
                avg_price = properties["price_usd"].mean()
                avg_surface = properties["surface_m2"].mean() if "surface_m2" in properties.columns else 0
                logger.info(f"  ✓ {len(properties)} {prop_type}s found")
                logger.info(f"  Average price: ${avg_price:,.0f}")
                if avg_surface > 0:
                    logger.info(f"  Average surface: {avg_surface:.0f} m²")
                    logger.info(f"  Price per m²: ${avg_price/avg_surface:.0f}")
            else:
                logger.info(f"  No {prop_type}s found")
                
        except Exception as e:
            logger.warning(f"  Error searching {prop_type}: {e}")
            type_results[prop_type] = pd.DataFrame()
    
    return type_results


def pagination_demo(analyzer):
    """Demonstrate pagination handling for large datasets."""
    logger.info("\n=== Pagination Demo ===")
    
    # Search with different result limits to show pagination
    result_limits = [10, 50, 100, 200]
    
    for limit in result_limits:
        logger.info(f"\nFetching up to {limit} properties...")
        start_time = time.time()
        
        try:
            properties = analyzer.fetch_properties(
                provider="mercadolibre",
                location="palermo",
                property_type="apartment",
                operation_type="sale",
                max_results=limit
            )
            
            fetch_time = time.time() - start_time
            
            logger.info(f"  ✓ Retrieved {len(properties)} properties in {fetch_time:.2f}s")
            logger.info(f"  Rate: {len(properties)/fetch_time:.1f} properties/second")
            
            if len(properties) > 0:
                # Show data distribution
                price_quartiles = properties["price_usd"].quantile([0.25, 0.5, 0.75])
                logger.info(f"  Price quartiles: Q1=${price_quartiles[0.25]:,.0f}, "
                          f"Q2=${price_quartiles[0.5]:,.0f}, Q3=${price_quartiles[0.75]:,.0f}")
            
        except ProviderRateLimitError as e:
            logger.warning(f"  Rate limit hit: {e}")
            logger.info("  Waiting before next request...")
            time.sleep(5)
            
        except Exception as e:
            logger.warning(f"  Error with limit {limit}: {e}")


def price_analysis_demo(analyzer):
    """Demonstrate price analysis across different segments."""
    logger.info("\n=== Price Analysis Demo ===")
    
    # Fetch data for price analysis
    logger.info("Fetching comprehensive dataset for analysis...")
    
    try:
        properties = analyzer.fetch_properties(
            provider="mercadolibre",
            location="capital federal",
            property_type="apartment",
            operation_type="sale",
            max_results=150
        )
        
        if len(properties) == 0:
            logger.warning("No properties found for price analysis")
            return
        
        logger.info(f"Analyzing {len(properties)} properties...")
        
        # Price distribution analysis
        logger.info("\nPrice Distribution Analysis:")
        price_data = properties["price_usd"].dropna()
        
        if len(price_data) > 0:
            logger.info(f"  Total properties with price: {len(price_data)}")
            logger.info(f"  Price range: ${price_data.min():,.0f} - ${price_data.max():,.0f}")
            logger.info(f"  Mean price: ${price_data.mean():,.0f}")
            logger.info(f"  Median price: ${price_data.median():,.0f}")
            logger.info(f"  Standard deviation: ${price_data.std():,.0f}")
            
            # Price segments
            logger.info("\nPrice Segments:")
            segments = {
                "Budget (< $100k)": price_data[price_data < 100000],
                "Mid-range ($100k - $200k)": price_data[(price_data >= 100000) & (price_data < 200000)],
                "Premium ($200k - $500k)": price_data[(price_data >= 200000) & (price_data < 500000)],
                "Luxury (> $500k)": price_data[price_data >= 500000]
            }
            
            for segment_name, segment_data in segments.items():
                if len(segment_data) > 0:
                    percentage = (len(segment_data) / len(price_data)) * 100
                    avg_price = segment_data.mean()
                    logger.info(f"  {segment_name}: {len(segment_data)} properties ({percentage:.1f}%), avg ${avg_price:,.0f}")
        
        # Room distribution analysis
        if "rooms" in properties.columns:
            logger.info("\nRoom Distribution Analysis:")
            room_data = properties["rooms"].dropna()
            
            if len(room_data) > 0:
                room_counts = room_data.value_counts().sort_index()
                for rooms, count in room_counts.items():
                    percentage = (count / len(room_data)) * 100
                    # Calculate average price for this room count
                    room_properties = properties[properties["rooms"] == rooms]
                    avg_price = room_properties["price_usd"].mean()
                    logger.info(f"  {rooms} rooms: {count} properties ({percentage:.1f}%), avg ${avg_price:,.0f}")
        
        # Surface area analysis
        if "surface_m2" in properties.columns:
            logger.info("\nSurface Area Analysis:")
            surface_data = properties["surface_m2"].dropna()
            
            if len(surface_data) > 0:
                logger.info(f"  Surface range: {surface_data.min():.0f} - {surface_data.max():.0f} m²")
                logger.info(f"  Average surface: {surface_data.mean():.0f} m²")
                
                # Price per square meter
                properties_with_both = properties.dropna(subset=["price_usd", "surface_m2"])
                if len(properties_with_both) > 0:
                    properties_with_both["price_per_m2"] = properties_with_both["price_usd"] / properties_with_both["surface_m2"]
                    avg_price_per_m2 = properties_with_both["price_per_m2"].mean()
                    logger.info(f"  Average price per m²: ${avg_price_per_m2:.0f}")
        
    except Exception as e:
        logger.error(f"Price analysis failed: {e}")


def caching_demo(analyzer):
    """Demonstrate caching behavior."""
    logger.info("\n=== Caching Demo ===")
    
    search_params = {
        "provider": "mercadolibre",
        "location": "palermo",
        "property_type": "apartment",
        "operation_type": "sale",
        "max_results": 20
    }
    
    # First request (should hit API)
    logger.info("First request (should fetch from API)...")
    start_time = time.time()
    
    try:
        properties1 = analyzer.fetch_properties(**search_params)
        first_time = time.time() - start_time
        logger.info(f"  ✓ First request: {len(properties1)} properties in {first_time:.2f}s")
        
        # Second request (should use cache if available)
        logger.info("Second request (may use cache)...")
        start_time = time.time()
        
        properties2 = analyzer.fetch_properties(**search_params)
        second_time = time.time() - start_time
        logger.info(f"  ✓ Second request: {len(properties2)} properties in {second_time:.2f}s")
        
        # Compare timing
        if second_time < first_time * 0.5:  # Significantly faster
            logger.info(f"  Cache hit detected! {first_time/second_time:.1f}x faster")
        else:
            logger.info("  No significant speed improvement (cache miss or disabled)")
            
    except Exception as e:
        logger.warning(f"Caching demo failed: {e}")


def main():
    """Run advanced MercadoLibre demonstration."""
    
    logger.info("Starting RENTA MercadoLibre Advanced Usage Example")
    logger.info("=================================================")

    try:
        # Step 1: Initialize analyzer
        logger.info("Initializing RealEstateAnalyzer...")
        analyzer = RealEstateAnalyzer()
        logger.info("✓ Analyzer initialized successfully")

        # Step 2: Location-based searches
        locations = ["palermo", "recoleta", "belgrano", "san telmo"]
        location_results = search_by_location(analyzer, locations)

        # Step 3: Property type searches
        property_types = ["apartment", "house"]  # Add more types as supported
        type_results = search_by_property_type(analyzer, property_types)

        # Step 4: Pagination demonstration
        pagination_demo(analyzer)

        # Step 5: Price analysis
        price_analysis_demo(analyzer)

        # Step 6: Caching demonstration
        caching_demo(analyzer)

        # Step 7: Export comprehensive results
        logger.info("\n=== Exporting Results ===")
        
        try:
            # Export location comparison
            if any(len(df) > 0 for df in location_results.values()):
                logger.info("Exporting location comparison...")
                
                for location, properties in location_results.items():
                    if len(properties) > 0:
                        filename = f"mercadolibre_advanced_{location.replace(' ', '_')}"
                        csv_path = analyzer.export(properties, format="csv", filename=filename)
                        logger.info(f"  ✓ {location}: {csv_path}")
            
            # Export property type comparison
            if any(len(df) > 0 for df in type_results.values()):
                logger.info("Exporting property type comparison...")
                
                for prop_type, properties in type_results.items():
                    if len(properties) > 0:
                        filename = f"mercadolibre_advanced_{prop_type}s"
                        csv_path = analyzer.export(properties, format="csv", filename=filename)
                        logger.info(f"  ✓ {prop_type}s: {csv_path}")

        except Exception as e:
            logger.warning(f"Export failed: {e}")

        # Step 8: Performance summary
        logger.info("\n=== Performance Summary ===")
        stats = analyzer.get_operation_stats()
        logger.info(f"Total API calls: {stats.get('scrapes', 0)}")
        logger.info(f"Cache hits: {stats.get('cache_hits', 'N/A')}")
        logger.info(f"Rate limit encounters: {stats.get('rate_limits', 'N/A')}")

        # Step 9: Best practices recommendations
        logger.info("\n=== Best Practices Recommendations ===")
        logger.info("1. Use specific location names for better results")
        logger.info("2. Set reasonable max_results to avoid rate limiting")
        logger.info("3. Cache is enabled by default - reuse recent searches")
        logger.info("4. Handle rate limits gracefully with retry logic")
        logger.info("5. Combine multiple searches for comprehensive analysis")
        logger.info("6. Export data regularly to avoid losing results")

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

    logger.info("\nMercadoLibre advanced usage example completed")


if __name__ == "__main__":
    # Show advanced usage information
    logger.info("RENTA MercadoLibre Advanced Usage Example")
    logger.info("========================================")
    logger.info("This example demonstrates:")
    logger.info("• Advanced filtering and search options")
    logger.info("• Pagination handling for large datasets")
    logger.info("• Price and market analysis")
    logger.info("• Performance optimization with caching")
    logger.info("• Best practices for production use")
    logger.info("")

    main()