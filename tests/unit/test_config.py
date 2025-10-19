"""
Unit tests for configuration management system.

Tests the configuration loading, validation, and access functionality
with focus on the real estate provider configuration.
"""

import pytest
import tempfile
import yaml
from pathlib import Path

from renta.config import ConfigManager
from renta.exceptions import ConfigurationError


@pytest.mark.unit
class TestConfigManager:
    """Test ConfigManager functionality."""

    def test_default_config_loads(self):
        """Test that default configuration loads successfully."""
        config = ConfigManager()
        
        # Verify basic structure
        assert config.get("data") is not None
        assert config.get("real_estate") is not None
        assert config.get("airbnb") is not None
        
    def test_real_estate_provider_config(self):
        """Test real estate provider configuration structure."""
        config = ConfigManager()
        
        # Test default provider
        default_provider = config.get("real_estate.default_provider")
        assert default_provider in ["zonaprop", "mercadolibre"]
        
        # Test MercadoLibre provider config
        ml_config = config.get("real_estate.providers.mercadolibre")
        assert ml_config is not None
        assert "rate_limit_seconds" in ml_config
        assert "max_retries" in ml_config
        assert "timeout_seconds" in ml_config
        assert "max_results_per_request" in ml_config
        assert "cache_ttl_hours" in ml_config
        assert "defaults" in ml_config
        
        # Test Zonaprop provider config
        zp_config = config.get("real_estate.providers.zonaprop")
        assert zp_config is not None
        assert "rate_limit_seconds" in zp_config
        assert "max_retries" in zp_config
        
    def test_mercadolibre_defaults(self):
        """Test MercadoLibre default configuration values."""
        config = ConfigManager()
        
        ml_defaults = config.get("real_estate.providers.mercadolibre.defaults")
        assert ml_defaults is not None
        assert ml_defaults.get("country") == "AR"
        assert ml_defaults.get("state") is not None
        
    def test_invalid_provider_validation(self):
        """Test that invalid provider names are rejected."""
        invalid_config = {
            "data": {"cache_dir": "~/.renta/cache", "export_dir": "~/.renta/exports", "freshness_threshold_hours": 24},
            "real_estate": {"default_provider": "invalid_provider"},
            "airbnb": {"matching": {"radius_km": 0.3, "min_nights_threshold": 7, "min_review_score": 4.0, "occupancy_thresholds": {"high": 14, "medium": 7}}},
            "zonaprop": {"scraping": {"rate_limit_seconds": 5.0, "max_retries": 3, "timeout_seconds": 30, "user_agents": ["test"]}},
            "exchange_rates": {"provider": "xe.com", "cache_ttl_hours": 24, "fallback_rate": 1000},
            "aws": {"region": "us-east-1", "bedrock": {"model_id": "test", "max_tokens": 1024, "temperature": 0.7, "max_retries": 3}},
            "prompts": {"default": "test"},
            "logging": {"level": "INFO", "format": "json"}
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(invalid_config, f)
            temp_path = f.name
            
        with pytest.raises(ConfigurationError) as exc_info:
            ConfigManager(temp_path)
            
        assert "invalid_provider" in str(exc_info.value)
        
    def test_invalid_rate_limit_validation(self):
        """Test that invalid rate limit values are rejected."""
        invalid_config = {
            "data": {"cache_dir": "~/.renta/cache", "export_dir": "~/.renta/exports", "freshness_threshold_hours": 24},
            "real_estate": {
                "default_provider": "mercadolibre",
                "providers": {
                    "mercadolibre": {
                        "rate_limit_seconds": -1,  # Invalid negative value
                        "max_retries": 3,
                        "timeout_seconds": 30,
                        "max_results_per_request": 50,
                        "cache_ttl_hours": 24,
                        "defaults": {"country": "AR", "state": "test"}
                    }
                }
            },
            "airbnb": {"matching": {"radius_km": 0.3, "min_nights_threshold": 7, "min_review_score": 4.0, "occupancy_thresholds": {"high": 14, "medium": 7}}},
            "zonaprop": {"scraping": {"rate_limit_seconds": 5.0, "max_retries": 3, "timeout_seconds": 30, "user_agents": ["test"]}},
            "exchange_rates": {"provider": "xe.com", "cache_ttl_hours": 24, "fallback_rate": 1000},
            "aws": {"region": "us-east-1", "bedrock": {"model_id": "test", "max_tokens": 1024, "temperature": 0.7, "max_retries": 3}},
            "prompts": {"default": "test"},
            "logging": {"level": "INFO", "format": "json"}
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(invalid_config, f)
            temp_path = f.name
            
        with pytest.raises(ConfigurationError):
            ConfigManager(temp_path)
            
    def test_config_get_with_defaults(self):
        """Test configuration access with default values."""
        config = ConfigManager()
        
        # Test existing key
        assert config.get("real_estate.default_provider") is not None
        
        # Test non-existing key with default
        assert config.get("nonexistent.key", "default_value") == "default_value"
        
        # Test nested non-existing key
        assert config.get("real_estate.nonexistent.nested", 42) == 42