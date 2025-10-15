# RealEstateAnalyzer

::: renta.analyzer.RealEstateAnalyzer
    options:
      show_root_heading: true
      show_source: true
      heading_level: 2
      members:
        - __init__
        - download_airbnb_data
        - scrape_zonaprop
        - enrich_with_airbnb
        - generate_summaries
        - export
        - get_operation_stats
        - close

## Usage Examples

### Basic Initialization

```python
from renta import RealEstateAnalyzer

# Initialize with default configuration
analyzer = RealEstateAnalyzer()

# Initialize with custom config file
analyzer = RealEstateAnalyzer(config_path="my_config.yaml")

# Initialize with environment variable
import os
os.environ['RENTA_CONFIG'] = '/path/to/config.yaml'
analyzer = RealEstateAnalyzer()
```

### Data Download and Processing

```python
# Download fresh Airbnb data
airbnb_data = analyzer.download_airbnb_data(force=True)
print(f"Downloaded {len(airbnb_data)} Airbnb listings")

# Use cached data if fresh
airbnb_data = analyzer.download_airbnb_data(force=False)
```

### Property Scraping

```python
# Scrape from web
search_url = "https://www.zonaprop.com.ar/inmuebles-venta-palermo.html"
properties = analyzer.scrape_zonaprop(search_url)

# Use HTML files as fallback
properties = analyzer.scrape_zonaprop(
    search_url=search_url,
    html_path="saved_search_results.html"
)
```

### Enrichment and Analysis

```python
# Enrich properties with Airbnb data
enriched = analyzer.enrich_with_airbnb(properties)

# Generate AI summaries
summaries = analyzer.generate_summaries(enriched)

# Use custom prompt template
summaries = analyzer.generate_summaries(
    enriched, 
    prompt_name="investment_focus"
)
```

### Export Options

```python
# Export as DataFrame (default)
df = analyzer.export(enriched)

# Export as CSV file
csv_path = analyzer.export(enriched, format="csv", path="analysis.csv")

# Export as JSON
json_path = analyzer.export(enriched, format="json", path="analysis.json")

# Export to memory
json_data = analyzer.export(enriched, format="json")
```

### Operation Statistics

```python
# Get operation statistics
stats = analyzer.get_operation_stats()
print(f"Downloads: {stats['downloads']}")
print(f"Scrapes: {stats['scrapes']}")
print(f"Enrichments: {stats['enrichments']}")
print(f"AI Analyses: {stats['ai_analyses']}")
print(f"Exports: {stats['exports']}")
```

### Resource Management

```python
# Always close when done (or use context manager)
analyzer.close()

# Or use as context manager
with RealEstateAnalyzer() as analyzer:
    properties = analyzer.scrape_zonaprop(search_url)
    enriched = analyzer.enrich_with_airbnb(properties)
    # Automatically closed when exiting context
```

## Error Handling

The RealEstateAnalyzer raises specific exceptions for different error conditions:

```python
from renta.exceptions import (
    ConfigurationError,
    AirbnbDataError, 
    ScrapingError,
    MatchingError,
    AIServiceConfigurationError,
    ExportFormatError
)

try:
    analyzer = RealEstateAnalyzer("invalid_config.yaml")
except ConfigurationError as e:
    print(f"Configuration error: {e}")

try:
    airbnb_data = analyzer.download_airbnb_data()
except AirbnbDataError as e:
    print(f"Airbnb data error: {e}")

try:
    properties = analyzer.scrape_zonaprop(search_url)
except ScrapingError as e:
    print(f"Scraping error: {e}")
```

## Performance Considerations

### Memory Management

```python
# For large datasets, process in batches
search_urls = [url1, url2, url3, ...]

all_properties = []
for url in search_urls:
    properties = analyzer.scrape_zonaprop(url)
    enriched = analyzer.enrich_with_airbnb(properties)
    
    # Export immediately to free memory
    analyzer.export(enriched, format="csv", 
                   path=f"batch_{len(all_properties)}.csv")
    
    all_properties.append(enriched)
```

### Caching Strategy

```python
# Download Airbnb data once, reuse for multiple analyses
analyzer.download_airbnb_data(force=True)  # First time

# Subsequent operations use cached data
for search_url in search_urls:
    properties = analyzer.scrape_zonaprop(search_url)
    enriched = analyzer.enrich_with_airbnb(properties)  # Uses cached Airbnb data
```

### Monitoring Operations

```python
import logging

# Enable debug logging for detailed operation info
logging.basicConfig(level=logging.DEBUG)

analyzer = RealEstateAnalyzer()
# Will log detailed progress information
properties = analyzer.scrape_zonaprop(search_url)
```