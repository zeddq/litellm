#!/bin/bash
set -euo pipefail

echo "======================================================================"
echo "Poetry SSL Diagnostic Script for Codex Universal + Python 3.13+"
echo "======================================================================"
echo ""

# --- Environment ---
echo "📋 Environment Information:"
echo "  Python version: $(python3 --version)"
echo "  Poetry version: $(poetry --version 2>/dev/null || echo 'NOT INSTALLED')"
echo "  Pip version: $(pip --version 2>/dev/null || echo 'NOT INSTALLED')"
echo ""

# --- Environment Variables ---
echo "🔧 Environment Variables:"
echo "  HTTP_PROXY: ${HTTP_PROXY:-NOT SET}"
echo "  HTTPS_PROXY: ${HTTPS_PROXY:-NOT SET}"
echo "  SSL_CERT_FILE: ${SSL_CERT_FILE:-NOT SET}"
echo "  CODEX_PROXY_CERT: ${CODEX_PROXY_CERT:-NOT SET}"
echo "  REQUESTS_CA_BUNDLE: ${REQUESTS_CA_BUNDLE:-NOT SET}"
echo "  CURL_CA_BUNDLE: ${CURL_CA_BUNDLE:-NOT SET}"
echo ""

# --- Certificate Files ---
echo "📜 Certificate Files:"
CERT_FILE="${CODEX_PROXY_CERT:-${SSL_CERT_FILE:-/usr/local/share/ca-certificates/envoy-mitmproxy-ca-cert.crt}}"
if [ -f "$CERT_FILE" ]; then
    echo "  ✅ Certificate exists: $CERT_FILE"
    echo "  File size: $(stat -c%s "$CERT_FILE" 2>/dev/null || stat -f%z "$CERT_FILE") bytes"
    echo "  Certificate info:"
    openssl x509 -in "$CERT_FILE" -noout -subject -issuer 2>/dev/null | sed 's/^/    /' || echo "    Could not parse certificate"
else
    echo "  ❌ Certificate NOT found: $CERT_FILE"
fi
echo ""

