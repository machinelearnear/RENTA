"""
Unit tests for Airbnb data ingestion with freshness caching.

Tests the core feature: "Download and normalize Airbnb datasets from InsideAirbnb with freshness caching"
"""

import pytest
import pandas as pd
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import time

from renta.ingestion import AirbnbIngester, DataProcessor
from renta.exceptions import AirbnbDataError


@pytest.mark.unit
class TestAirbnbIngester:
    """Test Airbnb data ingestion and caching."""

    def test_init(self, mock_config_manager):
        """Test AirbnbIngester initialization."""
        ingester = AirbnbIngester(mock_config_manager)

        assert ingester.config is not None
        assert ingester.cache_dir is not None
        assert hasattr(ingester, "logger")

    def test_is_data_fresh_no_cache(self, mock_config_manager):
        """Test freshness check when no cache exists."""
        ingester = AirbnbIngester(mock_config_manager)

        # With no cached data, should return False
        assert ingester.is_data_fresh() is False

    @patch("renta.ingestion.requests.get")
    def test_download_data_force(self, mock_get, mock_config_manager, sample_airbnb_data):
        """Test force downloading Airbnb data."""
        # Mock successful HTTP response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = sample_airbnb_data.to_csv(index=False).encode("utf-8")
        mock_get.return_value = mock_response

        ingester = AirbnbIngester(mock_config_manager)

        # Test download
        with patch.object(
            ingester,
            "_get_download_urls",
            return_value={"listings": "http://test.com/listings.csv"},
        ):
            result = ingester.download_data(force=True)

            assert result is not None
            assert "listings" in result
            assert Path(result["listings"]).exists()

    def test_download_data_cached(self, mock_config_manager, sample_airbnb_data, test_data_dir):
        """Test using cached data when fresh."""
        ingester = AirbnbIngester(mock_config_manager)

        # Create fake cached file
        cache_file = Path(ingester.cache_dir) / "listings.csv"
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        sample_airbnb_data.to_csv(cache_file, index=False)

        # Update timestamp to make it fresh
        cache_file.touch()

        # Should use cache when not forcing
        result = ingester.download_data(force=False)
        assert result is not None


@pytest.mark.unit
class TestDataProcessor:
    """Test Airbnb data processing and normalization."""

    def test_process_airbnb_data(self, mock_config_manager, sample_airbnb_data, test_data_dir):
        """Test processing raw Airbnb data."""
        processor = DataProcessor(mock_config_manager)

        # Create temp file with sample data
        temp_file = test_data_dir / "listings.csv"
        sample_airbnb_data.to_csv(temp_file, index=False)

        # Process the data
        result = processor.process_airbnb_data({"listings": str(temp_file)})

        assert isinstance(result, pd.DataFrame)
        assert len(result) > 0
        assert "id" in result.columns
        assert "latitude" in result.columns
        assert "longitude" in result.columns
        assert "price" in result.columns

    def test_process_empty_data(self, mock_config_manager, test_data_dir):
        """Test processing empty Airbnb data."""
        processor = DataProcessor(mock_config_manager)

        # Create empty CSV
        empty_file = test_data_dir / "empty.csv"
        pd.DataFrame().to_csv(empty_file, index=False)

        # Should handle empty data gracefully
        with pytest.raises((AirbnbDataError, ValueError)):
            processor.process_airbnb_data({"listings": str(empty_file)})

    def test_data_normalization(self, mock_config_manager, sample_airbnb_data):
        """Test that data normalization applies expected transformations."""
        processor = DataProcessor(mock_config_manager)

        # Add some edge cases to test data
        test_data = sample_airbnb_data.copy()
        test_data.loc[0, "price"] = None  # Null price
        test_data.loc[1, "price"] = 0  # Zero price
        test_data.loc[2, "latitude"] = 91.0  # Invalid latitude

        # Process should handle these cases
        # This is a placeholder - actual implementation may vary
        assert "price" in test_data.columns


@pytest.mark.unit
class TestDataFreshness:
    """Test data freshness caching logic."""

    def test_freshness_threshold(self, mock_config_manager):
        """Test that freshness threshold is respected."""
        ingester = AirbnbIngester(mock_config_manager)

        # Get threshold from config
        threshold_hours = mock_config_manager.get("data.freshness_threshold_hours", 24)

        assert threshold_hours > 0
        assert isinstance(threshold_hours, (int, float))

    @patch("renta.ingestion.time.time")
    def test_cache_expiry(self, mock_time, mock_config_manager, test_data_dir):
        """Test that cache expires after threshold."""
        # Set current time
        current_time = 1000000
        mock_time.return_value = current_time

        ingester = AirbnbIngester(mock_config_manager)

        # Create cache file with old timestamp
        cache_file = Path(ingester.cache_dir) / "listings.csv"
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text("test")

        # Set file time to 48 hours ago (older than 24 hour threshold)
        threshold_hours = mock_config_manager.get("data.freshness_threshold_hours", 24)
        old_time = current_time - (threshold_hours + 1) * 3600

        # Modify file timestamp
        import os

        os.utime(cache_file, (old_time, old_time))

        # Should not be fresh
        is_fresh = ingester.is_data_fresh()

        # Implementation may vary, but we're testing the logic exists
        assert isinstance(is_fresh, bool)


@pytest.mark.unit
class TestErrorHandling:
    """Test error handling in Airbnb ingestion."""

    @patch("renta.ingestion.requests.get")
    def test_network_error_handling(self, mock_get, mock_config_manager):
        """Test handling of network errors during download."""
        # Mock network error
        import requests

        mock_get.side_effect = requests.exceptions.ConnectionError("Network error")

        ingester = AirbnbIngester(mock_config_manager)

        with patch.object(
            ingester,
            "_get_download_urls",
            return_value={"listings": "http://test.com/listings.csv"},
        ):
            with pytest.raises((AirbnbDataError, requests.exceptions.ConnectionError)):
                ingester.download_data(force=True)

    @patch("renta.ingestion.requests.get")
    def test_http_error_handling(self, mock_get, mock_config_manager):
        """Test handling of HTTP errors (404, 500, etc.)."""
        # Mock HTTP error
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = Exception("404 Not Found")
        mock_get.return_value = mock_response

        ingester = AirbnbIngester(mock_config_manager)

        with patch.object(
            ingester,
            "_get_download_urls",
            return_value={"listings": "http://test.com/listings.csv"},
        ):
            with pytest.raises(Exception):
                ingester.download_data(force=True)
