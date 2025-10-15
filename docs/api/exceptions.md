# Exception Handling

RENTA defines a comprehensive exception hierarchy for different error conditions.

## Exception Hierarchy

::: renta.exceptions
    options:
      show_root_heading: true
      show_source: true
      heading_level: 3

## Base Exception

### RentaError

All RENTA exceptions inherit from `RentaError`:

```python
from renta.exceptions import RentaError

try:
    # Any RENTA operation
    analyzer = RealEstateAnalyzer()
    properties = analyzer.scrape_zonaprop(url)
except RentaError as e:
    print(f"RENTA error occurred: {e}")
    
    # Access error details if available
    if hasattr(e, 'details'):
        print(f"Error details: {e.details}")
```

## Configuration Errors

### ConfigurationError

Raised when configuration loading or validation fails:

```python
from renta.exceptions import ConfigurationError

try:
    analyzer = RealEstateAnalyzer(config_path="invalid_config.yaml")
except ConfigurationError as e:
    print(f"Configuration error: {e}")
    
    # Common causes:
    # - Invalid YAML syntax
    # - Schema validation failure
    # - Missing required configuration keys
    # - Invalid configuration values
```

**Common scenarios:**

```python
# Invalid YAML syntax
"""
aws:
  region: us-east-1
    bedrock:  # Incorrect indentation
      model_id: claude-3
"""

# Schema validation failure
"""
aws:
  region: "invalid-region"  # Not a valid AWS region
  bedrock:
    temperature: 2.0  # Outside valid range (0-1)
"""

# Missing required keys
"""
# Missing aws.bedrock.model_id
aws:
  region: "us-east-1"
  bedrock:
    temperature: 0.7
"""
```

## Data Ingestion Errors

### AirbnbDataError

Raised when Airbnb data download or processing fails:

```python
from renta.exceptions import AirbnbDataError

try:
    airbnb_data = analyzer.download_airbnb_data()
except AirbnbDataError as e:
    print(f"Airbnb data error: {e}")
    
    # Common causes:
    # - Network connectivity issues
    # - InsideAirbnb website changes
    # - Exchange rate API failures
    # - Data processing errors
    # - Insufficient disk space
```

**Error handling strategies:**

```python
def robust_airbnb_download(analyzer, max_retries=3):
    """Download Airbnb data with retry logic."""
    for attempt in range(max_retries):
        try:
            return analyzer.download_airbnb_data()
        except AirbnbDataError as e:
            if "network" in str(e).lower() and attempt < max_retries - 1:
                print(f"Network error, retrying in {2**attempt} seconds...")
                time.sleep(2**attempt)
                continue
            else:
                raise
    
    raise AirbnbDataError("Failed after all retry attempts")
```

### ScrapingError

Base class for web scraping errors:

```python
from renta.exceptions import ScrapingError

try:
    properties = analyzer.scrape_zonaprop(search_url)
except ScrapingError as e:
    print(f"Scraping error: {e}")
    
    # Handle with fallback methods
    print("Trying HTML file fallback...")
    properties = analyzer.scrape_zonaprop(
        search_url, 
        html_path="saved_search.html"
    )
```

### ZonapropAntiBotError

Specific error for anti-bot protection detection:

```python
from renta.exceptions import ZonapropAntiBotError

try:
    properties = analyzer.scrape_zonaprop(search_url)
except ZonapropAntiBotError as e:
    print(f"Anti-bot protection detected: {e}")
    
    # Recommended fallback strategies
    print("Recommended actions:")
    print("1. Save search results manually as HTML")
    print("2. Use HTML file parsing: scrape_zonaprop(url, html_path='file.html')")
    print("3. Wait and try again later")
    print("4. Consider using a scraping service")
    
    # Try HTML fallback if available
    html_files = glob.glob("*.html")
    if html_files:
        print(f"Found HTML files: {html_files}")
        properties = analyzer.scrape_zonaprop(search_url, html_path=html_files[0])
```

## Spatial Analysis Errors

### MatchingError

Raised when spatial matching or enrichment fails:

```python
from renta.exceptions import MatchingError

try:
    enriched = analyzer.enrich_with_airbnb(properties)
except MatchingError as e:
    print(f"Matching error: {e}")
    
    # Common causes:
    # - Invalid coordinate data
    # - No Airbnb data available
    # - Spatial indexing failures
    # - Memory issues with large datasets
```

**Debugging matching errors:**

