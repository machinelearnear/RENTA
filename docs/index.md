# RENTA Documentation

Welcome to the RENTA (Real Estate Network and Trend Analyzer) documentation!

RENTA is a comprehensive Python library for real estate investment analysis in Buenos Aires, Argentina. It combines property listings from Zonaprop, rental market data from Airbnb, and AI-powered analysis to provide intelligent investment insights.

## Features

- **🏠 Property Data Integration**: Seamlessly combines Airbnb rental data with property listings
- **🗺️ Spatial Analysis**: Matches properties with nearby rental opportunities using geospatial algorithms  
- **🤖 AI-Powered Insights**: Generates investment summaries in Argentinian Spanish using AWS Bedrock
- **📊 Flexible Export**: Supports multiple output formats (CSV, JSON, DataFrame)
- **⚙️ Configurable Pipeline**: Extensible architecture supporting custom workflows

## Quick Example

```python
from renta import RealEstateAnalyzer

# Initialize analyzer
analyzer = RealEstateAnalyzer()

# Download Airbnb data
airbnb_data = analyzer.download_airbnb_data()

# Scrape property listings
search_url = "https://www.zonaprop.com.ar/inmuebles-venta-palermo.html"
properties = analyzer.scrape_zonaprop(search_url)

# Enrich with rental data
enriched = analyzer.enrich_with_airbnb(properties)

# Generate AI summaries
summaries = analyzer.generate_summaries(enriched)

# Export results
analyzer.export(enriched, format="csv", path="analysis.csv")
```

## Getting Started

- [Installation Guide](getting-started/installation.md) - Install RENTA and set up dependencies
- [Quick Start](getting-started/quickstart.md) - Get up and running in minutes
- [Configuration](getting-started/configuration.md) - Customize RENTA for your needs

## API Reference

- [RealEstateAnalyzer](api/analyzer.md) - Main interface for analysis operations
- [Configuration](api/config.md) - Configuration management system
- [Data Ingestion](api/ingestion.md) - Airbnb and Zonaprop data collection
- [Spatial Analysis](api/spatial.md) - Geospatial matching and enrichment
- [AI Analysis](api/ai.md) - AWS Bedrock integration for summaries
- [Export](api/export.md) - Data export in multiple formats

## Examples

- [Basic Usage](examples/basic-usage.md) - Common usage patterns
- [Advanced Configuration](examples/advanced-config.md) - Custom configuration examples
- [Custom Strategies](examples/custom-strategies.md) - Extending RENTA with custom logic
- [Batch Processing](examples/batch-processing.md) - Processing multiple searches

## Legal Considerations

RENTA includes comprehensive guidance for responsible use:

- [Legal Notice](legal/legal-notice.md) - Important legal considerations
- [Compliance Guide](legal/compliance.md) - Best practices for compliance

## Support

- **GitHub Issues**: [Report bugs or request features](https://github.com/renta-dev/renta/issues)
- **Documentation**: This site contains comprehensive API documentation
- **Examples**: Check the [examples directory](https://github.com/renta-dev/renta/tree/main/examples) for sample code

## License

RENTA is released under the MIT License. See the [LICENSE](https://github.com/renta-dev/renta/blob/main/LICENSE) file for details.