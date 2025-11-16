# Codex Universal Docker Setup Scripts

This directory contains scripts to configure Poetry and Python dependencies in the Codex Universal Docker environment with MITM proxy SSL handling.

## Problem

The Codex Universal Docker image uses an MITM proxy that intercepts HTTPS traffic. Python 3.13+ has stricter SSL verification (`VERIFY_X509_STRICT` and `VERIFY_X509_PARTIAL_CHAIN` flags) that rejects the proxy's certificate, causing Poetry installations to fail with SSL errors.

## Scripts

### 1. `setup.sh` (Main Entry Point)
**Recommended:** Use this script from your Codex cloud setup script.

```bash
bash .codex/setup.sh
```

This orchestrator script:
- Runs diagnostics
- Tries the mirror approach first (simplest)
- Falls back to SSL patching if mirrors fail
- Provides clear status reporting

### 2. `fixed_setup_poetry.sh` (SSL Patching Approach)
**Use when:** Official PyPI access is required or mirrors are blocked.

```bash
bash .codex/fixed_setup_poetry.sh
```

What it does:
- Creates `sitecustomize.py` to globally patch Python's SSL module
- Disables `VERIFY_X509_STRICT` and `VERIFY_X509_PARTIAL_CHAIN` flags
- Configures pip to trust the proxy certificate
- Configures Poetry to use pip underneath
- Falls back to direct pip if Poetry fails

### 3. `setup_poetry_mirrors.sh` (Mirror Approach)
**Use when:** Chinese PyPI mirrors are accessible and preferred.

```bash
bash .codex/setup_poetry_mirrors.sh
```

What it does:
- Tests accessibility of Aliyun, Tencent, Tsinghua, Douban mirrors
- Selects the first accessible mirror
- Configures Poetry and pip to use the mirror
- Bypasses SSL issues entirely

### 4. `diagnose_poetry_ssl.sh` (Diagnostic Tool)
**Use for:** Troubleshooting and understanding your environment.

```bash
bash .codex/diagnose_poetry_ssl.sh
```

Provides detailed report on:
- Python and Poetry versions
- Environment variables (proxy, SSL certificates)
- Certificate file status
- System CA trust configuration
- sitecustomize.py status
- Poetry and pip configuration
- Network connectivity to PyPI and mirrors
- Test installations

### 5. `test_ssl_patch.py` (SSL Verification Test)
**Use for:** Verifying SSL patching is working correctly.

```bash
python3 .codex/test_ssl_patch.py
```

Tests:
- SSL module configuration
- sitecustomize.py loading
- SSL context flags (VERIFY_X509_STRICT, etc.)
- Certificate loading
- urllib connectivity

## Quick Start

### Option 1: Use the orchestrator (Recommended)
```bash
bash .codex/setup.sh
```

### Option 2: Manual approach selection
```bash
# First, diagnose your environment
bash .codex/diagnose_poetry_ssl.sh

# Then choose based on output:

# If mirrors are accessible:
bash .codex/setup_poetry_mirrors.sh

# If mirrors are blocked:
bash .codex/fixed_setup_poetry.sh
```

## Integration with Codex Cloud

Add this to your Codex cloud setup script (typically `.codex/setup.sh` or similar):

```bash
#!/bin/bash
set -euo pipefail

# Run the Poetry setup
bash .codex/setup.sh

# Continue with your application setup...
```

## Troubleshooting

### SSL errors persist after running scripts
```bash
# Check if sitecustomize.py has syntax errors
python3 -c "import sitecustomize"

# View detailed diagnostics
bash .codex/diagnose_poetry_ssl.sh

# Test SSL patching
python3 .codex/test_ssl_patch.py
```

### Poetry lock fails
```bash
# Try deleting and regenerating lock file (Poetry 2.x compatible)
rm -f poetry.lock
poetry lock

# Or use pip directly
poetry export -f requirements.txt --output requirements.txt --without-hashes
pip install -r requirements.txt
```

### Network timeouts
```bash
# Increase timeout in pip config
cat >> ~/.config/pip/pip.conf << EOF
[global]
timeout = 120
EOF

# Increase Poetry timeout
poetry config installer.max-workers 1
```

## Environment Variables

These are automatically set by the scripts, but you can override them:

```bash
# Proxy configuration
export HTTP_PROXY="http://proxy:8080"
export HTTPS_PROXY="http://proxy:8080"

# SSL certificate paths
export SSL_CERT_FILE="/usr/local/share/ca-certificates/envoy-mitmproxy-ca-cert.crt"
export CODEX_PROXY_CERT="/usr/local/share/ca-certificates/envoy-mitmproxy-ca-cert.crt"
export REQUESTS_CA_BUNDLE="$SSL_CERT_FILE"
export CURL_CA_BUNDLE="$SSL_CERT_FILE"

# Silence warnings
export PYTHONWARNINGS="ignore:Unverified HTTPS request"
```

## How It Works

### SSL Patching Approach
1. **sitecustomize.py**: Automatically loaded by Python on every invocation
2. **Monkey-patches** `ssl.create_default_context()` to disable strict flags
3. **Loads proxy certificate** into SSL context
4. **Poetry uses patched SSL** when installing packages

### Mirror Approach
1. **Tests connectivity** to various PyPI mirrors
2. **Configures Poetry and pip** to use accessible mirror
3. **Bypasses MITM proxy** entirely (mirrors may not route through it)

## Files Modified

The scripts modify these files:
- `~/.config/pip/pip.conf` - pip configuration
- `~/.cache/pypoetry/config.toml` - Poetry configuration
- `/path/to/python/site-packages/sitecustomize.py` - Global SSL patch
- `/etc/ssl/certs/` - System CA trust store (if needed)

## References

- [Python 3.13 SSL Changes Discussion](https://discuss.python.org/t/python-3-13-x-ssl-security-changes/91266)
- [Poetry SSL Issues](https://github.com/python-poetry/poetry/issues/6670)
- [Codex Universal Docker](https://github.com/openai/codex-universal)

## Support

If issues persist:
1. Run `bash .codex/diagnose_poetry_ssl.sh` and save output
2. Check for syntax errors in generated files
3. Verify proxy certificate exists and is valid
4. Try both approaches (mirrors and SSL patching)

---

**Last Updated:** 2025-11-16
**Python Version:** 3.13+
**Codex Universal:** Compatible
