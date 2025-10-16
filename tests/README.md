# RENTA Test Suite

Comprehensive test suite for the RENTA library covering all core features.

## Test Structure

```
tests/
├── __init__.py              # Test package initialization
├── conftest.py              # Shared fixtures and configuration
├── README.md                # This file
├── unit/                    # Unit tests (fast, isolated)
│   ├── test_airbnb_ingestion.py
│   ├── test_zonaprop_scraping.py
│   ├── test_spatial_matching.py
│   ├── test_ai_summaries.py
│   └── test_export.py
└── integration/             # Integration tests (slower, may need services)
    └── test_end_to_end.py
```

## Features Tested

### ✅ Airbnb Data Ingestion (`test_airbnb_ingestion.py`)
- Download and normalization of Airbnb datasets from InsideAirbnb
- Freshness caching mechanism
- Data validation and error handling
- Cache expiry logic

### ✅ Zonaprop Scraping (`test_zonaprop_scraping.py`)
- Web scraping of property listings
- HTML parsing and data extraction
- Anti-bot detection (Cloudflare)
- Fallback to saved HTML files
- Price, location, and attribute extraction

### ✅ Spatial Matching (`test_spatial_matching.py`)
- Property-to-Airbnb spatial matching
- Configurable radius filtering
- Distance calculations (Haversine)
- BallTree spatial indexing
- Enrichment with rental metrics
- Occupancy and yield estimation

### ✅ AI Summaries (`test_ai_summaries.py`)
- Claude Sonnet 4.5 integration via AWS Bedrock
- Spanish language summary generation
- Prompt template management
- Token usage tracking
- Error handling and retries

### ✅ Data Export (`test_export.py`)
- Export to CSV, JSON, and pandas DataFrame
- Schema consistency validation
- Encoding handling (UTF-8, special characters)
- Data type preservation
- Error handling (permissions, invalid paths)

### ✅ Integration Tests (`test_end_to_end.py`)
- Complete end-to-end workflows
- Data persistence and caching
- Error recovery mechanisms
- Performance benchmarks

## Running Tests

### Run All Tests

```bash
pytest
```

### Run Unit Tests Only (Fast)

```bash
pytest -m unit
```

### Run Integration Tests

```bash
pytest -m integration
```

### Run Tests Excluding Slow/AWS/Network

```bash
pytest -m "not slow and not aws and not network"
```

### Run Specific Test File

```bash
pytest tests/unit/test_airbnb_ingestion.py
```

### Run Specific Test

```bash
pytest tests/unit/test_export.py::TestCSVExporter::test_export_to_file
```

### Run with Coverage Report

```bash
pytest --cov=renta --cov-report=html
```

Then open `htmlcov/index.html` to view the coverage report.

### Run Tests in Parallel (with pytest-xdist)

```bash
pip install pytest-xdist
pytest -n auto
```

## Test Markers

Tests are categorized using pytest markers:

- `@pytest.mark.unit` - Fast unit tests with no external dependencies
- `@pytest.mark.integration` - Integration tests that may require services
- `@pytest.mark.slow` - Tests that take more than 5 seconds
- `@pytest.mark.aws` - Tests requiring AWS credentials (auto-skipped if not available)
- `@pytest.mark.network` - Tests requiring network access

## Environment Variables

### Required for AWS Tests

```bash
export AWS_ACCESS_KEY_ID="your-key"
export AWS_SECRET_ACCESS_KEY="your-secret"
export AWS_REGION="us-east-1"
```

Or configure `~/.aws/credentials`.

### Optional

```bash
# Suppress legal notice during tests (automatically set by conftest.py)
export RENTA_LEGAL_NOTICE_ACKNOWLEDGED=true

# Custom config for tests
export RENTA_CONFIG=/path/to/test_config.yaml
```

## Continuous Integration

### GitHub Actions Example

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ['3.10', '3.11', '3.12']

    steps:
    - uses: actions/checkout@v3

    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: ${{ matrix.python-version }}

    - name: Install dependencies
      run: |
        pip install -e ".[dev,test]"

    - name: Run tests
      run: |
        pytest -m "not slow and not aws and not network" --cov=renta

    - name: Upload coverage
      uses: codecov/codecov-action@v3
```

## Pre-commit Hooks

Run tests before committing:

```bash
# Install pre-commit
pip install pre-commit

# Install git hooks
pre-commit install

# Run manually
pre-commit run --all-files
```

## Fixtures

Common fixtures are defined in `conftest.py`:

- `test_data_dir` - Temporary directory for test files
- `test_config_dict` - Minimal test configuration
- `test_config_file` - Temporary config file
- `sample_airbnb_data` - Realistic sample Airbnb data
- `sample_zonaprop_data` - Sample property listings
- `sample_enriched_data` - Sample enriched properties
- `mock_config_manager` - Mocked configuration manager
- `mock_boto3_client` - Mocked AWS Bedrock client
- `mock_requests_get` - Mocked HTTP requests

## Writing New Tests

### Example Unit Test

```python
import pytest
from renta.ingestion import AirbnbIngester

@pytest.mark.unit
class TestMyFeature:
    def test_my_function(self, mock_config_manager):
        """Test description."""
        ingester = AirbnbIngester(mock_config_manager)

        result = ingester.some_method()

        assert result is not None
        assert len(result) > 0
```

### Example Integration Test

```python
import pytest

@pytest.mark.integration
@pytest.mark.slow
class TestMyIntegration:
    def test_complete_workflow(self, test_config_file):
        """Test end-to-end workflow."""
        from renta import RealEstateAnalyzer

        analyzer = RealEstateAnalyzer(config_path=test_config_file)
        # ... test complete workflow
```

## Troubleshooting

### Tests Failing Due to Missing Dependencies

```bash
pip install -e ".[dev,test]"
```

### AWS Tests Being Skipped

Either:
1. Configure AWS credentials
2. Run without AWS tests: `pytest -m "not aws"`

### Slow Tests Taking Too Long

Run without slow tests:

```bash
pytest -m "not slow"
```

### Coverage Too Low

Check which files need more tests:

```bash
pytest --cov=renta --cov-report=term-missing
```

## Test Data

Test data is automatically generated using:
- `pandas` for DataFrames
- `numpy` for random data generation
- `faker` (if needed) for realistic fake data

All test data uses Buenos Aires coordinates:
- Latitude: approximately -34.6037
- Longitude: approximately -58.3816

## Contributing

When adding new features:

1. Write tests first (TDD)
2. Ensure all tests pass: `pytest`
3. Check coverage: `pytest --cov=renta`
4. Run linters: `black . && isort . && flake8`
5. Update this README if adding new test categories

## Support

For issues with tests:
1. Check test logs in `tests/logs/pytest.log`
2. Run with verbose output: `pytest -vv`
3. Run specific failing test in isolation
4. Check if issue is environment-specific

## License

Tests are part of the RENTA project and follow the same MIT license.
