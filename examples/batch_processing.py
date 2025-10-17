#!/usr/bin/env python3
"""
Batch Processing Example

This script demonstrates how to efficiently process multiple Zonaprop search URLs
with RENTA, including:
- Parallel processing
- Memory management
- Progress tracking
- Error handling and recovery
- Result aggregation

Use this pattern when analyzing multiple neighborhoods or property types.
"""

import os
import sys
import logging
import time
import pandas as pd
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional

# Add RENTA to path if running from source
sys.path.insert(0, str(Path(__file__).parent.parent))

from renta import RealEstateAnalyzer
from renta.exceptions import (
    ScrapingError,
    ZonapropAntiBotError,
    MatchingError,
    AIServiceConfigurationError,
)

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class BatchProcessor:
    """Handles batch processing of multiple Zonaprop searches."""

    def __init__(self, config_path: Optional[str] = None):
        """Initialize batch processor."""
        self.analyzer = RealEstateAnalyzer(config_path)
        self.results = []
        self.errors = []

        # Download Airbnb data once for all searches
        logger.info("Pre-loading Airbnb data for batch processing...")
        try:
            self.airbnb_data = self.analyzer.download_airbnb_data()
            logger.info(f"✓ Airbnb data loaded: {len(self.airbnb_data)} listings")
        except Exception as e:
            logger.warning(f"Failed to load Airbnb data: {e}")
            self.airbnb_data = None

    def process_single_search(self, search_config: Dict) -> Dict:
        """Process a single search URL."""
        search_url = search_config["url"]
        search_name = search_config.get("name", f"search_{len(self.results) + 1}")

        logger.info(f"Processing {search_name}: {search_url}")

        result = {
            "search_name": search_name,
            "search_url": search_url,
            "status": "failed",
            "properties": pd.DataFrame(),
            "error": None,
            "processing_time": 0,
            "property_count": 0,
            "matched_count": 0,
            "ai_summary_count": 0,
        }

        start_time = time.time()

        try:
            # Step 1: Scrape properties
            properties = self.analyzer.scrape_zonaprop(
                search_url, html_path=search_config.get("html_path")
            )

            if len(properties) == 0:
                result["error"] = "No properties found"
                return result

            result["property_count"] = len(properties)
            logger.info(f"  Scraped {len(properties)} properties")

            # Step 2: Enrich with Airbnb data
            if self.airbnb_data is not None:
                try:
                    enriched_properties = self.analyzer.enrich_with_airbnb(properties)
                    matched_count = len(
                        enriched_properties[enriched_properties["match_status"] == "matched"]
                    )
                    result["matched_count"] = matched_count
                    logger.info(
                        f"  Enriched properties: {matched_count}/{len(enriched_properties)} matched"
                    )
                except MatchingError as e:
                    logger.warning(f"  Enrichment failed: {e}")
                    enriched_properties = properties
            else:
                enriched_properties = properties

            # Step 3: Generate AI summaries (limit to top properties)
            if search_config.get("generate_summaries", True):
                try:
                    # Sort by views_per_day and take top properties
                    top_properties = (
                        enriched_properties.nlargest(
                            search_config.get("max_summaries", 10), "views_per_day"
                        )
                        if "views_per_day" in enriched_properties.columns
                        else enriched_properties.head(10)
                    )

                    summaries = self.analyzer.generate_summaries(top_properties)
                    result["ai_summary_count"] = len(summaries)
                    logger.info(f"  Generated {len(summaries)} AI summaries")

                except AIServiceConfigurationError as e:
                    logger.warning(f"  AI analysis failed: {e}")

            result["properties"] = enriched_properties
            result["status"] = "success"

        except ZonapropAntiBotError as e:
            result["error"] = f"Anti-bot protection: {e}"
            logger.error(f"  {result['error']}")

        except ScrapingError as e:
            result["error"] = f"Scraping error: {e}"
            logger.error(f"  {result['error']}")

        except Exception as e:
            result["error"] = f"Unexpected error: {e}"
            logger.error(f"  {result['error']}")

        result["processing_time"] = time.time() - start_time
        logger.info(f"  Completed in {result['processing_time']:.1f}s")

        return result

    def process_batch_sequential(self, search_configs: List[Dict]) -> List[Dict]:
        """Process searches sequentially."""
        logger.info(f"Processing {len(search_configs)} searches sequentially...")

        results = []
        for i, config in enumerate(search_configs, 1):
            logger.info(f"Progress: {i}/{len(search_configs)}")
            result = self.process_single_search(config)
            results.append(result)

            # Rate limiting between searches
            if i < len(search_configs):
                delay = config.get("delay_seconds", 5)
                logger.info(f"Waiting {delay}s before next search...")
                time.sleep(delay)

        return results

    def process_batch_parallel(
        self, search_configs: List[Dict], max_workers: int = 3
    ) -> List[Dict]:
        """Process searches in parallel (use with caution for rate limiting)."""
        logger.info(f"Processing {len(search_configs)} searches with {max_workers} workers...")

        results = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_config = {
                executor.submit(self.process_single_search, config): config
                for config in search_configs
            }

            # Collect results as they complete
            for future in as_completed(future_to_config):
                config = future_to_config[future]
                try:
                    result = future.result()
                    results.append(result)
                    logger.info(f"Completed: {result['search_name']}")
                except Exception as e:
                    logger.error(f"Failed: {config.get('name', 'unknown')}: {e}")
                    results.append(
                        {
                            "search_name": config.get("name", "unknown"),
                            "search_url": config["url"],
                            "status": "failed",
                            "error": str(e),
                            "properties": pd.DataFrame(),
                        }
                    )

        return results

    def aggregate_results(self, results: List[Dict]) -> Dict:
        """Aggregate results from multiple searches."""
        logger.info("Aggregating batch results...")

        successful_results = [r for r in results if r["status"] == "success"]
        failed_results = [r for r in results if r["status"] == "failed"]

        # Combine all properties
        all_properties = []
        for result in successful_results:
            if not result["properties"].empty:
                # Add search metadata
                props = result["properties"].copy()
                props["search_name"] = result["search_name"]
                props["search_url"] = result["search_url"]
                all_properties.append(props)

        combined_properties = (
            pd.concat(all_properties, ignore_index=True) if all_properties else pd.DataFrame()
        )

        # Calculate aggregate statistics
        total_properties = sum(r["property_count"] for r in successful_results)
        total_matched = sum(r["matched_count"] for r in successful_results)
        total_summaries = sum(r["ai_summary_count"] for r in successful_results)
        total_time = sum(r["processing_time"] for r in results)

        aggregated = {
            "total_searches": len(results),
            "successful_searches": len(successful_results),
            "failed_searches": len(failed_results),
            "total_properties": total_properties,
            "total_matched": total_matched,
            "total_summaries": total_summaries,
            "total_processing_time": total_time,
            "combined_properties": combined_properties,
            "individual_results": results,
            "errors": [r["error"] for r in failed_results if r["error"]],
        }

        logger.info(f"Aggregation complete:")
        logger.info(
            f"  Successful searches: {aggregated['successful_searches']}/{aggregated['total_searches']}"
        )
        logger.info(f"  Total properties: {aggregated['total_properties']}")
        logger.info(f"  Matched properties: {aggregated['total_matched']}")
        logger.info(f"  AI summaries: {aggregated['total_summaries']}")
        logger.info(f"  Total time: {aggregated['total_processing_time']:.1f}s")

        return aggregated

    def export_batch_results(self, aggregated_results: Dict, output_dir: str = "batch_results"):
        """Export batch results to files."""
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)

        logger.info(f"Exporting batch results to {output_path}")

        # Export combined properties
        if not aggregated_results["combined_properties"].empty:
            combined_csv = output_path / "combined_properties.csv"
            aggregated_results["combined_properties"].to_csv(combined_csv, index=False)
            logger.info(f"✓ Combined properties: {combined_csv}")

        # Export individual search results
        for result in aggregated_results["individual_results"]:
            if result["status"] == "success" and not result["properties"].empty:
                filename = f"{result['search_name']}_properties.csv"
                filepath = output_path / filename
                result["properties"].to_csv(filepath, index=False)
                logger.info(f"✓ Individual result: {filepath}")

        # Export summary report
        summary_report = {
            "batch_summary": {
                k: v
                for k, v in aggregated_results.items()
                if k not in ["combined_properties", "individual_results"]
            },
            "search_results": [
                {
                    "search_name": r["search_name"],
                    "search_url": r["search_url"],
                    "status": r["status"],
                    "property_count": r["property_count"],
                    "matched_count": r["matched_count"],
                    "ai_summary_count": r["ai_summary_count"],
                    "processing_time": r["processing_time"],
                    "error": r["error"],
                }
                for r in aggregated_results["individual_results"]
            ],
        }

        import json

        summary_file = output_path / "batch_summary.json"
        with open(summary_file, "w", encoding="utf-8") as f:
            json.dump(summary_report, f, indent=2, ensure_ascii=False)
        logger.info(f"✓ Summary report: {summary_file}")

    def close(self):
        """Clean up resources."""
        if hasattr(self, "analyzer"):
            self.analyzer.close()


