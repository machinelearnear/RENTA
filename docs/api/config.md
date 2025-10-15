# Configuration Management

::: renta.config.ConfigManager
    options:
      show_root_heading: true
      show_source: true
      heading_level: 2

## Configuration Structure

RENTA uses YAML configuration files with the following structure:

```yaml
# Data storage and caching
data:
  cache_dir: "~/.renta/cache"
  export_dir: "~/.renta/exports"
  freshness_threshold_hours: 24

# Airbnb data processing and matching
airbnb:
  matching:
    radius_km: 0.3
    min_nights_threshold: 7
    min_review_score: 4.0
    occupancy_thresholds:
      high: 14  # nights per month
      medium: 7

# Zonaprop scraping configuration
zonaprop:
  scraping:
    rate_limit_seconds: 5
    max_retries: 3
    user_agents:
      - "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    timeout_seconds: 30

# Exchange rate providers
exchange_rates:
  provider: "xe.com"
  cache_ttl_hours: 24
  fallback_rate: 1000  # ARS per USD

# AWS Bedrock configuration
aws:
  region: "us-east-1"
  bedrock:
    model_id: "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
    max_tokens: 1024
    temperature: 0.7
    max_retries: 3

# AI prompt templates
prompts:
  default: "prompts/investment_summary.yaml"
  custom_templates:
    investment_focus: |
      Analyze this property for investment potential...

# Network configuration
network:
  max_retries: 3
  timeout_seconds: 30
  backoff_factor: 0.3
  user_agent: "RENTA/1.0.0"

# Logging configuration
logging:
  level: "INFO"
  format: "json"  # or "console"

# Debug settings
debug:
  enable_request_logging: false
  keep_intermediates: false
  keep_partial: false
```

## Configuration Discovery

RENTA discovers configuration files in the following order:

1. **Explicit path**: Passed to `RealEstateAnalyzer(config_path="...")`
2. **Environment variable**: `RENTA_CONFIG` environment variable
3. **Current directory**: `config.yaml` in current working directory
4. **Default configuration**: Embedded default configuration

```python
# Method 1: Explicit path
analyzer = RealEstateAnalyzer(config_path="/path/to/config.yaml")

# Method 2: Environment variable
import os
os.environ['RENTA_CONFIG'] = '/path/to/config.yaml'
analyzer = RealEstateAnalyzer()

# Method 3: Current directory
# Place config.yaml in current directory
analyzer = RealEstateAnalyzer()

# Method 4: Default configuration only
analyzer = RealEstateAnalyzer()  # Uses embedded defaults
```

## Configuration Validation

RENTA validates configuration against a JSON schema:

```python
from renta.config import ConfigManager

try:
    config = ConfigManager("config.yaml")
    print("Configuration is valid")
except ConfigurationError as e:
    print(f"Configuration error: {e}")
    # Error message includes specific validation failures
```

## Accessing Configuration Values

```python
# Dot notation access
config = ConfigManager()

# Simple values
cache_dir = config.get('data.cache_dir')
model_id = config.get('aws.bedrock.model_id')

# With defaults
timeout = config.get('network.timeout_seconds', 30)

# Complex nested values
occupancy_thresholds = config.get('airbnb.matching.occupancy_thresholds')
high_threshold = occupancy_thresholds['high']

# Direct dictionary access
config_dict = config.to_dict()
```

## Configuration Merging

User configuration is merged with default configuration:

```yaml
# Default configuration (embedded)
aws:
  region: "us-east-1"
  bedrock:
    model_id: "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
    max_tokens: 1024
    temperature: 0.7

# User configuration (config.yaml)
aws:
  region: "us-west-2"  # Override region
  bedrock:
    temperature: 0.5   # Override temperature
    # model_id and max_tokens inherited from defaults

# Final merged configuration
aws:
  region: "us-west-2"
  bedrock:
    model_id: "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
    max_tokens: 1024
    temperature: 0.5
```

## Environment-Specific Configuration

```yaml
# Development configuration
logging:
  level: "DEBUG"
  format: "console"

debug:
  enable_request_logging: true
  keep_intermediates: true

aws:
  bedrock:
    dry_run: true  # Don't make actual API calls

# Production configuration  
logging:
  level: "INFO"
  format: "json"

debug:
  enable_request_logging: false
  keep_intermediates: false

aws:
  bedrock:
    dry_run: false
```

## Dynamic Configuration Updates

```python
# Update configuration at runtime
config = ConfigManager()

# Update single value
config.set('logging.level', 'DEBUG')

# Update nested values
config.set('aws.bedrock.temperature', 0.8)

# Validate after updates
config.validate_schema()
```

## Configuration Examples

### Minimal Configuration

```yaml
# Minimal config - uses defaults for everything else
aws:
  region: "us-west-2"
```

### Performance-Optimized Configuration

```yaml
# Optimized for performance
airbnb:
  matching:
    radius_km: 0.2  # Smaller radius for faster matching

network:
  max_retries: 1  # Fewer retries
  timeout_seconds: 15  # Shorter timeout

aws:
  bedrock:
    model_id: "us.anthropic.claude-3-5-haiku-20241022-v1:0"  # Faster model

logging:
  level: "WARNING"  # Less logging overhead
```

### Development Configuration

```yaml
# Development-friendly settings
logging:
  level: "DEBUG"
  format: "console"

debug:
  enable_request_logging: true
  keep_intermediates: true
  keep_partial: true

aws:
  bedrock:
    dry_run: true  # Don't make API calls during development

zonaprop:
  scraping:
    rate_limit_seconds: 10  # More conservative rate limiting
```

### High-Volume Configuration

```yaml
# Configuration for processing many properties
data:
  cache_dir: "/tmp/renta_cache"  # Fast storage
  freshness_threshold_hours: 168  # Weekly refresh

airbnb:
  matching:
    radius_km: 0.5  # Larger radius for more matches

network:
  max_retries: 5
  timeout_seconds: 60

aws:
  bedrock:
    max_tokens: 2048  # Longer summaries
    temperature: 0.3  # More consistent output
```