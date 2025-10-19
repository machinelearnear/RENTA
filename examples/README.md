# RENTA Examples

This directory contains example scripts and notebooks demonstrating various RENTA usage patterns.

## Environment Setup

Before running any examples, make sure you have the RENTA environment activated:

```bash
# Activate the environment
source renta-env/bin/activate

# For Jupyter notebooks, you may also need to install the kernel
python -m ipykernel install --user --name=renta-env --display-name="RENTA Environment"
```

## Quick Start Examples

- **[basic_usage.py](basic_usage.py)** - Simple end-to-end analysis pipeline
- **[quickstart_notebook.ipynb](quickstart_notebook.ipynb)** - Interactive Jupyter notebook tutorial

## Provider Examples

- **[mercadolibre_basic.py](mercadolibre_basic.py)** - Basic MercadoLibre provider usage
- **[mercadolibre_advanced.py](mercadolibre_advanced.py)** - Advanced MercadoLibre features with filtering and pagination
- **[provider_comparison.py](provider_comparison.py)** - Compare data from multiple providers (Zonaprop vs MercadoLibre)

## Configuration Examples

- **[custom_config.py](custom_config.py)** - Custom configuration examples
- **[config_examples/](config_examples/)** - Various configuration files for different scenarios

## Advanced Usage

- **[batch_processing.py](batch_processing.py)** - Process multiple search URLs efficiently
- **[custom_strategies.py](custom_strategies.py)** - Implement custom matching strategies
- **[performance_optimization.py](performance_optimization.py)** - Optimize for large datasets

## Integration Examples

- **[web_app_integration.py](web_app_integration.py)** - Integrate RENTA with Flask web application
- **[scheduled_analysis.py](scheduled_analysis.py)** - Automated scheduled analysis
- **[data_pipeline.py](data_pipeline.py)** - ETL pipeline with RENTA

## Troubleshooting

- **[debugging_guide.py](debugging_guide.py)** - Debug common issues
- **[error_handling.py](error_handling.py)** - Comprehensive error handling patterns

## Real Estate Data Providers

RENTA supports multiple real estate data sources through a pluggable provider architecture:

### Available Providers

- **Zonaprop** (`zonaprop`) - Web scraping from Zonaprop.com.ar (original provider)
- **MercadoLibre** (`mercadolibre`) - API-based access to MercadoLibre real estate listings

### Provider Selection

```python
from renta import RealEstateAnalyzer

analyzer = RealEstateAnalyzer()

# Use MercadoLibre provider
properties = analyzer.fetch_properties(
    provider="mercadolibre",
    location="palermo",
    property_type="apartment",
    operation_type="sale"
)

# Use Zonaprop provider (backward compatible)
properties = analyzer.scrape_zonaprop(url)
```

### Provider Comparison

Each provider has different characteristics:

| Feature | Zonaprop | MercadoLibre |
|---------|----------|--------------|
| Data Access | Web Scraping | REST API |
| Rate Limits | High (30s delays) | Moderate (1s delays) |
| Data Freshness | Real-time | Real-time |
| Reliability | Anti-bot protection | Stable API |
| Coverage | Comprehensive | Good |
| Setup Required | None | None |

## Getting Started

1. **Install RENTA**: `pip install renta`
2. **Set up AWS credentials** (see [AWS Setup Guide](../docs/getting-started/installation.md#aws-setup)) - *Optional for provider examples*
3. **Run basic example**: `python basic_usage.py`
4. **Try provider examples**: `python mercadolibre_basic.py`

## Prerequisites

### Basic Examples
- Python 3.10+
- RENTA installed (`pip install renta`)

### Provider Examples (No AWS Required)
- **MercadoLibre examples**: Only internet connection required
- **Provider comparison**: Internet connection for both providers

### Full Analysis Pipeline
- AWS credentials configured
- AWS Bedrock model access enabled
- Internet connection for data sources

## Example Data

Some examples use sample data files in the `sample_data/` directory. These are provided for testing and learning purposes.

## Running Provider Examples

### MercadoLibre Basic Usage
```bash
python mercadolibre_basic.py
```
Demonstrates basic property fetching from MercadoLibre API with no additional setup required.

### MercadoLibre Advanced Usage
```bash
python mercadolibre_advanced.py
```
Shows advanced features including:
- Location-based filtering
- Property type comparisons
- Pagination handling
- Price analysis
- Caching optimization

### Provider Comparison
```bash
python provider_comparison.py
```
Compares data quality and coverage between Zonaprop and MercadoLibre providers.

### Expected Output

Provider examples will show:
- Property counts and basic statistics
- Data quality metrics
- Price ranges and averages
- Export file locations
- Performance metrics

## Contributing

Feel free to contribute additional examples! Please follow the existing patterns:

- Include comprehensive comments
- Handle errors gracefully
- Provide clear output/logging
- Include configuration examples where relevant
- Test with both providers when applicable