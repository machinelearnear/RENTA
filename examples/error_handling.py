#!/usr/bin/env python3
"""
Error Handling Example

This script demonstrates comprehensive error handling patterns for RENTA,
including recovery strategies, fallback mechanisms, and robust pipeline design.
"""

import os
import sys
import logging
import time
import pandas as pd
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
from contextlib import contextmanager

# Add RENTA to path if running from source
sys.path.insert(0, str(Path(__file__).parent.parent))

from renta import RealEstateAnalyzer
from renta.exceptions import *

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ErrorHandler:
    """Comprehensive error handler for RENTA operations."""
    
    def __init__(self):
        self.error_counts = {}
        self.recovery_strategies = {}
        self.fallback_data = {}
        
        # Register recovery strategies
        self._register_recovery_strategies()
    
    def _register_recovery_strategies(self):
        """Register recovery strategies for different error types."""
        
        self.recovery_strategies = {
            ConfigurationError: self._handle_config_error,
            AirbnbDataError: self._handle_airbnb_error,
            ZonapropAntiBotError: self._handle_antibot_error,
            ScrapingError: self._handle_scraping_error,
            MatchingError: self._handle_matching_error,
            AIServiceConfigurationError: self._handle_ai_error,
            ExportFormatError: self._handle_export_error
        }
    
    def handle_error(self, error: Exception, operation: str, **context) -> Dict[str, Any]:
        """Handle error with appropriate recovery strategy."""
        error_type = type(error)
        self.error_counts[error_type] = self.error_counts.get(error_type, 0) + 1
        
        logger.error(f"Error in {operation}: {error}")
        
        # Try recovery strategy
        if error_type in self.recovery_strategies:
            return self.recovery_strategies[error_type](error, operation, **context)
        else:
            return self._handle_generic_error(error, operation, **context)
    
    def _handle_config_error(self, error: ConfigurationError, operation: str, **context) -> Dict[str, Any]:
        """Handle configuration errors."""
        logger.info("Attempting configuration error recovery...")
        
        recovery_actions = []
        
        # Try default configuration
        try:
            from renta.config import ConfigManager
            config = ConfigManager()  # Use defaults
            recovery_actions.append("Used default configuration")
            
            return {
                'recovered': True,
                'strategy': 'default_config',
                'actions': recovery_actions,
                'fallback_data': {'config': config}
            }
            
        except Exception as e:
            recovery_actions.append(f"Default config failed: {e}")
            
            return {
                'recovered': False,
                'strategy': 'config_recovery',
                'actions': recovery_actions,
                'recommendation': 'Check configuration file syntax and required fields'
            }
    
    def _handle_airbnb_error(self, error: AirbnbDataError, operation: str, **context) -> Dict[str, Any]:
        """Handle Airbnb data errors."""
        logger.info("Attempting Airbnb data error recovery...")
        
        recovery_actions = []
        
        # Check if we have cached data
        cache_dir = Path("~/.renta/cache").expanduser()
        cached_files = list(cache_dir.glob("*airbnb*.csv")) if cache_dir.exists() else []
        
        if cached_files:
            try:
                # Use most recent cached file
                latest_file = max(cached_files, key=lambda f: f.stat().st_mtime)
                cached_data = pd.read_csv(latest_file)
                
                recovery_actions.append(f"Used cached data from {latest_file}")
                
                return {
                    'recovered': True,
                    'strategy': 'cached_data',
                    'actions': recovery_actions,
                    'fallback_data': {'airbnb_data': cached_data}
                }
                
            except Exception as e:
                recovery_actions.append(f"Cached data failed: {e}")
        
        # Create minimal sample data for testing
        sample_data = pd.DataFrame({
            'id': ['airbnb_1', 'airbnb_2', 'airbnb_3'],
            'latitude': [-34.6037, -34.6118, -34.5895],
            'longitude': [-58.3816, -58.3960, -58.3974],
            'price_usd_per_night': [45, 60, 35],
            'room_type': ['Entire home/apt', 'Private room', 'Entire home/apt'],
            'review_score_rating': [4.5, 4.2, 4.8],
            'estimated_nights_booked': ['high', 'medium', 'high']
        })
        
        recovery_actions.append("Created sample Airbnb data for testing")
        
        return {
            'recovered': True,
            'strategy': 'sample_data',
            'actions': recovery_actions,
            'fallback_data': {'airbnb_data': sample_data},
            'warning': 'Using sample data - results may not be accurate'
        }
    
    def _handle_antibot_error(self, error: ZonapropAntiBotError, operation: str, **context) -> Dict[str, Any]:
        """Handle anti-bot protection errors."""
        logger.info("Handling anti-bot protection...")
        
        recovery_actions = []
        
        # Check for HTML files in current directory
        html_files = list(Path(".").glob("*.html"))
        
        if html_files:
            recovery_actions.append(f"Found {len(html_files)} HTML files for fallback")
            
            return {
                'recovered': True,
                'strategy': 'html_fallback',
                'actions': recovery_actions,
                'fallback_data': {'html_files': html_files},
                'recommendation': f'Use HTML fallback: scrape_zonaprop(url, html_path="{html_files[0]}")'
            }
        
        # Create sample property data
        sample_properties = pd.DataFrame({
            'id': ['prop_1', 'prop_2', 'prop_3'],
            'title': ['2 ambientes en Palermo', 'Depto 2 amb con balcón', 'Palermo Hollywood 2 amb'],
            'price_usd': [95000, 110000, 85000],
            'surface_m2': [45, 52, 40],
            'rooms': [2, 2, 2],
            'bathrooms': [1, 1, 1],
            'latitude': [-34.5875, -34.5901, -34.5823],
            'longitude': [-58.4050, -58.4123, -58.4089],
            'views_per_day': [66, 45, 78],
            'address': ['Av. Santa Fe 3500', 'Thames 1200', 'Av. Córdoba 5800']
        })
        
        recovery_actions.append("Created sample property data")
        
        return {
            'recovered': True,
            'strategy': 'sample_properties',
            'actions': recovery_actions,
            'fallback_data': {'properties': sample_properties},
            'warning': 'Using sample data - save HTML files manually for real data'
        }
    
    def _handle_scraping_error(self, error: ScrapingError, operation: str, **context) -> Dict[str, Any]:
        """Handle general scraping errors."""
        logger.info("Attempting scraping error recovery...")
        
        recovery_actions = []
        
        # If it's a timeout, suggest retry with longer timeout
        if "timeout" in str(error).lower():
            recovery_actions.append("Timeout detected - recommend retry with longer timeout")
            
            return {
                'recovered': False,
                'strategy': 'timeout_retry',
                'actions': recovery_actions,
                'recommendation': 'Increase timeout_seconds in configuration and retry'
            }
        
        # For other scraping errors, fall back to sample data
        return self._handle_antibot_error(error, operation, **context)
    
    def _handle_matching_error(self, error: MatchingError, operation: str, **context) -> Dict[str, Any]:
        """Handle spatial matching errors."""
        logger.info("Attempting matching error recovery...")
        
        recovery_actions = []
        
        # Try with relaxed matching criteria
        recovery_actions.append("Attempting recovery with relaxed matching criteria")
        
        return {
            'recovered': False,
            'strategy': 'relaxed_matching',
            'actions': recovery_actions,
            'recommendation': 'Increase matching radius or reduce quality thresholds'
        }
    
    def _handle_ai_error(self, error: AIServiceConfigurationError, operation: str, **context) -> Dict[str, Any]:
        """Handle AI service errors."""
        logger.info("Attempting AI service error recovery...")
        
        recovery_actions = []
        error_str = str(error).lower()
        
        if "accessdenied" in error_str:
            recovery_actions.append("AWS access denied - check credentials and permissions")
            recommendation = "1. Verify AWS credentials\n2. Check Bedrock model access in AWS Console"
            
        elif "throttling" in error_str:
            recovery_actions.append("Rate limit exceeded - implement backoff")
            recommendation = "Reduce batch size or add delays between requests"
            
        elif "validation" in error_str:
            recovery_actions.append("Invalid request parameters")
            recommendation = "Check model ID and request parameters"
            
        else:
            recovery_actions.append("Generic AI service error")
            recommendation = "Check AWS configuration and service status"
        
        # Create mock summaries for testing
        mock_summaries = [
            {
                'property_id': 'mock_1',
                'summary': 'Mock AI summary - AI service unavailable',
                'confidence': 0.0
            }
        ]
        
        recovery_actions.append("Created mock AI summaries")
        
        return {
            'recovered': True,
            'strategy': 'mock_summaries',
            'actions': recovery_actions,
            'fallback_data': {'summaries': mock_summaries},
            'recommendation': recommendation,
            'warning': 'Using mock summaries - fix AI configuration for real analysis'
        }
    
    def _handle_export_error(self, error: ExportFormatError, operation: str, **context) -> Dict[str, Any]:
        """Handle export errors."""
        logger.info("Attempting export error recovery...")
        
        recovery_actions = []
        
        # Try alternative export format
        recovery_actions.append("Attempting alternative export format")
        
        return {
            'recovered': False,
            'strategy': 'alternative_format',
            'actions': recovery_actions,
            'recommendation': 'Try different export format (CSV, JSON, or in-memory DataFrame)'
        }
    
    def _handle_generic_error(self, error: Exception, operation: str, **context) -> Dict[str, Any]:
        """Handle generic errors."""
        logger.info(f"Handling generic error: {type(error).__name__}")
        
        return {
            'recovered': False,
            'strategy': 'generic',
            'actions': [f"Logged {type(error).__name__} error"],
            'recommendation': 'Check logs for details and consider manual intervention'
        }