# --- System CA Trust ---
echo "🔐 System CA Trust:"
if [ -d /etc/ssl/certs ]; then
    CERT_COUNT=$(ls -1 /etc/ssl/certs/*.pem 2>/dev/null | wc -l)
    echo "  System CA certificates: $CERT_COUNT"
    if [ -f /usr/local/share/ca-certificates/codex-proxy.crt ]; then
        echo "  ✅ Codex proxy cert installed in system trust"
    else
        echo "  ⚠️  Codex proxy cert NOT in system trust"
    fi
else
    echo "  ⚠️  /etc/ssl/certs not found"
fi
echo ""

# --- Python SSL Module ---
echo "🐍 Python SSL Module:"
python3 << 'PYEOF'
import ssl
import sys

print(f"  OpenSSL version: {ssl.OPENSSL_VERSION}")
print(f"  SSL module version: {ssl.OPENSSL_VERSION_INFO}")

# Check for Python 3.13+ flags
if hasattr(ssl, 'VERIFY_X509_STRICT'):
    print("  ✅ VERIFY_X509_STRICT available (Python 3.13+)")
else:
    print("  ℹ️  VERIFY_X509_STRICT not available (Python < 3.13)")

if hasattr(ssl, 'VERIFY_X509_PARTIAL_CHAIN'):
    print("  ✅ VERIFY_X509_PARTIAL_CHAIN available (Python 3.13+)")
else:
    print("  ℹ️  VERIFY_X509_PARTIAL_CHAIN not available (Python < 3.13)")

# Check default context
try:
    context = ssl.create_default_context()
    print(f"  Default context verify_flags: {context.verify_flags}")
except Exception as e:
    print(f"  ❌ Error creating default context: {e}")
PYEOF
echo ""

# --- sitecustomize.py ---
echo "📦 sitecustomize.py Status:"
SITE_PACKAGES=$(python3 -c "import site; print(site.getsitepackages()[0])")
SITECUSTOMIZE="$SITE_PACKAGES/sitecustomize.py"
if [ -f "$SITECUSTOMIZE" ]; then
    echo "  ✅ Found: $SITECUSTOMIZE"
    echo "  File size: $(stat -c%s "$SITECUSTOMIZE" 2>/dev/null || stat -f%z "$SITECUSTOMIZE") bytes"

    # Test if it loads
    if python3 -c "import sitecustomize" 2>/dev/null; then
        echo "  ✅ Loads successfully"
    else
        echo "  ❌ Import error (syntax issue?)"
        python3 -c "import sitecustomize" 2>&1 | head -5 | sed 's/^/    /'
    fi
else
    echo "  ⚠️  Not found: $SITECUSTOMIZE"
fi
echo ""

# --- pip Configuration ---
echo "🔧 pip Configuration:"
if [ -f ~/.config/pip/pip.conf ]; then
    echo "  ✅ Found: ~/.config/pip/pip.conf"
    echo "  Contents:"
    cat ~/.config/pip/pip.conf | sed 's/^/    /'
else
    echo "  ⚠️  Not found: ~/.config/pip/pip.conf"
fi
echo ""

# --- Poetry Configuration ---
echo "📚 Poetry Configuration:"
echo "  Poetry config directory: $(poetry config --list 2>/dev/null | grep 'cache-dir' | cut -d= -f2 | tr -d ' ' || echo 'UNKNOWN')"
echo ""
echo "  Poetry sources:"
poetry source show 2>/dev/null | sed 's/^/    /' || echo "    No sources configured"
echo ""
echo "  Poetry certificate settings:"
poetry config --list 2>/dev/null | grep -i cert | sed 's/^/    /' || echo "    No certificate settings"
echo ""
echo "  Poetry installer settings:"
poetry config installer.max-workers 2>/dev/null | sed 's/^/    max-workers: /' || echo "    max-workers: default"
poetry config installer.parallel 2>/dev/null | sed 's/^/    parallel: /' || echo "    parallel: default"
echo ""

# --- Network Connectivity ---
echo "🌐 Network Connectivity Tests:"

test_url() {
    local url=$1
    local name=$2
    printf "  %-30s " "$name:"

    if curl -s --connect-timeout 5 -I "$url" >/dev/null 2>&1; then
        echo "✅ Accessible"
        return 0
    else
        echo "❌ Blocked/Timeout"
        return 1
    fi
}

test_url "https://pypi.org/simple/" "PyPI (official)"
test_url "https://files.pythonhosted.org/" "PyPI files host"
test_url "https://mirrors.aliyun.com/pypi/simple/" "Aliyun mirror (China)"
test_url "https://mirrors.cloud.tencent.com/pypi/simple/" "Tencent mirror"
test_url "https://pypi.tuna.tsinghua.edu.cn/simple/" "Tsinghua mirror"
test_url "https://pypi.douban.com/simple/" "Douban mirror"
echo ""

# --- Test pip Install ---
echo "🧪 Test pip Install:"
echo "  Attempting to install a small package (pip-audit) with pip..."
if pip install --dry-run pip-audit 2>&1 | grep -q "Would install"; then
    echo "  ✅ pip can resolve dependencies"
else
    echo "  ❌ pip dependency resolution failed"
    echo "  Last error:"
    pip install --dry-run pip-audit 2>&1 | tail -5 | sed 's/^/    /'
fi
echo ""

# --- Test Poetry Lock ---
echo "🔒 Test Poetry Lock:"
if [ -f pyproject.toml ]; then
    echo "  Found pyproject.toml, testing poetry lock..."
    if timeout 30 poetry lock --check 2>&1 | head -10; then
        echo "  ✅ Poetry lock check passed"
    else
        echo "  ⚠️  Poetry lock check failed or timed out"
    fi
else
    echo "  ℹ️  No pyproject.toml found in current directory"
fi
echo ""

echo "======================================================================"
echo "Diagnostic complete!"
echo "======================================================================"
echo ""
echo "📋 Summary:"
echo "  If SSL errors occur, try one of these solutions:"
echo "    1. Use the sitecustomize.py approach (fixed_setup_poetry.sh)"
echo "    2. Use PyPI mirrors (setup_poetry_mirrors.sh)"
echo "    3. Disable Poetry modern installer + configure pip"
echo ""
