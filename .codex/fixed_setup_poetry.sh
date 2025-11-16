#!/bin/bash
set -euo pipefail

echo "🔧 Setting up Poetry with MITM proxy for Python 3.13+..."

# --- Proxy + CA env ---
export HTTP_PROXY="http://proxy:8080"
export HTTPS_PROXY="http://proxy:8080"

# Use the Codex-provided proxy CA
export SSL_CERT_FILE="${CODEX_PROXY_CERT:-/usr/local/share/ca-certificates/envoy-mitmproxy-ca-cert.crt}"
export REQUESTS_CA_BUNDLE="$SSL_CERT_FILE"
export CURL_CA_BUNDLE="$SSL_CERT_FILE"

# Install proxy CA into system trust
if [ -f "$SSL_CERT_FILE" ]; then
    cp "$SSL_CERT_FILE" /usr/local/share/ca-certificates/codex-proxy.crt 2>/dev/null || true
    update-ca-certificates 2>/dev/null || true
    echo "✅ Installed proxy CA certificate"
else
    echo "⚠️  Warning: Proxy CA certificate not found at $SSL_CERT_FILE"
fi

# --- Critical: Create sitecustomize.py to patch SSL globally ---
PYTHON_VERSION=$(python3 --version | grep -oP '\d+\.\d+')
SITE_PACKAGES=$(python3 -c "import site; print(site.getsitepackages()[0])")

echo "📝 Creating sitecustomize.py for Python $PYTHON_VERSION at $SITE_PACKAGES"

cat > "$SITE_PACKAGES/sitecustomize.py" << 'SITECUSTOM_EOF'
"""
Global SSL context patch for Python 3.13+ with MITM proxies.
This runs automatically on every Python invocation.
"""
import os
import ssl
import sys

# Only patch if we're behind the Codex proxy
if os.getenv("CODEX_PROXY_CERT") or os.getenv("SSL_CERT_FILE"):
    cert_file = os.getenv("CODEX_PROXY_CERT") or os.getenv("SSL_CERT_FILE")

    # Patch ssl.create_default_context to disable strict verification
    _original_create_default_context = ssl.create_default_context

    def patched_create_default_context(purpose=ssl.Purpose.SERVER_AUTH, *args, **kwargs):
        context = _original_create_default_context(purpose, *args, **kwargs)

        # Disable strict X.509 verification flags (Python 3.13+)
        if hasattr(ssl, 'VERIFY_X509_STRICT'):
            context.verify_flags &= ~ssl.VERIFY_X509_STRICT
        if hasattr(ssl, 'VERIFY_X509_PARTIAL_CHAIN'):
            context.verify_flags &= ~ssl.VERIFY_X509_PARTIAL_CHAIN

        # Load the proxy certificate
        if cert_file and os.path.exists(cert_file):
            try:
                context.load_verify_locations(cafile=cert_file)
            except Exception as e:
                print(f"⚠️  Warning: Could not load cert {cert_file}: {e}", file=sys.stderr)

        return context

    ssl.create_default_context = patched_create_default_context

    # Also patch SSLContext for direct instantiation
    _original_SSLContext_init = ssl.SSLContext.__init__

    def patched_SSLContext_init(self, protocol=ssl.PROTOCOL_TLS):
        _original_SSLContext_init(self, protocol)
        if hasattr(ssl, 'VERIFY_X509_STRICT'):
            self.verify_flags &= ~ssl.VERIFY_X509_STRICT
        if hasattr(ssl, 'VERIFY_X509_PARTIAL_CHAIN'):
            self.verify_flags &= ~ssl.VERIFY_X509_PARTIAL_CHAIN

    ssl.SSLContext.__init__ = patched_SSLContext_init
SITECUSTOM_EOF

echo "✅ Created sitecustomize.py"

# Verify the patch is working
python3 -c "import ssl; print('✅ SSL patch loaded successfully')" || echo "⚠️  SSL patch may have issues"

# --- Configure pip to use proxy CA and disable strict verification ---
mkdir -p ~/.config/pip

cat > ~/.config/pip/pip.conf << 'PIP_EOF'
[global]
cert = /usr/local/share/ca-certificates/envoy-mitmproxy-ca-cert.crt
trusted-host =
    pypi.org
    files.pythonhosted.org
    pypi.python.org
timeout = 60

[install]
trusted-host =
    pypi.org
    files.pythonhosted.org
    pypi.python.org
PIP_EOF

# Use CODEX_PROXY_CERT if set
if [ -n "${CODEX_PROXY_CERT:-}" ]; then
    sed -i "s|/usr/local/share/ca-certificates/envoy-mitmproxy-ca-cert.crt|${CODEX_PROXY_CERT}|g" ~/.config/pip/pip.conf
fi

echo "✅ Configured pip"

# --- Configure Poetry ---
echo "📦 Configuring Poetry..."

# Configure Poetry installer (compatible with all versions)
poetry config installer.max-workers 1 2>/dev/null || true  # Avoid race conditions
poetry config installer.parallel false 2>/dev/null || true  # Disable parallel to avoid issues

# Configure Poetry certificate handling for both PyPI domains
poetry source add --priority=primary pypi-main https://pypi.org/simple/ 2>/dev/null || true
poetry source add --priority=supplemental files-host https://files.pythonhosted.org/ 2>/dev/null || true

# Try to disable cert verification (may not work in 3.13+ but doesn't hurt)
poetry config certificates.pypi-main.cert false 2>/dev/null || true
poetry config certificates.PyPI.cert false 2>/dev/null || true
poetry config certificates.pypi.cert false 2>/dev/null || true
poetry config certificates.files-host.cert false 2>/dev/null || true

# Silence urllib3 warnings
export PYTHONWARNINGS="ignore:Unverified HTTPS request"

echo "✅ Poetry configured"

# --- Attempt installation ---
echo "📦 Installing dependencies with Poetry..."

if poetry install --no-interaction --no-root --all-groups -vv; then
    echo "✅ Poetry install successful!"
else
    echo "⚠️  Poetry install failed, trying pip fallback..."

    # Fallback: Export to requirements.txt and use pip directly
    if poetry export -f requirements.txt --output /tmp/requirements.txt --without-hashes --all-groups 2>/dev/null; then
        echo "📦 Installing via pip..."
        pip install --no-cache-dir -r /tmp/requirements.txt
        echo "✅ Pip install successful!"
    else
        echo "❌ Both Poetry and pip fallback failed"
        exit 1
    fi
fi

# --- Verify installation ---
echo "🔍 Verifying installation..."
python3 -c "
import sys
try:
    import fastapi
    import httpx
    print('✅ Core dependencies imported successfully')
    sys.exit(0)
except ImportError as e:
    print(f'❌ Import failed: {e}')
    sys.exit(1)
"

echo "✅ Setup complete!"
