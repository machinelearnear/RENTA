# RENTA Development Makefile

.PHONY: help install install-dev test test-unit test-integration lint format clean build docs serve-docs publish

# Default target
help:
	@echo "RENTA Development Commands:"
	@echo ""
	@echo "Setup:"
	@echo "  install      Install package in production mode"
	@echo "  install-dev  Install package in development mode with all dependencies"
	@echo ""
	@echo "Testing:"
	@echo "  test         Run all tests"
	@echo "  test-unit    Run unit tests only"
	@echo "  test-integration  Run integration tests only"
	@echo ""
	@echo "Code Quality:"
	@echo "  lint         Run all linting checks"
	@echo "  format       Format code with black and isort"
	@echo ""
	@echo "Documentation:"
	@echo "  docs         Build documentation"
	@echo "  serve-docs   Serve documentation locally"
	@echo ""
	@echo "Build & Release:"
	@echo "  clean        Clean build artifacts"
	@echo "  build        Build package for distribution"
	@echo "  publish      Publish to PyPI (requires credentials)"

# Installation
install:
	pip install -e .

install-dev:
	pip install -e ".[dev]"
	pre-commit install

# Testing
test:
	pytest tests/ -v --cov=renta --cov-report=term-missing --cov-report=html

test-unit:
	pytest tests/ -v -m "not integration" --cov=renta --cov-report=term-missing

test-integration:
	pytest tests/ -v -m "integration" --tb=short

# Code quality
lint:
	black --check renta/ tests/ examples/
	isort --check-only renta/ tests/ examples/
	flake8 renta/ tests/ examples/
	mypy renta/
	bandit -r renta/ -f json

format:
	black renta/ tests/ examples/
	isort renta/ tests/ examples/

# Documentation
docs:
	mkdocs build

serve-docs:
	mkdocs serve

# Build and release
clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf .pytest_cache/
	rm -rf .coverage
	rm -rf htmlcov/
	rm -rf site/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

build: clean
	python -m build

publish: build
	twine check dist/*
	twine upload dist/*

# Development utilities
check-deps:
	pip-audit
	safety check

update-deps:
	pip-compile --upgrade requirements.in
	pip-compile --upgrade requirements-dev.in