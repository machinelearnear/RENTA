# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.1] - 2025-10-17

### Added
- Professional logo and branding
- Assets folder for static resources
- Comprehensive test suite covering all core features
- CI/CD pipeline with GitHub Actions
- Publishing guides and checklists

### Changed
- Updated README with centered logo and improved branding
- Improved exception handling with proper logging

## [0.1.0] - 2024-10-15

### Added
- Initial release with basic project structure
- Core exception classes for error handling
- Abstract interfaces for pluggable components:
  - `ExchangeRateProvider` for currency conversion
  - `MatchingStrategy` for property-Airbnb matching
  - `PromptLoader` for AI prompt templates
  - `DataExporter` for output formats
  - `MetricsCollector` for monitoring
  - `CacheProvider` for caching
- Package configuration with `pyproject.toml`
- Main entry points for `RealEstateAnalyzer` and `ConfigManager`

### Technical Details
- Python 3.10+ support
- MIT License
- Comprehensive dependency management
- Plugin architecture via entry points
- Development tools configuration (black, isort, mypy, pytest)