```python
def debug_matching_error(properties, airbnb_data):
    """Debug spatial matching issues."""
    print("Debugging spatial matching...")
    
    # Check coordinate validity
    invalid_props = properties[
        (properties['latitude'].abs() > 90) | 
        (properties['longitude'].abs() > 180) |
        properties['latitude'].isna() |
        properties['longitude'].isna()
    ]
    
    if len(invalid_props) > 0:
        print(f"Found {len(invalid_props)} properties with invalid coordinates")
        return properties.drop(invalid_props.index)
    
    # Check Airbnb data
    if airbnb_data is None or len(airbnb_data) == 0:
        print("No Airbnb data available for matching")
        return None
    
    print(f"Properties: {len(properties)}, Airbnb listings: {len(airbnb_data)}")
    return properties

# Use debugging
try:
    enriched = analyzer.enrich_with_airbnb(properties)
except MatchingError as e:
    print(f"Matching failed: {e}")
    cleaned_properties = debug_matching_error(properties, analyzer._airbnb_data)
    if cleaned_properties is not None:
        enriched = analyzer.enrich_with_airbnb(cleaned_properties)
```

## AI Service Errors

### AIServiceConfigurationError

Raised when AWS Bedrock integration fails:

```python
from renta.exceptions import AIServiceConfigurationError

try:
    summaries = analyzer.generate_summaries(enriched_properties)
except AIServiceConfigurationError as e:
    print(f"AI service error: {e}")
    
    # Check specific error types
    error_str = str(e).lower()
    
    if "accessdenied" in error_str:
        print("AWS access denied - check credentials and permissions")
        print("1. Verify AWS credentials: aws sts get-caller-identity")
        print("2. Check Bedrock model access in AWS Console")
        
    elif "throttling" in error_str:
        print("Rate limit exceeded - reduce batch size or add delays")
        
    elif "validation" in error_str:
        print("Invalid request parameters - check model ID and settings")
        
    elif "region" in error_str:
        print("Region error - check AWS region configuration")
```

**AWS troubleshooting guide:**

```python
def diagnose_aws_issues(config):
    """Diagnose AWS configuration issues."""
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError
    
    print("Diagnosing AWS configuration...")
    
    # Check credentials
    try:
        sts = boto3.client('sts')
        identity = sts.get_caller_identity()
        print(f"✓ AWS credentials valid: {identity['Arn']}")
    except NoCredentialsError:
        print("✗ No AWS credentials found")
        print("  Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY")
        return False
    except ClientError as e:
        print(f"✗ AWS credentials error: {e}")
        return False
    
    # Check Bedrock access
    try:
        bedrock = boto3.client('bedrock', region_name=config.get('aws.region'))
        models = bedrock.list_foundation_models()
        print(f"✓ Bedrock access confirmed: {len(models['modelSummaries'])} models available")
    except ClientError as e:
        print(f"✗ Bedrock access error: {e}")
        if "AccessDenied" in str(e):
            print("  Enable Bedrock model access in AWS Console")
        return False
    
    # Check specific model access
    model_id = config.get('aws.bedrock.model_id')
    try:
        bedrock_runtime = boto3.client('bedrock-runtime', region_name=config.get('aws.region'))
        # This will fail if model access is not enabled
        print(f"✓ Model {model_id} access confirmed")
    except ClientError as e:
        print(f"✗ Model access error: {e}")
        print(f"  Enable access to {model_id} in AWS Console")
        return False
    
    return True

# Use diagnostics
if not diagnose_aws_issues(analyzer.config):
    print("Fix AWS configuration before proceeding")
```

## Export Errors

### ExportFormatError

Raised when data export fails:

```python
from renta.exceptions import ExportFormatError

try:
    result = analyzer.export(data, format="csv", path="results.csv")
except ExportFormatError as e:
    print(f"Export error: {e}")
    
    # Try alternative approaches
    try:
        # Try different format
        result = analyzer.export(data, format="json")
        print(f"JSON export successful: {result}")
    except ExportFormatError:
        # Try in-memory export
        df_result = analyzer.export(data, format="dataframe")
        print(f"In-memory export successful: {len(df_result)} rows")
```

## Error Context and Details

Many RENTA exceptions include additional context:

