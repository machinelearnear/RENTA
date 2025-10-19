<div align="center">
  <img src="https://raw.githubusercontent.com/machinelearnear/RENTA/main/assets/logo.png" alt="RENTA Logo" width="314">

  # Real Estate Network and Trend Analyzer

  [![PyPI version](https://badge.fury.io/py/renta.svg)](https://badge.fury.io/py/renta)
  [![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
  [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
  [![Documentation](https://img.shields.io/badge/docs-latest-brightgreen.svg)](https://renta.readthedocs.io)
</div>

RENTA is a Python library for real estate investment analysis in Buenos Aires. It combines Airbnb market data, Zonaprop listings, geospatial enrichment, and AWS Bedrock summaries to deliver investment-ready datasets.

## Features

- Download and normalize Airbnb datasets from InsideAirbnb with freshness caching.
- **Multi-provider real estate data** with pluggable architecture supporting Zonaprop and MercadoLibre.
- **Reliable Zonaprop scraping** with Playwright-based Cloudflare bypass (new in v0.2.0).
- **MercadoLibre API integration** for accessing Argentina's largest marketplace (new in v0.3.0).
- Match properties to nearby Airbnb listings with configurable spatial filters.
- Generate Claude Sonnet 4.5 summaries in Argentine Spanish through AWS Bedrock.
- Export enriched results to pandas, CSV, or JSON with consistent schemas.

## Installation

### Environment Setup (Recommended)

For development and testing, it's recommended to use a virtual environment with uv:

```bash
# Install uv if you haven't already
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create a new environment with Python 3.12+
uv venv renta-env --python 3.12

# Activate the environment
source renta-env/bin/activate  # On macOS/Linux
# or
renta-env\Scripts\activate     # On Windows

# Install RENTA in development mode
uv pip install -e .

# Install Playwright browsers (required for Zonaprop scraping)
playwright install chromium

# Or install from PyPI
uv pip install renta
playwright install chromium
```

### Standard Installation

```bash
pip install renta

# Install Playwright browsers (required for Zonaprop scraping)
playwright install chromium
```

> **Note**: RENTA now uses Playwright by default for Zonaprop scraping to reliably bypass Cloudflare protection. This requires ~130MB for Chromium browser installation.

## Quick Start

```python
from renta import RealEstateAnalyzer

analyzer = RealEstateAnalyzer()

# Download Airbnb data
airbnb = analyzer.download_airbnb_data(force=True)

# Fetch properties using the new provider system
properties = analyzer.fetch_properties(
    provider="mercadolibre",
    location="palermo",
    property_type="apartment",
    operation_type="rent",
    max_results=100
)

# Or use Zonaprop (legacy method still works)
properties = analyzer.scrape_zonaprop(
    "https://www.zonaprop.com.ar/inmuebles-venta-palermo-2-dormitorios-50000-130000-dolar.html"
)

# Enrich with spatial matching and AI analysis
enriched = analyzer.enrich_with_airbnb(properties)
summaries = analyzer.generate_summaries(enriched)

analyzer.export(enriched, format="csv", path="investment_analysis.csv")
```

## AWS Bedrock Requirements

Claude Sonnet 4.5 access is required for AI summaries.

```bash
export AWS_ACCESS_KEY_ID="YOUR_KEY"
export AWS_SECRET_ACCESS_KEY="YOUR_SECRET"
export AWS_REGION="us-east-1"
```

Or configure `~/.aws/credentials` or an IAM role. In AWS Console → Amazon Bedrock → Model access, request `us.anthropic.claude-sonnet-4-5-20250929-v1:0`.

## Configuration

Create `config.yaml` to override defaults in `renta/data/default_config.yaml`.

```yaml
data:
  cache_dir: "~/.renta/cache"
  freshness_threshold_hours: 24

# Real Estate Provider Configuration
real_estate:
  default_provider: "zonaprop"  # Options: "zonaprop", "mercadolibre"
  providers:
    mercadolibre:
      rate_limit_seconds: 1.0
      max_retries: 3
      timeout_seconds: 30
      max_results_per_request: 50
      cache_ttl_hours: 24
      defaults:
        country: "AR"
        state: "TUxBUENBUGw3M2E1"  # Capital Federal
    zonaprop:
      rate_limit_seconds: 5.0
      max_retries: 3
      timeout_seconds: 30
      cache_ttl_hours: 24

airbnb:
  matching:
    radius_km: 0.3
    min_nights_threshold: 7
zonaprop:
  scraping:
    use_playwright: true  # Enabled by default for reliable scraping
  playwright:
    headless: false  # Visible browser works better with Cloudflare
    cloudflare_wait_seconds: 10
    page_load_delay_seconds: 3
aws:
  region: "us-east-1"
logging:
  level: "INFO"
```

Load with `RealEstateAnalyzer(config_path="config.yaml")` or set `RENTA_CONFIG=/path/config.yaml`. Configuration is validated against `renta/schemas/config_schema.json`.

## Provider Architecture

RENTA uses a pluggable provider architecture that allows you to fetch real estate data from multiple sources through a unified interface. All providers return data in the same normalized format, making it easy to switch between sources or combine data from multiple platforms.

### Available Providers

#### Zonaprop Provider
- **Source**: Web scraping from Zonaprop.com.ar
- **Method**: Playwright-based browser automation
- **Coverage**: Comprehensive listings across Argentina
- **Reliability**: High (with Cloudflare bypass)
- **Rate Limits**: Configurable delays between requests

#### MercadoLibre Provider  
- **Source**: Official MercadoLibre API
- **Method**: REST API calls
- **Coverage**: Argentina's largest marketplace
- **Reliability**: Very high (official API)
- **Rate Limits**: Built-in respect for API limits

### Using Different Providers

```python
from renta import RealEstateAnalyzer

analyzer = RealEstateAnalyzer()

# Fetch from MercadoLibre (recommended for reliability)
ml_properties = analyzer.fetch_properties(
    provider="mercadolibre",
    location="palermo",
    property_type="apartment",
    operation_type="sale",
    max_results=200
)

# Fetch from Zonaprop
zp_properties = analyzer.fetch_properties(
    provider="zonaprop",
    location="palermo",
    property_type="apartment", 
    operation_type="sale"
)

# Use default provider (configured in config.yaml)
properties = analyzer.fetch_properties(
    location="recoleta",
    property_type="house"
)
```

### Provider-Specific Parameters

Each provider supports common parameters plus provider-specific options:

**Common Parameters:**
- `location`: Neighborhood, city, or area name
- `property_type`: "apartment", "house", "land", "commercial", "office"
- `operation_type`: "sale", "rent", "temporary_rent"
- `max_results`: Maximum number of properties to fetch

**MercadoLibre Specific:**
- `state`: State ID (e.g., "TUxBUENBUGw3M2E1" for Capital Federal)
- `city`: City ID for more precise location filtering
- `price_min`/`price_max`: Price range filters

**Zonaprop Specific:**
- `url`: Direct URL for backward compatibility
- `rooms_min`/`rooms_max`: Room count filters

### Data Schema

All providers return a pandas DataFrame with these standardized columns:

| Column | Type | Description |
|--------|------|-------------|
| `id` | str | Unique property identifier |
| `title` | str | Property title/description |
| `price_usd` | float | Price in USD |
| `price_ars` | float | Price in ARS |
| `address` | str | Property address |
| `latitude` | float | Latitude coordinate |
| `longitude` | float | Longitude coordinate |
| `property_type` | str | Property type (apartment, house, etc.) |
| `operation_type` | str | Operation type (sale, rent, etc.) |
| `rooms` | float | Number of rooms |
| `bathrooms` | float | Number of bathrooms |
| `surface_m2` | float | Surface area in square meters |
| `listing_url` | str | URL to the original listing |
| `source` | str | Provider name (zonaprop, mercadolibre) |

### Adding New Providers

The provider architecture is designed for easy extension. To add a new provider:

1. **Create Provider Class**: Inherit from `BaseRealEstateProvider`
2. **Implement Interface**: Define `fetch_properties()`, `get_provider_name()`, and `validate_filters()`
3. **Register Provider**: Add to `ProviderRegistry` in `renta/providers/registry.py`
4. **Add Configuration**: Include provider settings in default config

Example:

```python
from renta.providers.base import BaseRealEstateProvider
from renta.providers.registry import ProviderRegistry

class MyCustomProvider(BaseRealEstateProvider):
    def fetch_properties(self, **filters):
        # Implement data fetching logic
        return normalized_dataframe
    
    def get_provider_name(self):
        return "mycustom"
    
    def validate_filters(self, **filters):
        # Validate filter parameters
        return validated_filters

# Register the provider
ProviderRegistry.register("mycustom", MyCustomProvider)
```

See `docs/api/providers.md` for detailed API documentation.

### Zonaprop Scraping Methods

RENTA supports two scraping approaches:

1. **Playwright (Default & Recommended)**: Uses browser automation with stealth techniques to bypass Cloudflare. More reliable but slower.
2. **Cloudscraper (Legacy)**: HTTP-based scraping. Faster but often blocked by Cloudflare.

To switch methods:

```yaml
zonaprop:
  scraping:
    use_playwright: false  # Use cloudscraper instead
```

## Troubleshooting

- **Playwright not installed**: Run `playwright install chromium` to install browser.
- **Cloudflare still blocking**: Increase `cloudflare_wait_seconds` in config or ensure `headless: false`.
- **Download issues**: Call `analyzer.download_airbnb_data(force=True)`.
- **Zonaprop blocked with cloudscraper**: Switch to Playwright (`use_playwright: true`) or use `html_path="saved_results.html"`.
- **Bedrock errors**: Verify credentials with `aws sts get-caller-identity` and confirm model access.
- **Schema validation failures**: Run `RealEstateAnalyzer(config_path="config.yaml")` to surface detailed errors.

## Security and Compliance

Logs scrub PII when enabled in config, credentials are never persisted, and scraping obeys configurable rate limits. Review `renta/data/legal_notice.md` and `LEGAL_COMPLIANCE.md` for jurisdiction-specific guidance. Users are responsible for complying with local laws, Zonaprop terms, and AWS policies.

## Documentation and Examples

- API reference and guides: <https://renta.readthedocs.io>
- Example scripts and notebooks: `examples/`
- Default prompts and configuration templates ship with the package.

## Contributing

We welcome pull requests. Install development tooling with:

```bash
pip install -e ".[dev]"
pytest
black . && isort . && flake8
```

See `CONTRIBUTING.md` for workflow details.

## License

MIT License – see `LICENSE`.

---

RENTA supports research and exploratory investment analysis. Always verify property data independently and consult legal counsel when deploying scraping or AI-driven workflows in production.