def main():
    """Run batch processing example."""

    # Define multiple searches to process
    search_configs = [
        {
            "name": "palermo_2br",
            "url": "https://www.zonaprop.com.ar/inmuebles-venta-palermo-2-dormitorios-50000-130000-dolar.html",
            "generate_summaries": True,
            "max_summaries": 5,
            "delay_seconds": 5,
        },
        {
            "name": "recoleta_1br",
            "url": "https://www.zonaprop.com.ar/inmuebles-venta-recoleta-1-dormitorio-40000-100000-dolar.html",
            "generate_summaries": True,
            "max_summaries": 5,
            "delay_seconds": 5,
        },
        {
            "name": "belgrano_2br",
            "url": "https://www.zonaprop.com.ar/inmuebles-venta-belgrano-2-dormitorios-60000-140000-dolar.html",
            "generate_summaries": False,  # Skip AI for this search
            "delay_seconds": 5,
        },
    ]

    logger.info("Starting batch processing example")
    logger.info(f"Configured {len(search_configs)} searches")

    processor = None
    try:
        # Initialize batch processor
        processor = BatchProcessor()

        # Process searches (choose sequential or parallel)
        use_parallel = False  # Set to True for parallel processing (higher rate limit risk)

        if use_parallel:
            results = processor.process_batch_parallel(search_configs, max_workers=2)
        else:
            results = processor.process_batch_sequential(search_configs)

        # Aggregate results
        aggregated = processor.aggregate_results(results)

        # Export results
        processor.export_batch_results(aggregated)

        # Show final summary
        logger.info("Batch processing completed successfully!")
        logger.info(f"Check 'batch_results/' directory for exported files")

        if aggregated["errors"]:
            logger.warning("Some searches failed:")
            for error in aggregated["errors"]:
                logger.warning(f"  - {error}")

    except Exception as e:
        logger.error(f"Batch processing failed: {e}")

    finally:
        if processor:
            processor.close()


if __name__ == "__main__":
    main()
