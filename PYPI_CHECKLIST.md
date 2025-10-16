# PyPI Publishing Checklist

Quick checklist for publishing RENTA to PyPI. See `PUBLISHING_GUIDE.md` for detailed instructions.

## Pre-publish Checklist

- [ ] Update version number in `pyproject.toml`
- [ ] Update `CHANGELOG.md` with release notes
- [ ] Run all tests: `pytest`
- [ ] Run linters: `black . && isort . && flake8`
- [ ] Update README.md if needed
- [ ] Verify LICENSE is correct (MIT)
- [ ] Check that all package data files are included

## Build Checklist

- [ ] Clean previous builds: `rm -rf dist/ build/ *.egg-info/`
- [ ] Build package: `python -m build`
- [ ] Verify build: `twine check dist/*`
- [ ] Check contents: `tar -tzf dist/renta-*.tar.gz`

## Test Checklist

- [ ] Install locally: `pip install -e .`
- [ ] Test imports: `python -c "from renta import RealEstateAnalyzer"`
- [ ] Run unit tests: `pytest -m unit`
- [ ] Upload to TestPyPI: `twine upload --repository testpypi dist/*`
- [ ] Install from TestPyPI and verify
- [ ] Test all core features work

## Production Upload Checklist

- [ ] Get PyPI API token from https://pypi.org/
- [ ] Configure `~/.pypirc` with token
- [ ] Upload to PyPI: `twine upload dist/*`
- [ ] Verify on https://pypi.org/project/renta/
- [ ] Install from PyPI: `pip install renta`
- [ ] Test installation works

## Post-publish Checklist

- [ ] Create GitHub release with tag `v0.1.0`
- [ ] Attach distribution files to release
- [ ] Update README.md with PyPI badge
- [ ] Announce release
- [ ] Monitor for issues

## Commands Quick Reference

```bash
# Clean and build
rm -rf dist/ build/ *.egg-info/
python -m build
twine check dist/*

# Upload to TestPyPI
twine upload --repository testpypi dist/*

# Upload to PyPI
twine upload dist/*

# Test installation
pip install --index-url https://test.pypi.org/simple/ renta  # TestPyPI
pip install renta  # Production PyPI
```