```python
try:
    analyzer = RealEstateAnalyzer("config.yaml")
except ConfigurationError as e:
    print(f"Error: {e}")
    
    # Access additional details
    if hasattr(e, 'details'):
        details = e.details
        print(f"Error type: {details.get('error_type')}")
        print(f"Config file: {details.get('config_path')}")
        print(f"Validation errors: {details.get('validation_errors')}")
```

## Best Practices

### Comprehensive Error Handling

```python
from renta.exceptions import *
import logging

def robust_analysis_pipeline(search_url, config_path=None):
    """Robust analysis pipeline with comprehensive error handling."""
    
    try:
        # Initialize analyzer
        analyzer = RealEstateAnalyzer(config_path)
        
    except ConfigurationError as e:
        logging.error(f"Configuration error: {e}")
        # Use default configuration
        analyzer = RealEstateAnalyzer()
    
    try:
        # Download Airbnb data
        airbnb_data = analyzer.download_airbnb_data()
        
    except AirbnbDataError as e:
        logging.warning(f"Airbnb download failed: {e}")
        # Continue without fresh data
        airbnb_data = None
    
    try:
        # Scrape properties
        properties = analyzer.scrape_zonaprop(search_url)
        
    except ZonapropAntiBotError as e:
        logging.error(f"Anti-bot protection: {e}")
        raise  # Cannot continue without property data
        
    except ScrapingError as e:
        logging.error(f"Scraping failed: {e}")
        raise
    
    try:
        # Enrich with Airbnb data
        if airbnb_data is not None:
            enriched = analyzer.enrich_with_airbnb(properties)
        else:
            enriched = properties  # Use properties without enrichment
            
    except MatchingError as e:
        logging.warning(f"Enrichment failed: {e}")
        enriched = properties  # Fallback to non-enriched data
    
    try:
        # Generate AI summaries
        summaries = analyzer.generate_summaries(enriched)
        
    except AIServiceConfigurationError as e:
        logging.warning(f"AI analysis failed: {e}")
        summaries = []  # Continue without AI summaries
    
    try:
        # Export results
        result_path = analyzer.export(enriched, format="csv")
        logging.info(f"Analysis complete: {result_path}")
        return result_path
        
    except ExportFormatError as e:
        logging.error(f"Export failed: {e}")
        # Return in-memory result
        return analyzer.export(enriched, format="dataframe")

# Use robust pipeline
try:
    result = robust_analysis_pipeline("https://www.zonaprop.com.ar/...")
    print(f"Analysis successful: {result}")
except Exception as e:
    print(f"Analysis failed completely: {e}")
```

### Logging Integration

```python
import logging
import structlog

# Configure logging to capture RENTA errors
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# RENTA uses structlog internally
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.JSONRenderer()
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    logger_factory=structlog.stdlib.LoggerFactory(),
)

# Errors are automatically logged with context
try:
    analyzer = RealEstateAnalyzer()
    properties = analyzer.scrape_zonaprop(url)
except ScrapingError as e:
    # Error details are already logged by RENTA
    # Additional handling here
    pass
```

### Custom Error Handling

```python
class CustomRentaHandler:
    """Custom error handler for RENTA operations."""
    
    def __init__(self, notification_callback=None):
        self.notification_callback = notification_callback
        self.error_counts = {}
    
    def handle_error(self, error, operation, **context):
        """Handle RENTA errors with custom logic."""
        error_type = type(error).__name__
        self.error_counts[error_type] = self.error_counts.get(error_type, 0) + 1
        
        # Log error with context
        logging.error(
            f"RENTA error in {operation}",
            extra={
                'error_type': error_type,
                'error_message': str(error),
                'operation': operation,
                'context': context,
                'error_count': self.error_counts[error_type]
            }
        )
        
        # Send notification for critical errors
        if self.notification_callback and error_type in ['ConfigurationError', 'AIServiceConfigurationError']:
            self.notification_callback(f"Critical RENTA error: {error}")
        
        # Decide whether to retry or fail
        if error_type == 'ZonapropAntiBotError':
            return 'fail'  # Cannot retry anti-bot errors
        elif self.error_counts[error_type] < 3:
            return 'retry'  # Retry up to 3 times
        else:
            return 'fail'  # Give up after 3 attempts

# Use custom handler
def send_notification(message):
    print(f"NOTIFICATION: {message}")

handler = CustomRentaHandler(notification_callback=send_notification)

try:
    analyzer = RealEstateAnalyzer()
except ConfigurationError as e:
    action = handler.handle_error(e, 'initialization')
    if action == 'fail':
        raise
```