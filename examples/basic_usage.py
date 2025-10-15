#!/usr/bin/env python3
"""
Basic RENTA Usage Example

This script demonstrates the core RENTA workflow:
1. Initialize analyzer
2. Download Airbnb data
3. Scrape property listings
4. Enrich with rental data
5. Generate AI summaries
6. Export results

Prerequisites:
- AWS credentials configured
- AWS Bedrock model access enabled
- Internet connection for data download
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
    AirbnbDataError,
    ScrapingError,
    ZonapropAntiBotError,
    AIServiceConfigurationError,
    ExportFormatError
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Run basic RENTA analysis pipeline."""
    
    # Example search URL - 2 bedroom apartments in Palermo
    search_url = "https://www.zonaprop.com.ar/inmuebles-venta-palermo-2-dormitorios-50000-130000-dolar.html"
    
    logger.info("Starting RENTA basic usage example")
    logger.info(f"Search URL: {search_url}")
    
    try:
        # Step 1: Initialize analyzer
        logger.info("Initializing RealEstateAnalyzer...")
        analyzer = RealEstateAnalyzer()
        logger.info("✓ Analyzer initialized successfully")
        
        # Step 2: Download Airbnb data (first run or force refresh)
        logger.info("Downloading Airbnb data...")
        try:
            airbnb_data = analyzer.download_airbnb_data(force=False)  # Use cached if fresh
            logger.info(f"✓ Airbnb data loaded: {len(airbnb_data)} listings")
        except AirbnbDataError as e:
            logger.warning(f"Airbnb download failed: {e}")
            logger.info("Continuing without fresh Airbnb data...")
            airbnb_data = None
        
        # Step 3: Scrape property listings
        logger.info("Scraping Zonaprop listings...")
        try:
            properties = analyzer.scrape_zonaprop(search_url)
            logger.info(f"✓ Properties scraped: {len(properties)} listings")
            
            # Show sample property data
            if len(properties) > 0:
                sample_prop = properties.iloc[0]
                logger.info(f"Sample property: {sample_prop.get('title', 'N/A')}")
                logger.info(f"  Price: USD {sample_prop.get('price_usd', 'N/A')}")
                logger.info(f"  Surface: {sample_prop.get('surface_m2', 'N/A')} m²")
                
        except ZonapropAntiBotError as e:
            logger.error(f"Anti-bot protection detected: {e}")
            logger.info("Recommendation: Save search results manually as HTML file")
            logger.info("Then use: analyzer.scrape_zonaprop(url, html_path='saved_file.html')")
            return
            
        except ScrapingError as e:
            logger.error(f"Scraping failed: {e}")
            return
        
        # Step 4: Enrich with Airbnb data
        if airbnb_data is not None and len(properties) > 0:
            logger.info("Enriching properties with Airbnb data...")
            try:
                enriched_properties = analyzer.enrich_with_airbnb(properties)
                
                # Show enrichment statistics
                matched_count = len(enriched_properties[enriched_properties['match_status'] == 'matched'])
                match_rate = matched_count / len(enriched_properties) * 100
                
                logger.info(f"✓ Properties enriched: {len(enriched_properties)} total")
                logger.info(f"  Matched with Airbnb: {matched_count} ({match_rate:.1f}%)")
                
                # Show sample enriched data
                if matched_count > 0:
                    matched_sample = enriched_properties[
                        enriched_properties['match_status'] == 'matched'
                    ].iloc[0]
                    
                    logger.info(f"Sample enriched property:")
                    logger.info(f"  Airbnb avg price (entire home): USD {matched_sample.get('airbnb_avg_price_entire_home', 'N/A')}/night")
                    logger.info(f"  Occupancy probability: {matched_sample.get('airbnb_occupancy_probability', 'N/A')}")
                    logger.info(f"  Review score: {matched_sample.get('airbnb_avg_review_score', 'N/A')}")
                
            except Exception as e:
                logger.warning(f"Enrichment failed: {e}")
                logger.info("Continuing with non-enriched properties...")
                enriched_properties = properties
        else:
            logger.info("Skipping enrichment (no Airbnb data or properties)")
            enriched_properties = properties
        
        # Step 5: Generate AI summaries
        if len(enriched_properties) > 0:
            logger.info("Generating AI investment summaries...")
            try:
                # Limit to first 5 properties for demo
                sample_properties = enriched_properties.head(5)
                summaries = analyzer.generate_summaries(sample_properties)
                
                logger.info(f"✓ AI summaries generated: {len(summaries)} summaries")
                
                # Show sample summary
                if summaries:
                    sample_summary = summaries[0]
                    logger.info(f"Sample AI summary:")
                    logger.info(f"  Property ID: {sample_summary['property_id']}")
                    logger.info(f"  Confidence: {sample_summary['confidence']:.2f}")
                    logger.info(f"  Summary: {sample_summary['summary'][:100]}...")
                
            except AIServiceConfigurationError as e:
                logger.warning(f"AI analysis failed: {e}")
                logger.info("Check AWS credentials and Bedrock model access")
                summaries = []
        else:
            logger.info("No properties to analyze")
            summaries = []
        
        # Step 6: Export results
        logger.info("Exporting results...")
        try:
            # Export as CSV
            csv_path = analyzer.export(enriched_properties, format="csv")
            logger.info(f"✓ Results exported to CSV: {csv_path}")
            
            # Export as JSON for API integration
            json_path = analyzer.export(enriched_properties, format="json")
            logger.info(f"✓ Results exported to JSON: {json_path}")
            
            # Show final statistics
            stats = analyzer.get_operation_stats()
            logger.info(f"Final statistics:")
            logger.info(f"  Downloads: {stats['downloads']}")
            logger.info(f"  Scrapes: {stats['scrapes']}")
            logger.info(f"  Enrichments: {stats['enrichments']}")
            logger.info(f"  AI Analyses: {stats['ai_analyses']}")
            logger.info(f"  Exports: {stats['exports']}")
            
        except ExportFormatError as e:
            logger.error(f"Export failed: {e}")
            logger.info("Results available in memory as DataFrame")
            
    except ConfigurationError as e:
        logger.error(f"Configuration error: {e}")
        logger.info("Check your configuration file or use default settings")
        
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        logger.info("Check logs for details")
        
    finally:
        # Clean up resources
        if 'analyzer' in locals():
            analyzer.close()
            logger.info("✓ Resources cleaned up")
    
    logger.info("Basic usage example completed")


if __name__ == "__main__":
    # Check AWS credentials before starting
    if not os.environ.get('AWS_ACCESS_KEY_ID') and not os.path.exists(os.path.expanduser('~/.aws/credentials')):
        logger.warning("AWS credentials not found!")
        logger.info("Set up AWS credentials using one of these methods:")
        logger.info("1. Environment variables: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY")
        logger.info("2. AWS credentials file: ~/.aws/credentials")
        logger.info("3. IAM role (if running on AWS)")
        
        response = input("Continue anyway? (y/N): ")
        if response.lower() != 'y':
            sys.exit(1)
    
    main()