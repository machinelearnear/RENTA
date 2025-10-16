# Publishing RENTA to PyPI

Step-by-step guide to publish the RENTA library to PyPI.

## Prerequisites

1. **PyPI Account**: You already have one
2. **PyPI API Token**: Recommended for secure uploads
3. **Build tools installed**:
   ```bash
   pip install build twine
   ```

## Step 1: Update Version Number

Before each release, update the version in `pyproject.toml`:

```toml
[project]
version = "0.1.0"  # Update this for each release
```

Follow [Semantic Versioning](https://semver.org/):
- `0.1.0` - Initial development release
- `0.2.0` - Minor updates, new features
- `1.0.0` - First stable release
- `1.0.1` - Bug fixes

## Step 2: Clean Previous Builds

```bash
# Remove old build artifacts
rm -rf build/ dist/ *.egg-info/

# Remove cached files
find . -type d -name __pycache__ -exec rm -rf {} +
find . -type f -name "*.pyc" -delete
```

## Step 3: Build the Package

```bash
# Build source distribution and wheel
python -m build
```

This creates:
- `dist/renta-0.1.0.tar.gz` - Source distribution
- `dist/renta-0.1.0-py3-none-any.whl` - Wheel distribution

## Step 4: Verify the Build

```bash
# Check the distribution files
twine check dist/*
```

Should output: `Checking dist/renta-0.1.0.tar.gz: PASSED`

## Step 5: Test Installation Locally

```bash
# Install in editable mode first
pip install -e .

# Test imports
python -c "from renta import RealEstateAnalyzer; print('Import successful!')"

# Run tests
pytest -m unit
```

## Step 6: Upload to TestPyPI (Recommended First)

TestPyPI is a separate instance for testing package uploads.

### 6.1: Create TestPyPI API Token

1. Go to https://test.pypi.org/
2. Register/login with your account
3. Go to Account Settings → API tokens
4. Create token with scope: "Entire account"
5. Save the token (starts with `pypi-`)

### 6.2: Configure TestPyPI credentials

Create `~/.pypirc`:

```ini
[distutils]
index-servers =
    pypi
    testpypi

[pypi]
username = __token__
password = pypi-YOUR_PRODUCTION_TOKEN_HERE

[testpypi]
repository = https://test.pypi.org/legacy/
username = __token__
password = pypi-YOUR_TEST_TOKEN_HERE
```

### 6.3: Upload to TestPyPI

```bash
twine upload --repository testpypi dist/*
```

### 6.4: Test installation from TestPyPI

```bash
# Create fresh virtual environment
python -m venv test_env
source test_env/bin/activate  # On Windows: test_env\Scripts\activate

# Install from TestPyPI
pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ renta

# Test it works
python -c "from renta import RealEstateAnalyzer; print('Success!')"

# Cleanup
deactivate
rm -rf test_env
```

## Step 7: Upload to Production PyPI

**Only do this after testing on TestPyPI!**

### 7.1: Create PyPI API Token

1. Go to https://pypi.org/
2. Login with your account
3. Go to Account Settings → API tokens
4. Create token with scope: "Entire account" (or scope to project after first upload)
5. Save the token securely

### 7.2: Upload to PyPI

```bash
twine upload dist/*
```

You'll be prompted for credentials:
- Username: `__token__`
- Password: Your PyPI API token (starts with `pypi-`)

Or use the token from `~/.pypirc` configured earlier.

## Step 8: Verify Publication

1. Visit https://pypi.org/project/renta/
2. Check that:
   - Version number is correct
   - Description renders properly
   - Links work
   - Classifiers are correct

## Step 9: Test Installation from PyPI

```bash
# Create fresh virtual environment
python -m venv verify_env
source verify_env/bin/activate

# Install from PyPI
pip install renta

# Verify installation
python -c "from renta import RealEstateAnalyzer; print('Installed successfully!')"

# Test basic functionality
python -c "
from renta import RealEstateAnalyzer
analyzer = RealEstateAnalyzer()
status = analyzer.get_status()
print('Status:', status)
"

# Cleanup
deactivate
rm -rf verify_env
```

## Step 10: Create GitHub Release

1. Go to https://github.com/machinelearnear/RENTA/releases
2. Click "Create a new release"
3. Tag: `v0.1.0`
4. Title: `RENTA v0.1.0`
5. Description: Copy from CHANGELOG.md
6. Attach the distribution files from `dist/`
7. Publish release

## Step 11: Announce

Consider announcing the release:
- GitHub Discussions
- README.md badge: `[![PyPI version](https://badge.fury.io/py/renta.svg)](https://badge.fury.io/py/renta)`
- Social media/community channels

## Troubleshooting

### "The name 'renta' is too similar to an existing project"

PyPI prevents similar names. Options:
1. Choose a different name (e.g., `renta-ba`, `renta-analyzer`)
2. Request the abandoned project name if it exists

### "File already exists"

You cannot re-upload the same version. Options:
1. Increment version number
2. Delete the release on TestPyPI (production PyPI doesn't allow deletion)

### "Invalid distribution file"

```bash
# Rebuild cleanly
rm -rf dist/ build/ *.egg-info
python -m build
twine check dist/*
```

### Missing files in package

Check `MANIFEST.in` includes necessary files:
```
include README.md LICENSE CHANGELOG.md
recursive-include renta *.py *.yaml *.json *.md *.csv
```

Verify with:
```bash
tar -tzf dist/renta-0.1.0.tar.gz | head -20
```

### Import errors after installation

Ensure package structure is correct:
```
renta/
├── __init__.py
├── analyzer.py
├── config.py
└── ...
```

## Automation

### Using GitHub Actions

Create `.github/workflows/publish.yml`:

```yaml
name: Publish to PyPI

on:
  release:
    types: [published]

jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-python@v5
      with:
        python-version: '3.11'
    - name: Install dependencies
      run: |
        pip install build twine
    - name: Build package
      run: python -m build
    - name: Publish to PyPI
      env:
        TWINE_USERNAME: __token__
        TWINE_PASSWORD: ${{ secrets.PYPI_API_TOKEN }}
      run: twine upload dist/*
```

Add `PYPI_API_TOKEN` to repository secrets.

## Best Practices

1. **Always test on TestPyPI first**
2. **Never reuse version numbers**
3. **Keep CHANGELOG.md updated**
4. **Run tests before publishing**: `pytest`
5. **Use semantic versioning**
6. **Tag releases in git**: `git tag v0.1.0 && git push --tags`
7. **Keep dependencies up to date**
8. **Monitor package security**: `pip-audit`

## Quick Reference

```bash
# Complete publish workflow
rm -rf dist/ build/ *.egg-info/
python -m build
twine check dist/*
twine upload --repository testpypi dist/*  # Test first
twine upload dist/*                        # Production
```

## Support

- PyPI Help: https://pypi.org/help/
- Packaging Guide: https://packaging.python.org/
- Twine Docs: https://twine.readthedocs.io/