@contextmanager
def error_recovery_context(handler: ErrorHandler, operation: str, **context):
    """Context manager for error recovery."""
    try:
        yield
    except Exception as e:
        recovery_result = handler.handle_error(e, operation, **context)
        
        if recovery_result['recovered']:
            logger.info(f"Recovery successful: {recovery_result['strategy']}")
            if 'warning' in recovery_result:
                logger.warning(recovery_result['warning'])
        else:
            logger.error(f"Recovery failed: {recovery_result.get('recommendation', 'No recommendation')}")
            raise


class RobustRentaPipeline:
    """Robust RENTA pipeline with comprehensive error handling."""
    
    def __init__(self, config_path: Optional[str] = None):
        self.error_handler = ErrorHandler()
        self.analyzer = None
        self.fallback_data = {}
        
        # Initialize analyzer with error handling
        with error_recovery_context(self.error_handler, "initialization"):
            self.analyzer = RealEstateAnalyzer(config_path)
    
    def run_analysis(self, search_url: str) -> Dict[str, Any]:
        """Run complete analysis with error handling."""
        results = {
            'success': False,
            'data': {},
            'errors': [],
            'warnings': [],
            'recovery_actions': []
        }
        
        try:
            # Step 1: Download Airbnb data
            airbnb_data = self._download_airbnb_with_recovery()
            results['data']['airbnb_data'] = airbnb_data
            
            # Step 2: Scrape properties
            properties = self._scrape_properties_with_recovery(search_url)
            results['data']['properties'] = properties
            
            # Step 3: Enrich properties
            enriched_properties = self._enrich_properties_with_recovery(properties, airbnb_data)
            results['data']['enriched_properties'] = enriched_properties
            
            # Step 4: Generate AI summaries
            summaries = self._generate_summaries_with_recovery(enriched_properties)
            results['data']['summaries'] = summaries
            
            # Step 5: Export results
            export_paths = self._export_results_with_recovery(enriched_properties)
            results['data']['export_paths'] = export_paths
            
            results['success'] = True
            logger.info("Analysis completed successfully with error recovery")
            
        except Exception as e:
            logger.error(f"Analysis failed completely: {e}")
            results['errors'].append(str(e))
        
        return results
    
    def _download_airbnb_with_recovery(self) -> pd.DataFrame:
        """Download Airbnb data with error recovery."""
        try:
            return self.analyzer.download_airbnb_data()
        except AirbnbDataError as e:
            recovery_result = self.error_handler.handle_error(e, "airbnb_download")
            if recovery_result['recovered']:
                return recovery_result['fallback_data']['airbnb_data']
            raise
    
    def _scrape_properties_with_recovery(self, search_url: str) -> pd.DataFrame:
        """Scrape properties with error recovery."""
        try:
            return self.analyzer.scrape_zonaprop(search_url)
        except (ZonapropAntiBotError, ScrapingError) as e:
            recovery_result = self.error_handler.handle_error(e, "property_scraping", url=search_url)
            if recovery_result['recovered']:
                if 'html_files' in recovery_result['fallback_data']:
                    # Try HTML fallback
                    html_file = recovery_result['fallback_data']['html_files'][0]
                    return self.analyzer.scrape_zonaprop(search_url, html_path=str(html_file))
                else:
                    return recovery_result['fallback_data']['properties']
            raise
    
    def _enrich_properties_with_recovery(self, properties: pd.DataFrame, airbnb_data: pd.DataFrame) -> pd.DataFrame:
        """Enrich properties with error recovery."""
        try:
            return self.analyzer.enrich_with_airbnb(properties)
        except MatchingError as e:
            recovery_result = self.error_handler.handle_error(e, "property_enrichment")
            logger.warning("Enrichment failed, returning non-enriched properties")
            return properties
    
    def _generate_summaries_with_recovery(self, properties: pd.DataFrame) -> List[Dict]:
        """Generate AI summaries with error recovery."""
        try:
            return self.analyzer.generate_summaries(properties.head(3))  # Limit for demo
        except AIServiceConfigurationError as e:
            recovery_result = self.error_handler.handle_error(e, "ai_analysis")
            if recovery_result['recovered']:
                return recovery_result['fallback_data']['summaries']
            return []
    
    def _export_results_with_recovery(self, data: pd.DataFrame) -> Dict[str, str]:
        """Export results with error recovery."""
        export_paths = {}
        
        # Try CSV export
        try:
            csv_path = self.analyzer.export(data, format="csv")
            export_paths['csv'] = csv_path
        except ExportFormatError as e:
            logger.warning(f"CSV export failed: {e}")
        
        # Try JSON export
        try:
            json_path = self.analyzer.export(data, format="json")
            export_paths['json'] = json_path
        except ExportFormatError as e:
            logger.warning(f"JSON export failed: {e}")
        
        # Fallback to in-memory
        if not export_paths:
            try:
                df_result = self.analyzer.export(data, format="dataframe")
                export_paths['dataframe'] = f"In-memory DataFrame ({len(df_result)} rows)"
            except Exception as e:
                logger.error(f"All export methods failed: {e}")
        
        return export_paths
    
    def close(self):
        """Clean up resources."""
        if self.analyzer:
            self.analyzer.close()


