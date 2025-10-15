# RENTA - Real Estate Network and Trend Analyzer

[![PyPI version](https://badge.fury.io/py/renta.svg)](https://badge.fury.io/py/renta)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Documentation](https://img.shields.io/badge/docs-latest-brightgreen.svg)](https://renta.readthedocs.io)

A comprehensive Python library for real estate investment analysis in Buenos Aires, Argentina. RENTA combines property listings from Zonaprop, rental market data from Airbnb, and AI-powered analysis to provide intelligent investment insights.

## 🏠 What RENTA Does

RENTA provides a complete data pipeline for real estate investment analysis:

1. **📊 Data Integration**: Downloads and processes Airbnb rental data from InsideAirbnb
2. **🏘️ Property Scraping**: Extracts property listings from Zonaprop with engagement metrics
3. **🗺️ Spatial Matching**: Matches properties with nearby Airbnb listings using geospatial algorithms
4. **🤖 AI Analysis**: Generates investment summaries in Argentinian Spanish using AWS Bedrock
5. **📈 Export & Analysis**: Exports results in multiple formats (CSV, JSON, DataFrame)

## 🚀 Quick Start

### Installation

```bash
pip install renta
```

### Basic Usage

```python
from renta import RealEstateAnalyzer

# Initialize analyzer (loads default configuration)
analyzer = RealEstateAnalyzer()

# Download and process Airbnb data (first run only)
airbnb_data = analyzer.download_airbnb_data(force=True)

# Scrape Zonaprop listings
search_url = "https://www.zonaprop.com.ar/inmuebles-venta-palermo-2-dormitorios-50000-130000-dolar.html"
properties = analyzer.scrape_zonaprop(search_url)

# Enrich properties with Airbnb rental data
enriched_properties = analyzer.enrich_with_airbnb(properties)

# Generate AI-powered investment summaries
summaries = analyzer.generate_summaries(enriched_properties)

# Export results
analyzer.export(enriched_properties, format="csv", path="investment_analysis.csv")
```

### AWS Setup

RENTA requires AWS Bedrock for AI analysis. Set up your credentials:

```bash
# Method 1: Environment variables
export AWS_ACCESS_KEY_ID="your_access_key"
export AWS_SECRET_ACCESS_KEY="your_secret_key"
export AWS_REGION="us-east-1"

# Method 2: AWS credentials file (~/.aws/credentials)
[default]
aws_access_key_id = your_access_key
aws_secret_access_key = your_secret_key
region = us-east-1

# Method 3: IAM Role (recommended for production)
# No configuration needed - uses instance role automatically
```

**Enable Bedrock Model Access:**
1. Go to AWS Console → Amazon Bedrock → Model access
2. Request access to Claude Sonnet 4.5: `us.anthropic.claude-sonnet-4-5-20250929-v1:0`
3. Wait for approval (usually instant)

## 📋 Configuration

RENTA uses YAML configuration files for customization. Create a `config.yaml` file:

```yaml
# Basic configuration example
data:
  cache_dir: "~/.renta/cache"
  export_dir: "~/.renta/exports"
  freshness_threshold_hours: 24

airbnb:
  matching:
    radius_km: 0.3
    min_nights_threshold: 7
    min_review_score: 4.0

aws:
  region: "us-east-1"
  bedrock:
    model_id: "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
    max_tokens: 1024
    temperature: 0.7

logging:
  level: "INFO"
  format: "json"
```

Load custom configuration:

```python
# Load from specific path
analyzer = RealEstateAnalyzer(config_path="my_config.yaml")

# Or set via environment variable
import os
os.environ['RENTA_CONFIG'] = '/path/to/config.yaml'
analyzer = RealEstateAnalyzer()
```

## 🔧 Advanced Usage

### Custom Matching Strategies

```python
from renta.matching import SpatialMatchingStrategy

# Create custom matching strategy
class CustomStrategy(SpatialMatchingStrategy):
    def match_properties(self, properties, airbnb_listings):
        # Your custom matching logic
        return super().match_properties(properties, airbnb_listings)

# Register and use
analyzer.register_matching_strategy("custom", CustomStrategy)
```

### Batch Processing

```python
# Process multiple search URLs
search_urls = [
    "https://www.zonaprop.com.ar/inmuebles-venta-palermo-2-dormitorios.html",
    "https://www.zonaprop.com.ar/inmuebles-venta-recoleta-1-dormitorio.html"
]

all_properties = []
for url in search_urls:
    properties = analyzer.scrape_zonaprop(url)
    enriched = analyzer.enrich_with_airbnb(properties)
    all_properties.append(enriched)

# Combine and analyze
import pandas as pd
combined_df = pd.concat(all_properties, ignore_index=True)
summaries = analyzer.generate_summaries(combined_df)
```

### Dry-Run Mode

```python
# Test prompts without calling AWS Bedrock
analyzer = RealEstateAnalyzer()
analyzer.config.set('aws.bedrock.dry_run', True)

# This will log prompts but not make API calls
summaries = analyzer.generate_summaries(enriched_properties)
```

## 📊 Output Examples

### Property Data Structure

```python
# Enriched property DataFrame includes:
{
    'id': 'prop_12345',
    'title': '2 ambientes en Palermo con balcón',
    'price_usd': 95000,
    'price_ars': 95000000,
    'address': 'Av. Santa Fe 3500, Palermo',
    'latitude': -34.5875,
    'longitude': -58.4050,
    'rooms': 2,
    'bathrooms': 1,
    'surface_m2': 45,
    'views_per_day': 66,
    
    # Airbnb enrichment
    'airbnb_avg_price_entire_home': 85.50,
    'airbnb_avg_price_private_room': 45.20,
    'airbnb_occupancy_probability': 'high',
    'airbnb_avg_review_score': 4.7,
    'match_status': 'matched'
}
```

### AI Summary Example

```json
{
    "property_id": "prop_12345",
    "summary": "Che, esta propiedad en Palermo está a 95.000 dólares y tiene muy buena pinta para inversión. Con 2 ambientes y 45m², el precio por metro está en 2.111 USD/m², que está dentro del rango competitivo para la zona. Los Airbnb cercanos muestran que podés sacar entre 45-85 dólares por noche, con alta ocupación. La ubicación sobre Santa Fe es excelente para alquileres temporarios. Considerando los 66 views por día, hay mucho interés. Es una oportunidad sólida si buscás rentabilidad por alquiler turístico.",
    "confidence": 0.85
}
```

## 🛠️ Troubleshooting

### Common Issues

**"No Airbnb data found"**
```bash
# Download fresh data
analyzer.download_airbnb_data(force=True)
```

**"Zonaprop scraping blocked"**
```python
# Use HTML file fallback
properties = analyzer.scrape_zonaprop(
    search_url="https://...", 
    html_path="saved_search_results.html"
)
```

**"AWS Bedrock access denied"**
1. Check AWS credentials: `aws sts get-caller-identity`
2. Verify Bedrock model access in AWS Console
3. Ensure correct region configuration

**"Configuration validation failed"**
```python
# Check configuration
analyzer = RealEstateAnalyzer(config_path="config.yaml")
print(analyzer.config.validate_schema())
```

### Debug Mode

```python
# Enable detailed logging
import logging
logging.basicConfig(level=logging.DEBUG)

# Or via configuration
analyzer = RealEstateAnalyzer()
analyzer.config.set('logging.level', 'DEBUG')
analyzer.config.set('debug.keep_intermediates', True)
```

## 💰 Cost Estimates

**AWS Bedrock Pricing (per 100 property summaries):**

| Model | Input Tokens | Output Tokens | Total Cost |
|-------|-------------|---------------|------------|
| Claude Sonnet 4.5 | ~10K | ~40K | **~$1.50** |
| Claude 3.7 Sonnet | ~10K | ~40K | **~$1.50** |
| Claude 3.5 Haiku | ~10K | ~40K | **~$0.15** |

*Estimates based on AWS Bedrock pricing as of October 2025. Actual costs may vary.*

## 🔒 Security & Compliance

### Data Privacy
- PII scrubbing in logs and debug output
- Secure credential management (no hard-coded keys)
- Configurable data retention policies

### Legal Compliance for Argentina Users

**Applicable Laws**: Ley de Protección de Datos Personales (25.326), Código Civil y Comercial, Ley de Defensa del Consumidor (24.240).

**Key Requirements**: 
- **Data Processing**: Register activities with DNPDP if processing personal data
- **Web Scraping**: Respect robots.txt, terms of service, and implement conservative rate limits (5+ seconds between requests)
- **AWS Bedrock**: Review data processing locations and implement appropriate safeguards for international transfers
- **Commercial Use**: Seek legal review for commercial applications; academic/research use generally has lower risk

**Risk Mitigation**: Use HTML file fallbacks to reduce server load, enable PII scrubbing, implement secure credential management, and maintain documentation of compliance measures.

**Disclaimer**: This information is for guidance only and does not constitute legal advice. Consult qualified legal professionals for specific compliance questions. Users are responsible for ensuring compliance with all applicable laws in their jurisdiction.

### Best Practices
```python
# Secure configuration
config = {
    'aws': {
        'region': 'us-east-1',
        # Never put credentials in config files
    },
    'zonaprop': {
        'scraping': {
            'rate_limit_seconds': 5,  # Respectful rate limiting
            'max_retries': 3
        }
    },
    'logging': {
        'level': 'INFO',
        'scrub_pii': True  # Enable PII scrubbing
    }
}
```

## 📚 Documentation

- **[API Reference](https://renta.readthedocs.io/api/)**: Complete API documentation
- **[Configuration Guide](https://renta.readthedocs.io/configuration/)**: Detailed configuration options
- **[Examples](examples/)**: Sample scripts and notebooks
- **[Legal Notice](renta/data/legal_notice.md)**: Legal considerations and compliance

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

### Development Setup

```bash
# Clone repository
git clone https://github.com/renta-dev/renta.git
cd renta

# Install development dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run linting
black . && isort . && flake8
```

## 📄 License

MIT License - see [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **Data Sources**: [InsideAirbnb](http://insideairbnb.com/) for rental market data
- **Inspiration**: Real estate analysis methodologies from industry experts
- **Community**: Contributors and users who make RENTA better

---

**⚠️ Disclaimer**: RENTA is for research and educational purposes. Always verify property information directly and conduct proper due diligence before making investment decisions. Users are responsible for ensuring compliance with all applicable laws and terms of service.