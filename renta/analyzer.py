"""
Main RealEstateAnalyzer class - entry point for RENTA functionality.

Provides the main interface for real estate investment analysis combining
Airbnb data, Zonaprop listings, spatial matching, and AI-powered summaries.
"""

import logging
import time
import random
import functools
from contextlib import contextmanager
from typing import Optional, List, Dict, Union, Any, Callable, Type
import pandas as pd
import structlog
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import ConfigManager
from .exceptions import (
    RentaError,
    ConfigurationError,
    AirbnbDataError,
    ScrapingError,
    MatchingError,
    AIServiceConfigurationError,
    ExportFormatError
)
from .ingestion import AirbnbIngester, ZonapropScraper, DataProcessor
from .spatial import SpatialMatcher, EnrichmentEngine
from .ai import AIAnalyzer
from .export import ExportManager
from .security import SecurityManager
from .utils.retry import RetryConfig, with_retry

logger = structlog.get_logger(__name__)


class NetworkSession:
    """Enhanced requests session with retry logic and monitoring."""
    
    def __init__(self, config: ConfigManager, logger_instance: Optional[structlog.BoundLogger] = None):
        self.config = config
        self.logger = logger_instance or logger
        self.session = requests.Session()
        
        # Configure retry strategy
        retry_strategy = Retry(
            total=config.get('network.max_retries', 3),
            backoff_factor=config.get('network.backoff_factor', 0.3),
            status_forcelist=[429, 500, 502, 503, 504],
            respect_retry_after_header=True
        )
        
        # Mount adapter with retry strategy
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # Set default timeout
        self.default_timeout = config.get('network.timeout_seconds', 30)
        
        # Configure headers
        self.session.headers.update({
            'User-Agent': config.get('network.user_agent', 'RENTA/1.0.0'),
        })
    
    def get(self, url: str, **kwargs) -> requests.Response:
        """Enhanced GET request with logging and error handling."""
        kwargs.setdefault('timeout', self.default_timeout)
        
        self.logger.debug("Making HTTP GET request", url=url, timeout=kwargs.get('timeout'))
        
        try:
            response = self.session.get(url, **kwargs)
            response.raise_for_status()
            
            self.logger.debug(
                "HTTP GET request successful",
                url=url,
                status_code=response.status_code,
                response_size=len(response.content)
            )
            
            return response
            
        except requests.exceptions.RequestException as e:
            self.logger.error(
                "HTTP GET request failed",
                url=url,
                error=str(e),
                error_type=type(e).__name__
            )
            raise
    
    def close(self):
        """Close the session."""
        self.session.close()


class ErrorContext:
    """Context manager for enhanced error handling with automatic logging."""
    
    def __init__(
        self,
        operation_name: str,
        logger_instance: structlog.BoundLogger,
        reraise_as: Optional[Type[Exception]] = None,
        **context
    ):
        self.operation_name = operation_name
        self.logger = logger_instance
        self.reraise_as = reraise_as
        self.context = context
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            error_details = {
                "operation": self.operation_name,
                "error": str(exc_val),
                "error_type": exc_type.__name__,
                **self.context
            }
            
            # Add traceback in debug mode
            if self.logger._context.get('debug_mode', False):
                import traceback
                error_details['traceback'] = traceback.format_exc()
            
            self.logger.error(f"Error in {self.operation_name}", **error_details)
            
            # Optionally reraise as different exception type
            if self.reraise_as and not isinstance(exc_val, self.reraise_as):
                raise self.reraise_as(
                    f"Error in {self.operation_name}: {exc_val}",
                    details=error_details
                ) from exc_val
        
        return False  # Don't suppress exceptions


