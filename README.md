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
- **Reliable Zonaprop scraping** with Playwright-based Cloudflare bypass (new in v0.2.0).
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

airbnb = analyzer.download_airbnb_data(force=True)
properties = analyzer.scrape_zonaprop(
    "https://www.zonaprop.com.ar/inmuebles-venta-palermo-2-dormitorios-50000-130000-dolar.html"
)
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
