# BottleSumo Test Suite

This directory contains structured tests for the BottleSumo project.

## Running tests

```bash
# Run all tests
pytest bottlesumo_pi/tests/

# Run with coverage
pytest bottlesumo_pi/tests/ --cov=bottlesumo_pi --cov-report=html

# Run specific test file
pytest bottlesumo_pi/tests/test_imports.py -v
```

## Test categories

- `test_imports.py` - Module import sanity checks
- `test_config.py` - Configuration validation
- *(more test files will be added in Integration Cycle #2)*
