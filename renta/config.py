"""
Configuration management system for RENTA library.

Provides centralized configuration loading, validation, and access with support
for user configuration overrides and embedded defaults.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional, Union
import yaml
import jsonschema
from jsonschema import ValidationError
import importlib.resources

from .exceptions import ConfigurationError


class ConfigManager:
    """Manages configuration loading, validation, and access.
    
    Supports configuration discovery via environment variables and current directory,
    deep merging of user config with embedded defaults, and JSON schema validation.
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """Initialize ConfigManager with optional config path.
        
        Args:
            config_path: Optional explicit path to configuration file.
                        If None, will discover via RENTA_CONFIG env var or current directory.
                        
        Raises:
            ConfigurationError: If configuration loading or validation fails
        """
        self._config: Dict[str, Any] = {}
        self._schema: Dict[str, Any] = {}
        
        # Load configuration schema
        self._load_schema()
        
        # Load default configuration
        default_config = self._load_default_config()
        
        # Discover and load user configuration
        user_config_path = config_path or self.discover_config_path()
        user_config = self._load_user_config(user_config_path) if user_config_path else {}
        
        # Deep merge configurations (user overrides defaults)
        self._config = self._deep_merge(default_config, user_config)
        
        # Validate merged configuration
        self.validate_schema()
        
        # Expand paths (handle ~ and relative paths)
        self._expand_paths()
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value with dot notation support.
        
        Args:
            key: Configuration key using dot notation (e.g., 'airbnb.matching.radius_km')
            default: Default value if key is not found
            
        Returns:
            Configuration value or default
            
        Examples:
            >>> config.get('airbnb.matching.radius_km')
            0.3
            >>> config.get('nonexistent.key', 'fallback')
            'fallback'
        """
        keys = key.split('.')
        value = self._config
        
        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default
    
    def set(self, key: str, value: Any) -> None:
        """Set configuration value with dot notation support.
        
        Args:
            key: Configuration key using dot notation
            value: Value to set
            
        Note:
            This modifies the in-memory configuration only.
            Changes are not persisted to configuration files.
        """
        keys = key.split('.')
        config = self._config
        
        # Navigate to parent of target key
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        
        # Set the final key
        config[keys[-1]] = value
    
    def validate_schema(self) -> None:
        """Validate configuration against JSON schema.
        
        Raises:
            ConfigurationError: If configuration is invalid with descriptive error message
        """
        try:
            jsonschema.validate(self._config, self._schema)
        except ValidationError as e:
            # Create descriptive error message with path to offending key
            error_path = '.'.join(str(p) for p in e.absolute_path) if e.absolute_path else 'root'
            raise ConfigurationError(
                f"Configuration validation failed at '{error_path}': {e.message}",
                details={
                    "path": error_path,
                    "value": e.instance,
                    "schema_path": list(e.schema_path),
                    "validator": e.validator,
                    "validator_value": e.validator_value
                }
            ) from e
    
    @staticmethod
    def discover_config_path() -> Optional[str]:
        """Discover config file via env var or current directory.
        
        Returns:
            Path to configuration file if found, None otherwise
            
        Discovery order:
            1. RENTA_CONFIG environment variable
            2. config.yaml in current directory
            3. .renta/config.yaml in current directory
        """
        # Check environment variable first
        env_path = os.getenv('RENTA_CONFIG')
        if env_path and os.path.isfile(env_path):
            return env_path
        
        # Check current directory
        current_dir = Path.cwd()
        
        # Check for config.yaml in current directory
        config_yaml = current_dir / 'config.yaml'
        if config_yaml.is_file():
            return str(config_yaml)
        
        # Check for .renta/config.yaml in current directory
        renta_config = current_dir / '.renta' / 'config.yaml'
        if renta_config.is_file():
            return str(renta_config)
        
        return None
    
    def _load_schema(self) -> None:
        """Load JSON schema for configuration validation."""
        try:
            with importlib.resources.open_text('renta.schemas', 'config_schema.json') as f:
                self._schema = json.load(f)
        except Exception as e:
            raise ConfigurationError(
                f"Failed to load configuration schema: {e}",
                details={"error_type": type(e).__name__}
            ) from e
    
    def _load_default_config(self) -> Dict[str, Any]:
        """Load embedded default configuration.

        Returns:
            Default configuration dictionary

        Raises:
            ConfigurationError: If default config cannot be loaded
        """
        try:
            with importlib.resources.open_text('renta.data', 'default_config.yaml') as f:
                return yaml.safe_load(f)
        except Exception as e:
            raise ConfigurationError(
                f"Failed to load default configuration: {e}",
                details={"error_type": type(e).__name__}
            ) from e
    
    def _load_user_config(self, config_path: str) -> Dict[str, Any]:
        """Load user configuration from file.
        
        Args:
            config_path: Path to user configuration file
            
        Returns:
            User configuration dictionary
            
        Raises:
            ConfigurationError: If user config cannot be loaded or parsed
        """
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                return config if config is not None else {}
        except FileNotFoundError as e:
            raise ConfigurationError(
                f"Configuration file not found: {config_path}",
                details={"path": config_path}
            ) from e
        except yaml.YAMLError as e:
            raise ConfigurationError(
                f"Invalid YAML in configuration file {config_path}: {e}",
                details={"path": config_path, "yaml_error": str(e)}
            ) from e
        except Exception as e:
            raise ConfigurationError(
                f"Failed to load configuration from {config_path}: {e}",
                details={"path": config_path, "error_type": type(e).__name__}
            ) from e
    
    def _deep_merge(self, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """Deep merge two configuration dictionaries.
        
        Args:
            base: Base configuration (defaults)
            override: Override configuration (user config)
            
        Returns:
            Merged configuration with override taking precedence
        """
        result = base.copy()
        
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        
        return result
    
    def _expand_paths(self) -> None:
        """Expand ~ and relative paths in configuration."""
        # Expand data directories
        if 'data' in self._config:
            for key in ['cache_dir', 'export_dir']:
                if key in self._config['data']:
                    path = self._config['data'][key]
                    if isinstance(path, str):
                        expanded = os.path.expanduser(path)
                        self._config['data'][key] = os.path.abspath(expanded)
        
        # Expand prompt paths
        if 'prompts' in self._config:
            if 'default' in self._config['prompts']:
                path = self._config['prompts']['default']
                if isinstance(path, str) and not path.startswith('/'):
                    # Relative paths are relative to package
                    self._config['prompts']['default'] = path
            
            if 'custom' in self._config['prompts']:
                for name, path in self._config['prompts']['custom'].items():
                    if isinstance(path, str):
                        expanded = os.path.expanduser(path)
                        self._config['prompts']['custom'][name] = os.path.abspath(expanded)
    
    def to_dict(self) -> Dict[str, Any]:
        """Get configuration as dictionary.
        
        Returns:
            Complete configuration dictionary
        """
        return self._config.copy()
    
    def __repr__(self) -> str:
        """String representation of ConfigManager."""
        return f"ConfigManager(keys={list(self._config.keys())})"