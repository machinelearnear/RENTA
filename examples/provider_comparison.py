#!/usr/bin/env python3
"""
Provider Comparison Example

This script demonstrates how to fetch data from multiple real estate providers
and compare the results:
1. Fetch properties from both Zonaprop and MercadoLibre
2. Compare data quality and coverage
3. Analyze price differences between providers
4. Export comparative analysis

Prerequisites:
- Internet connection for API access
- RENTA installed and configured
"""

import os
import sys
import logging
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
    ZonapropAntiBotError,
)
from renta.providers import ProviderRegistry

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def fetch_from_provider(analyzer, provider_name, search_params):
    """Fetch properties from a specific provider with error handling."""
    try:
        logger.info(f"Fetching from {provider_name}...")
        
        if provider_name == "zonaprop":
            # For Zonaprop, we need to use a URL (backward compatibility)
            # This is a sample URL for 2-bedroom apartments in Palermo
            url = "https://www.zonaprop.com.ar/inmuebles-venta-palermo-2-dormitorios.html"
            properties = analyzer.scrape_zonaprop(url)
        else:
            # For other providers, use the new fetch_properties method
            properties = analyzer.fetch_properties(provider=provider_name, **search_params)
        
        logger.info(f"✓ {provider_name}: {len(properties)} properties fetched")
        return properties
        
    except ZonapropAntiBotError as e:
        logger.warning(f"{provider_name}: Anti-bot protection detected - {e}")
        return pd.DataFrame()
        
    except ProviderAPIError as e:
        logger.warning(f"{provider_name}: API error - {e}")
        return pd.DataFrame()
        
    except ScrapingError as e:
        logger.warning(f"{provider_name}: Scraping error - {e}")
        return pd.DataFrame()
        
    except Exception as e:
        logger.warning(f"{provider_name}: Unexpected error - {e}")
        return pd.DataFrame()


def analyze_data_quality(properties_df, provider_name):
    """Analyze data quality metrics for a provider."""
    if len(properties_df) == 0:
        return {
            "provider": provider_name,
            "total_properties": 0,
            "completeness": {},
            "price_stats": {}
        }
    
    # Calculate completeness for key fields
    key_fields = ["price_usd", "address", "latitude", "longitude", "rooms", "surface_m2"]
    completeness = {}
    
    for field in key_fields:
        if field in properties_df.columns:
            non_null_count = properties_df[field].notna().sum()
            completeness[field] = (non_null_count / len(properties_df)) * 100
        else:
            completeness[field] = 0
    
    # Price statistics
    price_stats = {}
    if "price_usd" in properties_df.columns and properties_df["price_usd"].notna().any():
        price_data = properties_df["price_usd"].dropna()
        price_stats = {
            "min": price_data.min(),
            "max": price_data.max(),
            "mean": price_data.mean(),
            "median": price_data.median(),
            "std": price_data.std()
        }
    
    return {
        "provider": provider_name,
        "total_properties": len(properties_df),
        "completeness": completeness,
        "price_stats": price_stats
    }


def compare_providers(provider_data):
    """Compare data from multiple providers."""
    logger.info("\nProvider Comparison Analysis:")
    logger.info("=" * 50)
    
    # Overall statistics
    for data in provider_data:
        analysis = data["analysis"]
        logger.info(f"\n{analysis['provider'].upper()} Provider:")
        logger.info(f"  Total properties: {analysis['total_properties']}")
        
        if analysis['total_properties'] > 0:
            # Data completeness
            logger.info("  Data completeness:")
            for field, percentage in analysis['completeness'].items():
                logger.info(f"    {field}: {percentage:.1f}%")
            
            # Price statistics
            if analysis['price_stats']:
                logger.info("  Price statistics (USD):")
                stats = analysis['price_stats']
                logger.info(f"    Range: ${stats['min']:,.0f} - ${stats['max']:,.0f}")
                logger.info(f"    Average: ${stats['mean']:,.0f}")
                logger.info(f"    Median: ${stats['median']:,.0f}")
    
    # Cross-provider comparison
    logger.info("\nCross-Provider Comparison:")
    logger.info("-" * 30)
    
    # Compare total properties
    total_counts = [(data["analysis"]["provider"], data["analysis"]["total_properties"]) 
                   for data in provider_data if data["analysis"]["total_properties"] > 0]
    
    if len(total_counts) > 1:
        logger.info("Property count comparison:")
        for provider, count in sorted(total_counts, key=lambda x: x[1], reverse=True):
            logger.info(f"  {provider}: {count} properties")
    
    # Compare price ranges
    price_providers = [(data["analysis"]["provider"], data["analysis"]["price_stats"]) 
                      for data in provider_data 
                      if data["analysis"]["price_stats"]]
    
    if len(price_providers) > 1:
        logger.info("\nPrice comparison:")
        for provider, stats in price_providers:
            logger.info(f"  {provider}: ${stats['mean']:,.0f} avg, ${stats['median']:,.0f} median")
    
    # Data quality score
    logger.info("\nData Quality Scores:")
    for data in provider_data:
        analysis = data["analysis"]
        if analysis['total_properties'] > 0:
            # Calculate overall completeness score
            completeness_values = list(analysis['completeness'].values())
            avg_completeness = np.mean(completeness_values) if completeness_values else 0
            
            # Quality score (0-100)
            quality_score = avg_completeness
            logger.info(f"  {analysis['provider']}: {quality_score:.1f}/100")