class OperationTimer:
    """Context manager for timing operations with automatic logging."""
    
    def __init__(self, operation_name: str, logger: structlog.BoundLogger, **context):
        self.operation_name = operation_name
        self.logger = logger
        self.context = context
        self.start_time = None
        self.end_time = None
    
    def __enter__(self):
        self.start_time = time.time()
        self.logger.info(f"Starting {self.operation_name}", **self.context)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.time()
        duration = self.end_time - self.start_time
        
        if exc_type is None:
            self.logger.info(
                f"Completed {self.operation_name}",
                duration_seconds=round(duration, 3),
                **self.context
            )
        else:
            self.logger.error(
                f"Failed {self.operation_name}",
                duration_seconds=round(duration, 3),
                error_type=exc_type.__name__ if exc_type else None,
                error=str(exc_val) if exc_val else None,
                **self.context
            )
    
    def get_duration(self) -> Optional[float]:
        """Get operation duration if completed."""
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return None


class ProgressTracker:
    """Tracks progress of operations with periodic logging."""
    
    def __init__(self, total_items: int, operation_name: str, logger: structlog.BoundLogger, log_interval: int = 10):
        self.total_items = total_items
        self.operation_name = operation_name
        self.logger = logger
        self.log_interval = log_interval
        self.processed_items = 0
        self.start_time = time.time()
        self.last_log_time = self.start_time
    
    def update(self, increment: int = 1) -> None:
        """Update progress and log if interval reached."""
        self.processed_items += increment
        current_time = time.time()
        
        # Log at intervals or when complete
        if (current_time - self.last_log_time >= self.log_interval or 
            self.processed_items >= self.total_items):
            
            elapsed = current_time - self.start_time
            progress_pct = (self.processed_items / self.total_items) * 100
            rate = self.processed_items / elapsed if elapsed > 0 else 0
            
            self.logger.info(
                f"Progress: {self.operation_name}",
                processed=self.processed_items,
                total=self.total_items,
                progress_percent=round(progress_pct, 1),
                rate_per_second=round(rate, 2),
                elapsed_seconds=round(elapsed, 1)
            )
            
            self.last_log_time = current_time


def configure_logging(config: ConfigManager) -> None:
    """Configure structured logging based on configuration.
    
    Args:
        config: Configuration manager with logging settings
    """
    # Get logging configuration
    log_level = config.get('logging.level', 'INFO').upper()
    log_format = config.get('logging.format', 'json')
    
    # Configure structlog
    processors = [
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    
    if log_format.lower() == 'json':
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer(colors=True))
    
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    # Configure standard library logging
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format='%(message)s'
    )
    
    # Set third-party library log levels
    logging.getLogger('boto3').setLevel(logging.WARNING)
    logging.getLogger('botocore').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('requests').setLevel(logging.WARNING)


