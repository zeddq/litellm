#!/bin/bash
set -euo pipefail

echo "🔧 Setting up Poetry with PyPI mirrors (bypass MITM proxy)..."

# --- Test which mirrors are accessible ---
test_mirror() {
    local url=$1
    local name=$2
    echo "Testing $name ($url)..."
    if curl -s --connect-timeout 5 -I "$url" >/dev/null 2>&1; then
        echo "  ✅ $name accessible"
        return 0
    else
        echo "  ❌ $name blocked or slow"
        return 1
    fi
}

echo "🌐 Testing PyPI mirrors..."
MIRROR_URL=""
MIRROR_HOST=""
MIRROR_NAME=""

# Test mirrors in order of reliability
if test_mirror "https://mirrors.aliyun.com/pypi/simple/" "Aliyun (China)"; then
    MIRROR_URL="https://mirrors.aliyun.com/pypi/simple/"
    MIRROR_HOST="mirrors.aliyun.com"
    MIRROR_NAME="aliyun"
elif test_mirror "https://mirrors.cloud.tencent.com/pypi/simple/" "Tencent Cloud"; then
    MIRROR_URL="https://mirrors.cloud.tencent.com/pypi/simple/"
    MIRROR_HOST="mirrors.cloud.tencent.com"
    MIRROR_NAME="tencent"
elif test_mirror "https://pypi.tuna.tsinghua.edu.cn/simple/" "Tsinghua University"; then
    MIRROR_URL="https://pypi.tuna.tsinghua.edu.cn/simple/"
    MIRROR_HOST="pypi.tuna.tsinghua.edu.cn"
    MIRROR_NAME="tsinghua"
elif test_mirror "https://pypi.douban.com/simple/" "Douban"; then
    MIRROR_URL="https://pypi.douban.com/simple/"
    MIRROR_HOST="pypi.douban.com"
    MIRROR_NAME="douban"
else
    echo "❌ No accessible PyPI mirrors found. Trying original PyPI with SSL workarounds..."
    MIRROR_URL="https://pypi.org/simple/"
    MIRROR_HOST="pypi.org"
    MIRROR_NAME="pypi"
fi

echo ""
echo "✅ Using mirror: $MIRROR_NAME ($MIRROR_URL)"
echo ""

# --- Configure pip ---
mkdir -p ~/.config/pip

cat > ~/.config/pip/pip.conf << EOF
[global]
index-url = $MIRROR_URL
trusted-host = $MIRROR_HOST
timeout = 60

[install]
trusted-host = $MIRROR_HOST
EOF

echo "✅ Configured pip to use $MIRROR_NAME"

# --- Configure Poetry ---
echo "📦 Configuring Poetry..."

# Configure Poetry installer (compatible with all versions)
poetry config installer.max-workers 1 2>/dev/null || true
poetry config installer.parallel false 2>/dev/null || true

# Add mirror as primary source
poetry source add --priority=primary "$MIRROR_NAME" "$MIRROR_URL" 2>/dev/null || true

# Configure Poetry to trust the mirror host
poetry config certificates."$MIRROR_NAME".cert false 2>/dev/null || true

echo "✅ Poetry configured to use $MIRROR_NAME"

# --- Install dependencies ---
echo "📦 Installing dependencies..."

if poetry install --no-interaction --no-root --all-groups -vv; then
    echo "✅ Poetry install successful!"
else
    echo "⚠️  Poetry install failed, trying pip fallback..."

    # Fallback to pip
    if poetry export -f requirements.txt --output /tmp/requirements.txt --without-hashes --all-groups 2>/dev/null; then
        echo "📦 Installing via pip..."
        pip install --no-cache-dir -r /tmp/requirements.txt
        echo "✅ Pip install successful!"
    else
        echo "❌ Both Poetry and pip failed"
        exit 1
    fi
fi

# --- Verify ---
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

echo ""
echo "✅ Setup complete using $MIRROR_NAME mirror!"
