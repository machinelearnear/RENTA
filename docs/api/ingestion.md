# Data Ingestion

The data ingestion module handles downloading and processing data from multiple sources.

## AirbnbIngester

::: renta.ingestion.AirbnbIngester
    options:
      show_root_heading: true
      show_source: true
      heading_level: 3

### Usage Examples

```python
from renta.ingestion import AirbnbIngester
from renta.config import ConfigManager

config = ConfigManager()
ingester = AirbnbIngester(config)

# Check if data is fresh
if ingester.is_data_fresh():
    print("Data is still fresh, no need to download")
else:
    # Download fresh data
    files = ingester.download_data(force=True)
    print(f"Downloaded files: {list(files.keys())}")
```

## ZonapropScraper

::: renta.ingestion.ZonapropScraper
    options:
      show_root_heading: true
      show_source: true
      heading_level: 3

### Usage Examples

```python
from renta.ingestion import ZonapropScraper
from renta.config import ConfigManager

config = ConfigManager()
scraper = ZonapropScraper(config)

# Scrape from web
search_url = "https://www.zonaprop.com.ar/inmuebles-venta-palermo.html"
try:
    properties = scraper.scrape_search_results(search_url)
    print(f"Scraped {len(properties)} properties")
except ZonapropAntiBotError:
    print("Anti-bot protection detected, use HTML fallback")
    
# Parse saved HTML files
properties = scraper.parse_html_files("saved_search.html")
```

## DataProcessor

::: renta.ingestion.DataProcessor
    options:
      show_root_heading: true
      show_source: true
      heading_level: 3

### Usage Examples

```python
from renta.ingestion import DataProcessor
from renta.config import ConfigManager
import pandas as pd

config = ConfigManager()
processor = DataProcessor(config)

# Process Airbnb data
raw_airbnb = pd.read_csv("raw_airbnb_listings.csv")
processed_airbnb = processor.process_airbnb_listings(raw_airbnb)

# Process Zonaprop data
raw_properties = pd.read_csv("raw_zonaprop_listings.csv")
processed_properties = processor.process_zonaprop_listings(raw_properties)

# Convert currency
usd_prices = processor.convert_currency(
    amounts=processed_properties['price_ars'],
    from_currency='ARS',
    to_currency='USD'
)
```

## Data Schemas

### Airbnb Listing Schema

After processing, Airbnb listings have the following structure:

```python
{
    'id': str,                          # Unique listing ID
    'listing_url': str,                 # Airbnb listing URL
    'latitude': float,                  # Latitude coordinate
    'longitude': float,                 # Longitude coordinate
    'room_type': str,                   # 'Entire home/apt', 'Private room', etc.
    'price_usd_per_night': float,       # Nightly rate in USD
    'beds': Optional[int],              # Number of beds
    'bathrooms': Optional[float],       # Number of bathrooms
    'review_score_rating': Optional[float],     # Overall rating (0-5)
    'review_score_location': Optional[float],   # Location rating (0-5)
    'review_score_value': Optional[float],      # Value rating (0-5)
    'estimated_nights_booked': str,     # 'high', 'medium', 'low'
    'neighbourhood': str,               # Neighborhood name
    'minimum_nights': int,              # Minimum stay requirement
    'availability_365': int,            # Days available per year
    'number_of_reviews': int,           # Total review count
    'last_review': Optional[str],       # Date of last review
}
```

### Property Listing Schema

After processing, property listings have the following structure:

```python
{
    'id': str,                          # Unique property ID
    'title': str,                       # Property title
    'price_ars': Optional[float],       # Price in Argentine Pesos
    'price_usd': Optional[float],       # Price in USD
    'address': str,                     # Property address
    'latitude': float,                  # Latitude coordinate
    'longitude': float,                 # Longitude coordinate
    'rooms': Optional[int],             # Number of rooms
    'bathrooms': Optional[float],       # Number of bathrooms
    'surface_m2': Optional[float],      # Surface area in square meters
    'views_per_day': Optional[int],     # Daily view count on Zonaprop
    'listing_url': str,                 # Zonaprop listing URL
    'property_type': Optional[str],     # 'Apartment', 'House', etc.
    'expenses_ars': Optional[float],    # Monthly expenses in ARS
    'age_years': Optional[int],         # Property age in years
    'floor': Optional[int],             # Floor number
    'total_floors': Optional[int],      # Total floors in building
    'parking': Optional[bool],          # Has parking space
    'balcony': Optional[bool],          # Has balcony
    'terrace': Optional[bool],          # Has terrace
}
```

## Error Handling

The ingestion module defines specific exceptions:

```python
from renta.exceptions import (
    AirbnbDataError,
    ScrapingError,
    ZonapropAntiBotError
)

# Handle Airbnb data errors
try:
    files = ingester.download_data()
except AirbnbDataError as e:
    print(f"Failed to download Airbnb data: {e}")

# Handle scraping errors
try:
    properties = scraper.scrape_search_results(url)
except ZonapropAntiBotError as e:
    print(f"Anti-bot protection detected: {e}")
    # Use HTML fallback
    properties = scraper.parse_html_files("fallback.html")
except ScrapingError as e:
    print(f"General scraping error: {e}")
```

## Configuration Options

### Airbnb Ingestion Configuration

```yaml
data:
  cache_dir: "~/.renta/cache"
  freshness_threshold_hours: 24

exchange_rates:
  provider: "xe.com"
  cache_ttl_hours: 24
  fallback_rate: 1000
```

### Zonaprop Scraping Configuration

```yaml
zonaprop:
  scraping:
    rate_limit_seconds: 5
    max_retries: 3
    timeout_seconds: 30
    user_agents:
      - "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
      - "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
```

### Data Processing Configuration

```yaml
data:
  processing:
    validate_coordinates: true
    require_price: true
    min_surface_m2: 10
    max_surface_m2: 1000
```

## Best Practices

### Rate Limiting

```python
import time

# Respect rate limits when scraping multiple URLs
urls = [url1, url2, url3, ...]
properties = []

for url in urls:
    try:
        props = scraper.scrape_search_results(url)
        properties.extend(props)
        
        # Rate limiting (configured in config.yaml)
        time.sleep(scraper.config.get('zonaprop.scraping.rate_limit_seconds', 5))
        
    except ZonapropAntiBotError:
        print(f"Blocked on {url}, switching to HTML fallback")
        # Handle with saved HTML files
```

### Data Validation

```python
# Validate data after processing
def validate_airbnb_data(df):
    required_columns = ['id', 'latitude', 'longitude', 'price_usd_per_night']
    missing_columns = [col for col in required_columns if col not in df.columns]
    
    if missing_columns:
        raise ValueError(f"Missing required columns: {missing_columns}")
    
    # Check for valid coordinates
    invalid_coords = df[
        (df['latitude'].abs() > 90) | 
        (df['longitude'].abs() > 180)
    ]
    
    if len(invalid_coords) > 0:
        print(f"Warning: {len(invalid_coords)} listings have invalid coordinates")

# Use validation
processed_data = processor.process_airbnb_listings(raw_data)
validate_airbnb_data(processed_data)
```

### Memory Management

```python
# Process large datasets in chunks
def process_large_dataset(file_path, chunk_size=1000):
    processed_chunks = []
    
    for chunk in pd.read_csv(file_path, chunksize=chunk_size):
        processed_chunk = processor.process_airbnb_listings(chunk)
        processed_chunks.append(processed_chunk)
    
    return pd.concat(processed_chunks, ignore_index=True)

# Use for large files
large_dataset = process_large_dataset("huge_airbnb_file.csv")
```