def demonstrate_error_scenarios():
    """Demonstrate various error scenarios and recovery."""
    
    logger.info("Demonstrating error handling scenarios...")
    
    scenarios = [
        {
            'name': 'Invalid Configuration',
            'test': lambda: RealEstateAnalyzer(config_path="nonexistent_config.yaml")
        },
        {
            'name': 'Network Timeout',
            'test': lambda: simulate_network_error()
        },
        {
            'name': 'Anti-bot Protection',
            'test': lambda: simulate_antibot_error()
        },
        {
            'name': 'AWS Credentials Missing',
            'test': lambda: simulate_aws_error()
        }
    ]
    
    handler = ErrorHandler()
    
    for scenario in scenarios:
        logger.info(f"\n--- Testing: {scenario['name']} ---")
        
        try:
            scenario['test']()
            logger.info("✓ No error occurred")
        except Exception as e:
            recovery_result = handler.handle_error(e, scenario['name'])
            
            if recovery_result['recovered']:
                logger.info(f"✓ Recovery successful: {recovery_result['strategy']}")
                for action in recovery_result['actions']:
                    logger.info(f"  - {action}")
            else:
                logger.warning(f"⚠ Recovery failed: {recovery_result.get('recommendation', 'No recommendation')}")


def simulate_network_error():
    """Simulate network timeout error."""
    import requests
    raise requests.exceptions.Timeout("Connection timed out")