class RealEstateAnalyzer:
    """Main entry point for RENTA functionality.
    
    Provides a unified interface for real estate investment analysis by orchestrating
    data ingestion, spatial matching, AI analysis, and export operations.
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """Initialize analyzer with configuration loading.
        
        Args:
            config_path: Optional path to configuration file. If None, will discover
                        via RENTA_CONFIG env var or current directory.
                        
        Raises:
            ConfigurationError: If configuration loading or validation fails
        """
        with OperationTimer("RealEstateAnalyzer initialization", logger, config_path=config_path):
            try:
                # Load and validate configuration
                self.config = ConfigManager(config_path)
                
                # Configure logging based on config
                configure_logging(self.config)
                
                # Create bound logger with context
                self.logger = logger.bind(
                    component="RealEstateAnalyzer",
                    debug_mode=self.config.get('debug.enable_request_logging', False)
                )
                
                # Initialize retry configuration
                self.retry_config = RetryConfig(
                    max_attempts=self.config.get('network.max_retries', 3),
                    base_delay=self.config.get('network.base_delay', 1.0),
                    max_delay=self.config.get('network.max_delay', 60.0),
                    exponential_base=self.config.get('network.exponential_base', 2.0),
                    jitter=self.config.get('network.jitter', True)
                )
                
                # Initialize network session
                self.network_session = NetworkSession(self.config, self.logger)
                
                # Initialize security manager first
                self.security_manager = SecurityManager(self.config)
                
                # Initialize secure environment and validate credentials
                security_init = self.security_manager.initialize_secure_environment()
                
                if not security_init['credentials_valid']:
                    self.logger.warning(
                        "AWS credentials validation failed - AI features may not work",
                        warnings=security_init['security_warnings']
                    )
                
                if security_init['security_warnings']:
                    self.logger.warning(
                        "Security warnings detected",
                        warnings=security_init['security_warnings']
                    )
                
                # Initialize components with progress tracking
                components = [
                    ("AirbnbIngester", lambda: AirbnbIngester(self.config)),
                    ("ZonapropScraper", lambda: ZonapropScraper(self.config)),
                    ("DataProcessor", lambda: DataProcessor(self.config)),
                    ("SpatialMatcher", lambda: SpatialMatcher(self.config)),
                    ("EnrichmentEngine", lambda: EnrichmentEngine(self.config)),
                    ("AIAnalyzer", lambda: AIAnalyzer(self.config, self.security_manager)),
                    ("ExportManager", lambda: ExportManager(self.config)),
                ]
                
                progress = ProgressTracker(len(components), "component initialization", self.logger, log_interval=2)
                
                for name, factory in components:
                    self.logger.debug(f"Initializing {name}")
                    component = factory()
                    setattr(self, f"_{name.lower()}", component)
                    progress.update()
                
                # State management
                self._airbnb_data: Optional[pd.DataFrame] = None
                self._last_airbnb_download: Optional[float] = None
                self._operation_stats = {
                    'downloads': 0,
                    'scrapes': 0,
                    'enrichments': 0,
                    'ai_analyses': 0,
                    'exports': 0
                }
                
                self.logger.info(
                    "RealEstateAnalyzer initialized successfully",
                    components_loaded=len(components),
                    config_keys=list(self.config.to_dict().keys()),
                    debug_mode=self.config.get('debug.enable_request_logging', False)
                )
                
            except Exception as e:
                self.logger.error("Failed to initialize RealEstateAnalyzer", error=str(e))
                if isinstance(e, (ConfigurationError, RentaError)):
                    raise
                raise ConfigurationError(
                    f"Unexpected error during initialization: {e}",
                    details={"error_type": type(e).__name__}
                )
    
    @with_retry()
    def download_airbnb_data(self, force: bool = False) -> pd.DataFrame:
        """Download and process Airbnb data.
        
        Args:
            force: Force re-download even if data is fresh
            
        Returns:
            Processed Airbnb data as DataFrame
            
        Raises:
            AirbnbDataError: If download or processing fails
        """
        with OperationTimer("Airbnb data download", self.logger, force=force) as timer:
            with ErrorContext("Airbnb data download", self.logger, reraise_as=AirbnbDataError, force=force):
                # Check if we have fresh cached data and force is not set
                if not force and self._airbnb_data is not None and self._airbnb_ingester.is_data_fresh():
                    self.logger.info("Using cached Airbnb data (still fresh)")
                    return self._airbnb_data.copy()
                
                # Download raw data files with retry logic
                downloaded_files = self._download_with_retry(force)
                self.logger.info("Airbnb files downloaded", files=list(downloaded_files.keys()))
                
                # Process the data
                processed_data = self._data_processor.process_airbnb_data(downloaded_files)
                
                # Validate processed data
                self._validate_airbnb_data(processed_data)
                
                # Cache the processed data
                self._airbnb_data = processed_data
                self._last_airbnb_download = time.time()
                self._operation_stats['downloads'] += 1
                
                self.logger.info(
                    "Airbnb data download completed",
                    rows=len(processed_data),
                    columns=len(processed_data.columns),
                    memory_usage_mb=round(processed_data.memory_usage(deep=True).sum() / 1024 / 1024, 2),
                    total_downloads=self._operation_stats['downloads']
                )
                
                return processed_data.copy()
    
    @with_retry()
    def scrape_zonaprop(self, search_url: str, *, html_path: Optional[str] = None) -> pd.DataFrame:
        """Scrape Zonaprop listings.
        
        Args:
            search_url: Zonaprop search URL to scrape
            html_path: Optional path to saved HTML files as fallback
            
        Returns:
            Property listings as DataFrame
            
        Raises:
            ScrapingError: If scraping fails
            ZonapropAntiBotError: If anti-bot protection is detected
        """
        with OperationTimer("Zonaprop scraping", self.logger, url=search_url, html_path=html_path) as timer:
            with ErrorContext("Zonaprop scraping", self.logger, reraise_as=ScrapingError, 
                            url=search_url, html_path=html_path):
                if html_path:
                    # Use HTML files as fallback
                    self.logger.info("Using HTML files for parsing", path=html_path)
                    properties_df = self._zonaprop_scraper.parse_html_files(html_path)
                else:
                    # Scrape from web with enhanced error handling
                    properties_df = self._scrape_with_retry(search_url)
                
                # Process and normalize the data
                processed_properties = self._data_processor.process_zonaprop_data(properties_df)
                
                # Validate scraped data
                self._validate_property_data(processed_properties)
                
                self._operation_stats['scrapes'] += 1
                
                self.logger.info(
                    "Zonaprop scraping completed",
                    properties=len(processed_properties),
                    columns=len(processed_properties.columns),
                    memory_usage_mb=round(processed_properties.memory_usage(deep=True).sum() / 1024 / 1024, 2),
                    total_scrapes=self._operation_stats['scrapes']
                )
                
                return processed_properties
    
    def enrich_with_airbnb(self, properties_df: pd.DataFrame) -> pd.DataFrame:
        """Enrich properties with Airbnb data.
        
        Args:
            properties_df: DataFrame of property listings
            
        Returns:
            Enriched properties DataFrame with Airbnb metrics
            
        Raises:
            MatchingError: If spatial matching fails
            AirbnbDataError: If Airbnb data is not available
        """
        with OperationTimer("property enrichment", self.logger, properties=len(properties_df)) as timer:
            with ErrorContext("property enrichment", self.logger, reraise_as=MatchingError, 
                            properties_count=len(properties_df)):
                # Validate input data
                self._validate_property_data(properties_df)
                
                # Ensure we have Airbnb data
                if self._airbnb_data is None:
                    self.logger.info("No cached Airbnb data, downloading...")
                    self.download_airbnb_data()
                
                # Perform spatial matching with progress tracking and error handling
                progress = ProgressTracker(len(properties_df), "spatial matching", self.logger)
                try:
                    matches_df = self._spatial_matcher.match_properties(properties_df, self._airbnb_data)
                    progress.update(len(properties_df))
                except Exception as e:
                    self.logger.error("Spatial matching failed", error=str(e))
                    raise MatchingError(f"Spatial matching failed: {e}") from e
                
                self.logger.info("Spatial matching completed", matches=len(matches_df))
                
                # Enrich properties with aggregated metrics
                try:
                    enriched_properties = self._enrichment_engine.enrich_properties(properties_df, matches_df)
                except Exception as e:
                    self.logger.error("Property enrichment failed", error=str(e))
                    raise MatchingError(f"Property enrichment failed: {e}") from e
                
                # Validate enriched data
                self._validate_enriched_data(enriched_properties)
                
                self._operation_stats['enrichments'] += 1
                
                # Log enrichment statistics
                matched_count = len(enriched_properties[enriched_properties['match_status'] == 'matched'])
                match_rate = matched_count / len(enriched_properties) * 100 if len(enriched_properties) > 0 else 0
                
                self.logger.info(
                    "Property enrichment completed",
                    total_properties=len(enriched_properties),
                    matched_properties=matched_count,
                    match_rate=round(match_rate, 1),
                    airbnb_listings_used=len(self._airbnb_data),
                    total_enrichments=self._operation_stats['enrichments']
                )
                
                return enriched_properties
    
    def generate_summaries(self, enriched_properties: pd.DataFrame, *, prompt_name: str = "default") -> List[Dict]:
        """Generate AI summaries.
        
        Args:
            enriched_properties: DataFrame with enriched property data
            prompt_name: Name of prompt template to use
            
        Returns:
            List of dictionaries with property_id, summary, and confidence
            
        Raises:
            AIServiceConfigurationError: If AI service fails
            ConfigurationError: If prompt template is invalid
        """
        with OperationTimer("AI summary generation", self.logger, 
                          properties=len(enriched_properties), prompt_name=prompt_name) as timer:
            try:
                # Track progress for AI analysis
                progress = ProgressTracker(len(enriched_properties), "AI analysis", self.logger, log_interval=5)
                
                summaries = self._ai_analyzer.analyze_properties(enriched_properties, prompt_name)
                progress.update(len(enriched_properties))
                
                self._operation_stats['ai_analyses'] += 1
                
                # Log summary statistics
                successful_summaries = len([s for s in summaries if s['confidence'] > 0])
                avg_confidence = sum(s['confidence'] for s in summaries) / len(summaries) if summaries else 0
                confidence_distribution = self._calculate_confidence_distribution(summaries)
                
                self.logger.info(
                    "AI summary generation completed",
                    total_summaries=len(summaries),
                    successful_summaries=successful_summaries,
                    success_rate=round(successful_summaries / len(summaries) * 100, 1) if summaries else 0,
                    average_confidence=round(avg_confidence, 3),
                    confidence_distribution=confidence_distribution,
                    total_ai_analyses=self._operation_stats['ai_analyses']
                )
                
                return summaries
                
            except Exception as e:
                self.logger.error(
                    "AI summary generation failed",
                    error=str(e),
                    properties=len(enriched_properties),
                    prompt_name=prompt_name
                )
                if isinstance(e, (AIServiceConfigurationError, ConfigurationError, RentaError)):
                    raise
                raise AIServiceConfigurationError(
                    f"Unexpected error during AI summary generation: {e}",
                    details={"error_type": type(e).__name__, "prompt_name": prompt_name}
                )
    
    def export(self, results: pd.DataFrame, format: str = "dataframe", path: Optional[str] = None) -> Union[pd.DataFrame, str]:
        """Export results in specified format.
        
        Args:
            results: DataFrame to export
            format: Export format ('dataframe', 'csv', 'json')
            path: Optional file path for export
            
        Returns:
            DataFrame if format is 'dataframe', file path or data otherwise
            
        Raises:
            ExportFormatError: If export fails
        """
        with OperationTimer("data export", self.logger, 
                          format=format, path=path, rows=len(results), columns=len(results.columns)) as timer:
            try:
                exported_result = self._export_manager.export(results, format, path)
                self._operation_stats['exports'] += 1
                
                # Calculate file size if exported to file
                file_size_mb = None
                if isinstance(exported_result, str) and path:
                    try:
                        import os
                        file_size_mb = round(os.path.getsize(exported_result) / 1024 / 1024, 2)
                    except:
                        pass
                
                self.logger.info(
                    "Data export completed",
                    format=format,
                    result_type=type(exported_result).__name__,
                    file_size_mb=file_size_mb,
                    total_exports=self._operation_stats['exports']
                )
                
                return exported_result
                
            except Exception as e:
                self.logger.error("Data export failed", error=str(e), format=format, path=path)
                if isinstance(e, ExportFormatError):
                    raise
                raise ExportFormatError(
                    f"Unexpected error during export: {e}",
                    details={"error_type": type(e).__name__, "format": format}
                )
    
    # Method chaining support
    def with_airbnb_data(self, force: bool = False) -> 'RealEstateAnalyzer':
        """Download Airbnb data and return self for method chaining.
        
        Args:
            force: Force re-download even if data is fresh
            
        Returns:
            Self for method chaining
        """
        self.download_airbnb_data(force=force)
        return self
    
    def with_properties(self, search_url: str, *, html_path: Optional[str] = None) -> pd.DataFrame:
        """Scrape properties and return DataFrame for chaining.
        
        Args:
            search_url: Zonaprop search URL
            html_path: Optional path to saved HTML files
            
        Returns:
            Properties DataFrame
        """
        return self.scrape_zonaprop(search_url, html_path=html_path)
    
    # State management and utility methods
    def get_config(self) -> ConfigManager:
        """Get configuration manager instance.
        
        Returns:
            ConfigManager instance
        """
        return self.config
    
    def get_cached_airbnb_data(self) -> Optional[pd.DataFrame]:
        """Get cached Airbnb data if available.
        
        Returns:
            Cached Airbnb DataFrame or None if not available
        """
        return self._airbnb_data.copy() if self._airbnb_data is not None else None
    
    def clear_cache(self) -> None:
        """Clear cached data to free memory."""
        logger.info("Clearing cached data")
        self._airbnb_data = None
        self._last_airbnb_download = None
    
    def get_status(self) -> Dict[str, Any]:
        """Get analyzer status and statistics.
        
        Returns:
            Dictionary with status information
        """
        return {
            "config_loaded": self.config is not None,
            "airbnb_data_cached": self._airbnb_data is not None,
            "airbnb_data_rows": len(self._airbnb_data) if self._airbnb_data is not None else 0,
            "airbnb_data_memory_mb": round(self._airbnb_data.memory_usage(deep=True).sum() / 1024 / 1024, 2) if self._airbnb_data is not None else 0,
            "last_airbnb_download": self._last_airbnb_download,
            "airbnb_data_fresh": self._airbnb_ingester.is_data_fresh() if self._airbnb_data is not None else False,
            "supported_export_formats": self._export_manager.list_supported_formats(),
            "available_prompts": self._ai_analyzer.prompt_manager.list_available_prompts(),
            "operation_stats": self._operation_stats.copy(),
            "debug_mode": self.config.get('debug.enable_request_logging', False),
            "log_level": self.config.get('logging.level', 'INFO')
        }
    
    def _calculate_confidence_distribution(self, summaries: List[Dict]) -> Dict[str, int]:
        """Calculate confidence score distribution for logging.
        
        Args:
            summaries: List of summary dictionaries with confidence scores
            
        Returns:
            Dictionary with confidence ranges and counts
        """
        distribution = {
            "high (0.8-1.0)": 0,
            "medium (0.5-0.8)": 0,
            "low (0.0-0.5)": 0
        }
        
        for summary in summaries:
            confidence = summary.get('confidence', 0)
            if confidence >= 0.8:
                distribution["high (0.8-1.0)"] += 1
            elif confidence >= 0.5:
                distribution["medium (0.5-0.8)"] += 1
            else:
                distribution["low (0.0-0.5)"] += 1
        
        return distribution
    
    @contextmanager
    def debug_mode(self):
        """Context manager to temporarily enable debug logging.
        
        Usage:
            with analyzer.debug_mode():
                analyzer.download_airbnb_data()
        """
        original_level = self.config.get('logging.level', 'INFO')
        self.config.set('logging.level', 'DEBUG')
        self.config.set('debug.enable_request_logging', True)
        
        # Reconfigure logging
        configure_logging(self.config)
        self.logger.info("Debug mode enabled")
        
        try:
            yield
        finally:
            # Restore original settings
            self.config.set('logging.level', original_level)
            self.config.set('debug.enable_request_logging', False)
            configure_logging(self.config)
            self.logger.info("Debug mode disabled")
    
    # Helper methods for retry logic and validation
    
    def _download_with_retry(self, force: bool = False) -> Dict[str, str]:
        """Download Airbnb data with retry logic.
        
        Args:
            force: Force re-download even if data is fresh
            
        Returns:
            Dictionary mapping file type to local file path
            
        Raises:
            AirbnbDataError: If download fails after all retries
        """
        @with_retry(self.retry_config, logger_instance=self.logger)
        def _download():
            return self._airbnb_ingester.download_data(force=force)
        
        return _download()
    
    def _scrape_with_retry(self, search_url: str) -> pd.DataFrame:
        """Scrape Zonaprop with retry logic.
        
        Args:
            search_url: URL to scrape
            
        Returns:
            DataFrame of scraped properties
            
        Raises:
            ScrapingError: If scraping fails after all retries
        """
        @with_retry(self.retry_config, logger_instance=self.logger)
        def _scrape():
            return self._zonaprop_scraper.scrape_search_results(search_url)
        
        return _scrape()
    
    def _validate_airbnb_data(self, data: pd.DataFrame) -> None:
        """Validate Airbnb data integrity.
        
        Args:
            data: Airbnb DataFrame to validate
            
        Raises:
            AirbnbDataError: If data validation fails
        """
        if data is None or data.empty:
            raise AirbnbDataError("Airbnb data is empty or None")
        
        required_columns = ['id', 'latitude', 'longitude', 'price']
        missing_columns = [col for col in required_columns if col not in data.columns]
        if missing_columns:
            raise AirbnbDataError(
                f"Airbnb data missing required columns: {missing_columns}",
                details={"missing_columns": missing_columns, "available_columns": list(data.columns)}
            )
        
        # Check for reasonable data ranges
        if data['latitude'].isna().all() or data['longitude'].isna().all():
            raise AirbnbDataError("Airbnb data has no valid coordinates")
        
        # Check coordinate ranges for Buenos Aires
        lat_range = (-35.0, -34.0)  # Approximate Buenos Aires latitude range
        lon_range = (-59.0, -58.0)  # Approximate Buenos Aires longitude range
        
        valid_coords = (
            data['latitude'].between(lat_range[0], lat_range[1]) &
            data['longitude'].between(lon_range[0], lon_range[1])
        )
        
        if not valid_coords.any():
            self.logger.warning(
                "No Airbnb listings found within Buenos Aires coordinate range",
                lat_range=lat_range,
                lon_range=lon_range
            )
    
    def _validate_property_data(self, data: pd.DataFrame) -> None:
        """Validate property data integrity.
        
        Args:
            data: Property DataFrame to validate
            
        Raises:
            ScrapingError: If data validation fails
        """
        if data is None or data.empty:
            raise ScrapingError("Property data is empty or None")
        
        required_columns = ['id', 'title']
        missing_columns = [col for col in required_columns if col not in data.columns]
        if missing_columns:
            raise ScrapingError(
                f"Property data missing required columns: {missing_columns}",
                details={"missing_columns": missing_columns, "available_columns": list(data.columns)}
            )
        
        # Check for duplicate IDs
        if data['id'].duplicated().any():
            duplicate_count = data['id'].duplicated().sum()
            self.logger.warning(
                "Property data contains duplicate IDs",
                duplicate_count=duplicate_count,
                total_properties=len(data)
            )
    
    def _validate_enriched_data(self, data: pd.DataFrame) -> None:
        """Validate enriched property data.
        
        Args:
            data: Enriched property DataFrame to validate
            
        Raises:
            MatchingError: If enriched data validation fails
        """
        if data is None or data.empty:
            raise MatchingError("Enriched data is empty or None")
        
        # Check that match_status column exists
        if 'match_status' not in data.columns:
            raise MatchingError("Enriched data missing match_status column")
        
        # Validate match status values
        valid_statuses = ['matched', 'no_matches', 'error']
        invalid_statuses = data[~data['match_status'].isin(valid_statuses)]['match_status'].unique()
        if len(invalid_statuses) > 0:
            self.logger.warning(
                "Enriched data contains invalid match statuses",
                invalid_statuses=list(invalid_statuses),
                valid_statuses=valid_statuses
            )
    
    def _handle_network_error(self, error: Exception, operation: str, **context) -> None:
        """Handle network-related errors with appropriate logging and context.
        
        Args:
            error: The network error that occurred
            operation: Name of the operation that failed
            **context: Additional context for logging
        """
        error_details = {
            "operation": operation,
            "error_type": type(error).__name__,
            "error": str(error),
            **context
        }
        
        if isinstance(error, requests.exceptions.ConnectionError):
            self.logger.error("Network connection error", **error_details)
        elif isinstance(error, requests.exceptions.Timeout):
            self.logger.error("Network timeout error", **error_details)
        elif isinstance(error, requests.exceptions.HTTPError):
            if hasattr(error, 'response') and error.response is not None:
                error_details.update({
                    "status_code": error.response.status_code,
                    "response_headers": dict(error.response.headers)
                })
            self.logger.error("HTTP error", **error_details)
        else:
            self.logger.error("Unexpected network error", **error_details)
    
    def __del__(self):
        """Cleanup resources when analyzer is destroyed."""
        try:
            if hasattr(self, 'network_session'):
                self.network_session.close()
        except:
            pass  # Ignore cleanup errors