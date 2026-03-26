default:
    just --list

# Install package in editable mode with all dev dependencies
install:
    uv pip install -e ".[dev,docs,notebook]"

# Run tests
test:
    pytest tests/ -v

# Run tests with coverage report
coverage:
    pytest tests/ --cov=shacl_bridges --cov-report=term-missing

# Serve docs locally
docs:
    mkdocs serve

# Build docs
docs-build:
    mkdocs build

# Run the worked example end-to-end
example:
    python examples/process_to_experiment/run_example.py

# Build the package
build:
    uv build

# Clean generated files
clean:
    rm -rf dist/ site/ .pytest_cache/ htmlcov/
    find . -type d -name __pycache__ -exec rm -rf {} +
    find . -name "*.pyc" -delete
