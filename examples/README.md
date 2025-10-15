# RENTA Examples

This directory contains example scripts and notebooks demonstrating various RENTA usage patterns.

## Quick Start Examples

- **[basic_usage.py](basic_usage.py)** - Simple end-to-end analysis pipeline
- **[quickstart_notebook.ipynb](quickstart_notebook.ipynb)** - Interactive Jupyter notebook tutorial

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

## Getting Started

1. **Install RENTA**: `pip install renta`
2. **Set up AWS credentials** (see [AWS Setup Guide](../docs/getting-started/installation.md#aws-setup))
3. **Run basic example**: `python basic_usage.py`

## Prerequisites

All examples assume you have:

- Python 3.10+
- RENTA installed (`pip install renta`)
- AWS credentials configured
- AWS Bedrock model access enabled

## Example Data

Some examples use sample data files in the `sample_data/` directory. These are provided for testing and learning purposes.

## Contributing

Feel free to contribute additional examples! Please follow the existing patterns:

- Include comprehensive comments
- Handle errors gracefully
- Provide clear output/logging
- Include configuration examples where relevant