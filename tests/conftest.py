"""
Pytest configuration and shared fixtures for RENTA test suite.

Provides reusable fixtures, test data, and configuration for unit and integration tests.
"""

import os
import json
import tempfile
from pathlib import Path
from typing import Dict, Any
import pytest
import pandas as pd
import numpy as np
from unittest.mock import Mock, MagicMock

# Set test environment variable to suppress legal notice during tests
os.environ["RENTA_LEGAL_NOTICE_ACKNOWLEDGED"] = "true"


@pytest.fixture(scope="session")
def test_data_dir():
    """Create temporary directory for test data."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def test_config_dict() -> Dict[str, Any]:
    """Minimal test configuration dictionary."""
    return {
        "data": {
            "cache_dir": tempfile.mkdtemp(),
            "export_dir": tempfile.mkdtemp(),
            "freshness_threshold_hours": 24,
        },
        "airbnb": {
            "matching": {
                "radius_km": 0.3,
                "min_nights_threshold": 7,
                "max_listings_per_property": 10,
            }
        },
        "aws": {
            "region": "us-east-1",
            "model_id": "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
            "max_tokens": 1000,
            "temperature": 0.7,
        },
        "logging": {"level": "ERROR", "format": "json"},  # Suppress logs during tests
        "security": {"enable_pii_scrubbing": True, "pii_replacement": "[REDACTED]"},
        "network": {"timeout_seconds": 30, "max_retries": 3, "backoff_factor": 0.3},
    }


@pytest.fixture
def test_config_file(test_config_dict, test_data_dir):
    """Create temporary test configuration file."""
    config_path = test_data_dir / "test_config.yaml"

    import yaml

    with open(config_path, "w") as f:
        yaml.dump(test_config_dict, f)

    return str(config_path)


@pytest.fixture
def sample_airbnb_data() -> pd.DataFrame:
    """Generate realistic sample Airbnb data for testing."""
    np.random.seed(42)
    n_listings = 100

    # Buenos Aires approximate coordinates
    base_lat, base_lon = -34.6037, -58.3816

    data = {
        "id": [f"airbnb_{i}" for i in range(n_listings)],
        "name": [f"Beautiful Apartment {i}" for i in range(n_listings)],
        "latitude": base_lat + np.random.normal(0, 0.02, n_listings),
        "longitude": base_lon + np.random.normal(0, 0.02, n_listings),
        "price": np.random.randint(30, 200, n_listings),
        "minimum_nights": np.random.choice([1, 2, 3, 7, 30], n_listings),
        "number_of_reviews": np.random.randint(0, 100, n_listings),
        "reviews_per_month": np.random.uniform(0, 5, n_listings),
        "calculated_host_listings_count": np.random.randint(1, 5, n_listings),
        "availability_365": np.random.randint(0, 365, n_listings),
        "room_type": np.random.choice(
            ["Entire home/apt", "Private room", "Shared room"], n_listings
        ),
        "bedrooms": np.random.randint(1, 4, n_listings),
        "beds": np.random.randint(1, 5, n_listings),
    }

    return pd.DataFrame(data)


@pytest.fixture
def sample_zonaprop_data() -> pd.DataFrame:
    """Generate realistic sample Zonaprop property data for testing."""
    np.random.seed(42)
    n_properties = 20

    # Buenos Aires approximate coordinates
    base_lat, base_lon = -34.6037, -58.3816

    data = {
        "id": [f"prop_{i}" for i in range(n_properties)],
        "title": [f"2 Ambientes en Palermo {i}" for i in range(n_properties)],
        "price_usd": np.random.randint(60000, 150000, n_properties),
        "latitude": base_lat + np.random.normal(0, 0.01, n_properties),
        "longitude": base_lon + np.random.normal(0, 0.01, n_properties),
        "bedrooms": np.random.randint(1, 3, n_properties),
        "bathrooms": np.random.randint(1, 2, n_properties),
        "area_m2": np.random.randint(40, 80, n_properties),
        "neighborhood": ["Palermo"] * n_properties,
        "property_type": ["Departamento"] * n_properties,
        "url": [f"https://www.zonaprop.com.ar/property-{i}.html" for i in range(n_properties)],
    }

    return pd.DataFrame(data)


@pytest.fixture
def sample_enriched_data(sample_zonaprop_data) -> pd.DataFrame:
    """Generate sample enriched property data for testing."""
    np.random.seed(42)

    enriched = sample_zonaprop_data.copy()

    # Add enrichment columns
    enriched["match_status"] = np.random.choice(
        ["matched", "no_matches"], len(enriched), p=[0.8, 0.2]
    )
    enriched["matched_listings_count"] = np.where(
        enriched["match_status"] == "matched", np.random.randint(1, 10, len(enriched)), 0
    )
    enriched["avg_airbnb_price"] = np.where(
        enriched["match_status"] == "matched", np.random.uniform(50, 150, len(enriched)), np.nan
    )
    enriched["median_airbnb_price"] = np.where(
        enriched["match_status"] == "matched", np.random.uniform(40, 140, len(enriched)), np.nan
    )
    enriched["avg_reviews_per_month"] = np.where(
        enriched["match_status"] == "matched", np.random.uniform(0.5, 4.0, len(enriched)), np.nan
    )
    enriched["estimated_occupancy"] = np.where(
        enriched["match_status"] == "matched",
        np.random.choice(["high", "medium", "low"], len(enriched)),
        "unknown",
    )
    enriched["rental_yield_estimate"] = np.where(
        enriched["match_status"] == "matched", np.random.uniform(0.03, 0.08, len(enriched)), np.nan
    )

    return enriched


@pytest.fixture
def mock_config_manager(test_config_dict):
    """Create a mock ConfigManager for testing."""
    from renta.config import ConfigManager

    # Create a real ConfigManager with test config
    # We'll use a temporary file approach
    import tempfile
    import yaml

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(test_config_dict, f)
        temp_path = f.name

    try:
        config = ConfigManager(temp_path)
        yield config
    finally:
        # Cleanup
        os.unlink(temp_path)


@pytest.fixture
def mock_boto3_client():
    """Create a mock boto3 Bedrock client for testing."""
    mock_client = Mock()

    # Mock invoke_model response
    mock_response = {
        "body": Mock(),
        "contentType": "application/json",
        "ResponseMetadata": {"HTTPStatusCode": 200},
    }

    # Mock response body
    mock_body = Mock()
    mock_body.read.return_value = json.dumps(
        {
            "content": [
                {"text": "Esta propiedad presenta una excelente oportunidad de inversión..."}
            ],
            "usage": {"input_tokens": 500, "output_tokens": 300},
            "stop_reason": "end_turn",
        }
    ).encode("utf-8")

    mock_response["body"] = mock_body
    mock_client.invoke_model.return_value = mock_response

    return mock_client


@pytest.fixture
def mock_requests_get():
    """Create a mock for requests.get for web scraping tests."""
    mock = Mock()

    # Mock successful response
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.content = b"<html><body>Test HTML</body></html>"
    mock_response.text = "<html><body>Test HTML</body></html>"
    mock_response.headers = {"Content-Type": "text/html"}

    mock.return_value = mock_response

    return mock


@pytest.fixture
def sample_csv_file(sample_enriched_data, test_data_dir):
    """Create a sample CSV file for export testing."""
    csv_path = test_data_dir / "test_export.csv"
    sample_enriched_data.to_csv(csv_path, index=False)
    return str(csv_path)


@pytest.fixture
def sample_json_file(sample_enriched_data, test_data_dir):
    """Create a sample JSON file for export testing."""
    json_path = test_data_dir / "test_export.json"
    sample_enriched_data.to_json(json_path, orient="records", indent=2)
    return str(json_path)


# Markers for different test categories
def pytest_configure(config):
    """Configure custom pytest markers."""
    config.addinivalue_line("markers", "unit: Unit tests")
    config.addinivalue_line("markers", "integration: Integration tests requiring external services")
    config.addinivalue_line("markers", "aws: Tests requiring AWS credentials")
    config.addinivalue_line("markers", "network: Tests requiring network access")
    config.addinivalue_line("markers", "slow: Slow tests that take more than 5 seconds")


# Skip AWS tests if credentials not available
def pytest_collection_modifyitems(config, items):
    """Automatically skip AWS tests if credentials are not available."""
    skip_aws = pytest.mark.skip(reason="AWS credentials not configured")

    # Check for AWS credentials
    has_aws_creds = (
        os.getenv("AWS_ACCESS_KEY_ID")
        or os.getenv("AWS_PROFILE")
        or Path.home().joinpath(".aws", "credentials").exists()
    )

    for item in items:
        if "aws" in item.keywords and not has_aws_creds:
            item.add_marker(skip_aws)