def main():
    """Run provider comparison analysis."""
    
    logger.info("Starting RENTA Provider Comparison Example")
    logger.info("==========================================")

    try:
        # Step 1: Initialize analyzer
        logger.info("Initializing RealEstateAnalyzer...")
        analyzer = RealEstateAnalyzer()
        logger.info("✓ Analyzer initialized successfully")

        # Step 2: Get available providers
        available_providers = ProviderRegistry.list_providers()
        logger.info(f"Available providers: {', '.join(available_providers)}")

        # Step 3: Define search parameters
        search_params = {
            "location": "palermo",
            "property_type": "apartment", 
            "operation_type": "sale",
            "max_results": 50
        }
        
        logger.info(f"Search parameters: {search_params}")

        # Step 4: Fetch data from each provider
        provider_data = []
        
        for provider_name in available_providers:
            logger.info(f"\n--- Fetching from {provider_name} ---")
            
            properties = fetch_from_provider(analyzer, provider_name, search_params)
            analysis = analyze_data_quality(properties, provider_name)
            
            provider_data.append({
                "provider": provider_name,
                "properties": properties,
                "analysis": analysis
            })

        # Step 5: Compare providers
        compare_providers(provider_data)

        # Step 6: Create combined dataset
        logger.info("\nCreating Combined Dataset:")
        logger.info("-" * 30)
        
        combined_properties = []
        for data in provider_data:
            if len(data["properties"]) > 0:
                combined_properties.append(data["properties"])
        
        if combined_properties:
            combined_df = pd.concat(combined_properties, ignore_index=True)
            logger.info(f"Combined dataset: {len(combined_df)} total properties")
            
            # Remove duplicates based on title and price (rough deduplication)
            if len(combined_df) > 0:
                initial_count = len(combined_df)
                combined_df = combined_df.drop_duplicates(
                    subset=["title", "price_usd"], 
                    keep="first"
                )
                final_count = len(combined_df)
                duplicates_removed = initial_count - final_count
                
                logger.info(f"After deduplication: {final_count} unique properties")
                logger.info(f"Duplicates removed: {duplicates_removed}")

            # Step 7: Export results
            logger.info("\nExporting Results:")
            try:
                # Export individual provider data
                for data in provider_data:
                    if len(data["properties"]) > 0:
                        filename = f"provider_comparison_{data['provider']}"
                        csv_path = analyzer.export(
                            data["properties"], 
                            format="csv", 
                            filename=filename
                        )
                        logger.info(f"✓ {data['provider']} data exported: {csv_path}")

                # Export combined data
                if len(combined_df) > 0:
                    combined_path = analyzer.export(
                        combined_df, 
                        format="csv", 
                        filename="provider_comparison_combined"
                    )
                    logger.info(f"✓ Combined data exported: {combined_path}")

            except Exception as e:
                logger.warning(f"Export failed: {e}")

        else:
            logger.warning("No data fetched from any provider")

        # Step 8: Recommendations
        logger.info("\nRecommendations:")
        logger.info("-" * 20)
        
        successful_providers = [data for data in provider_data 
                              if data["analysis"]["total_properties"] > 0]
        
        if successful_providers:
            # Recommend best provider based on data quality
            best_provider = max(
                successful_providers,
                key=lambda x: (
                    x["analysis"]["total_properties"] * 
                    np.mean(list(x["analysis"]["completeness"].values()) or [0])
                )
            )
            
            logger.info(f"Recommended primary provider: {best_provider['provider']}")
            logger.info(f"  Reason: Best combination of quantity and data quality")
            
            if len(successful_providers) > 1:
                logger.info("Consider using multiple providers for:")
                logger.info("  - Broader market coverage")
                logger.info("  - Cross-validation of prices")
                logger.info("  - Backup when one provider is unavailable")
        else:
            logger.warning("No providers returned data successfully")
            logger.info("Check network connection and provider availability")

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

    logger.info("\nProvider comparison example completed")


if __name__ == "__main__":
    main()