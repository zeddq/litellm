# Integration Example for Codex Cloud

This document shows how to integrate the Poetry setup scripts into your Codex cloud environment.

## Option 1: Simple Integration (Recommended)

Create or modify your Codex cloud startup script to call the orchestrator:

```bash
#!/bin/bash
set -euo pipefail

echo "Starting Codex environment setup..."

# Run Poetry setup (handles SSL and mirrors automatically)
bash .codex/setup.sh

# Your application-specific setup continues here...
poetry install --all-groups

echo "Environment ready!"
```

## Option 2: Custom Integration with Error Handling

For more control over the setup process:

```bash
#!/bin/bash
set -euo pipefail

echo "Starting Codex environment setup..."

# Run Poetry setup with error handling
if bash .codex/setup.sh; then
    echo "✅ Poetry setup successful"
else
    echo "❌ Poetry setup failed"
    echo "Running diagnostics..."
    bash .codex/diagnose_poetry_ssl.sh
    exit 1
fi

# Install project dependencies
echo "Installing project dependencies..."
poetry install --no-interaction --all-groups

# Verify critical imports
echo "Verifying critical imports..."
poetry run python -c "
import fastapi
import httpx
import litellm
print('✅ All critical imports successful')
"

echo "✅ Environment ready!"
```

## Option 3: Manual Strategy Selection

If you want to control which approach to use:

```bash
#!/bin/bash
set -euo pipefail

echo "Starting Codex environment setup..."

# Choose your strategy:
# Option A: Try mirrors first (simplest)
if bash .codex/setup_poetry_mirrors.sh; then
    echo "✅ Mirror setup successful"
# Option B: Fallback to SSL patching
elif bash .codex/fixed_setup_poetry.sh; then
    echo "✅ SSL patch setup successful"
else
    echo "❌ All setup approaches failed"
    bash .codex/diagnose_poetry_ssl.sh
    exit 1
fi

# Continue with your setup...
poetry install --all-groups

echo "✅ Environment ready!"
```

## Environment Variables

These are automatically configured by the scripts, but you can override them:

```bash
# Optional: Override proxy settings
export HTTP_PROXY="http://custom-proxy:8080"
export HTTPS_PROXY="http://custom-proxy:8080"

# Optional: Override certificate path
export CODEX_PROXY_CERT="/path/to/your/cert.crt"
export SSL_CERT_FILE="$CODEX_PROXY_CERT"

# Run setup
bash .codex/setup.sh
```

## Troubleshooting in Codex Cloud

If setup fails in Codex cloud:

### 1. Run Diagnostics
Add this to your startup script:
```bash
bash .codex/diagnose_poetry_ssl.sh > /tmp/poetry-diagnostics.log 2>&1
cat /tmp/poetry-diagnostics.log
```

### 2. Enable Verbose Logging
```bash
# Enable Poetry verbose output
export POETRY_VERBOSE=true

# Enable pip verbose output
export PIP_VERBOSE=true

# Run setup with full output
bash .codex/setup.sh 2>&1 | tee /tmp/setup.log
```

### 3. Test SSL Patching
```bash
# Test if SSL patch is working
python3 .codex/test_ssl_patch.py

# Test Poetry can access PyPI
poetry search httpx --no-interaction
```

### 4. Manual Fallback
If all automated approaches fail:
```bash
# Export requirements and use pip directly
poetry export -f requirements.txt --output /tmp/requirements.txt --without-hashes
pip install -r /tmp/requirements.txt
```

## CI/CD Integration

For automated builds in Codex cloud:

```yaml
# Example GitHub Actions workflow
name: Deploy to Codex

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Setup Codex Environment
        run: |
          # Your Codex cloud deployment commands here
          # The .codex/setup.sh will run automatically in the container

      - name: Verify Setup
        run: |
          poetry --version
          poetry show
```

## Performance Considerations

The orchestrator script typically takes:
- **Mirror approach**: 10-30 seconds
- **SSL patch approach**: 20-45 seconds
- **Diagnostics**: 5-15 seconds

To optimize:
```bash
# Skip diagnostics in production
export SKIP_DIAGNOSTICS=true
bash .codex/setup.sh

# Use cached dependencies
poetry install --no-interaction --no-root --only-root --no-cache
```

## Maintenance

### Updating Scripts
To update the setup scripts:
```bash
git pull origin main
chmod +x .codex/*.sh
```

### Testing Changes Locally
Before pushing to Codex cloud:
```bash
# Test in Docker locally
docker run --rm -it \
    -v $(pwd):/workspace \
    -w /workspace \
    ghcr.io/openai/codex-universal:latest \
    bash .codex/setup.sh
```

## Support

If you encounter issues:
1. Check `.codex/README.md` for detailed documentation
2. Run `.codex/diagnose_poetry_ssl.sh` for diagnostics
3. Review logs from the setup script
4. Open an issue with the diagnostic output

---

**Last Updated:** 2025-11-16