def simulate_antibot_error():
    """Simulate anti-bot protection error."""
    raise ZonapropAntiBotError("Cloudflare protection detected")


def simulate_aws_error():
    """Simulate AWS credentials error."""
    raise AIServiceConfigurationError("AccessDeniedException: User not authorized")


def main():
    """Run error handling demonstration."""
    
    print("RENTA Error Handling Example")
    print("============================")
    print()
    print("Choose an option:")
    print("1. Run robust analysis pipeline")
    print("2. Demonstrate error scenarios")
    print("3. Test specific error recovery")
    print("4. Exit")
    
    choice = input("\nEnter choice (1-4): ").strip()
    
    if choice == "1":
        search_url = "https://www.zonaprop.com.ar/inmuebles-venta-palermo-2-dormitorios.html"
        
        logger.info("Running robust analysis pipeline...")
        pipeline = RobustRentaPipeline()
        
        try:
            results = pipeline.run_analysis(search_url)
            
            if results['success']:
                logger.info("✓ Pipeline completed successfully")
                print(f"\nResults summary:")
                for key, value in results['data'].items():
                    if isinstance(value, pd.DataFrame):
                        print(f"  {key}: {len(value)} rows")
                    elif isinstance(value, list):
                        print(f"  {key}: {len(value)} items")
                    else:
                        print(f"  {key}: {value}")
            else:
                logger.error("❌ Pipeline failed")
                for error in results['errors']:
                    print(f"  Error: {error}")
                    
        finally:
            pipeline.close()
    
    elif choice == "2":
        demonstrate_error_scenarios()
    
    elif choice == "3":
        print("\nAvailable error types:")
        print("- config: Configuration errors")
        print("- airbnb: Airbnb data errors")
        print("- antibot: Anti-bot protection")
        print("- ai: AI service errors")
        
        error_type = input("\nEnter error type: ").strip()
        
        handler = ErrorHandler()
        
        if error_type == "config":
            try:
                raise ConfigurationError("Invalid configuration file")
            except Exception as e:
                result = handler.handle_error(e, "test")
                print(f"Recovery result: {result}")
                
        elif error_type == "antibot":
            try:
                raise ZonapropAntiBotError("Cloudflare protection")
            except Exception as e:
                result = handler.handle_error(e, "test")
                print(f"Recovery result: {result}")
                
        # Add more test cases as needed
        
    elif choice == "4":
        print("Goodbye!")
        
    else:
        print("Invalid choice")


if __name__ == "__main__":
    main()