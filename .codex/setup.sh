#!/bin/bash
set -euo pipefail

##############################################################################
# Codex Universal Poetry Setup Orchestrator
#
# This script intelligently sets up Poetry in Codex Universal Docker with
# MITM proxy SSL handling. It tries multiple approaches in order of simplicity.
##############################################################################

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "╔════════════════════════════════════════════════════════════════════╗"
echo "║  Codex Universal Poetry Setup                                      ║"
echo "║  Python 3.13+ with MITM Proxy SSL Handling                        ║"
echo "╚════════════════════════════════════════════════════════════════════╝"
echo ""

# Function to print colored status messages
print_status() {
    local status=$1
    local message=$2
    case $status in
        "info")    echo "ℹ️  $message" ;;
        "success") echo "✅ $message" ;;
        "warning") echo "⚠️  $message" ;;
        "error")   echo "❌ $message" ;;
        "step")    echo "📋 $message" ;;
    esac
}

# Function to check if Poetry is working
test_poetry() {
    print_status "info" "Testing Poetry installation..."

    if poetry --version >/dev/null 2>&1; then
        print_status "success" "Poetry is installed: $(poetry --version)"
        return 0
    else
        print_status "error" "Poetry is not installed or not in PATH"
        return 1
    fi
}

# Function to test if we can resolve packages
test_package_resolution() {
    print_status "info" "Testing package resolution..."

    # Try to do a dry-run install of a small package
    if timeout 30 pip install --dry-run httpx >/dev/null 2>&1; then
        print_status "success" "Package resolution working"
        return 0
    else
        print_status "warning" "Package resolution failed"
        return 1
    fi
}

# Function to test mirror accessibility
test_mirrors() {
    print_status "info" "Testing PyPI mirror accessibility..."

    local mirrors=(
        "https://mirrors.aliyun.com/pypi/simple/:Aliyun"
        "https://mirrors.cloud.tencent.com/pypi/simple/:Tencent"
        "https://pypi.tuna.tsinghua.edu.cn/simple/:Tsinghua"
    )

    for mirror_info in "${mirrors[@]}"; do
        IFS=':' read -r url name <<< "$mirror_info"
        if curl -s --connect-timeout 3 -I "$url" >/dev/null 2>&1; then
            print_status "success" "$name mirror accessible"
            return 0
        fi
    done

    print_status "warning" "No accessible mirrors found"
    return 1
}

##############################################################################
# Main Setup Process
##############################################################################

print_status "step" "Step 1: Environment Check"
echo ""

# Check Python version
PYTHON_VERSION=$(python3 --version 2>&1 | grep -oP '\d+\.\d+' || echo "unknown")
print_status "info" "Python version: $PYTHON_VERSION"

# Check if we're in Codex environment
if [ -n "${CODEX_PROXY_CERT:-}" ] || [ -f "/usr/local/share/ca-certificates/envoy-mitmproxy-ca-cert.crt" ]; then
    print_status "success" "Codex Universal environment detected"
    IN_CODEX=true
else
    print_status "warning" "Not in Codex environment (no proxy cert found)"
    IN_CODEX=false
fi

echo ""
print_status "step" "Step 2: Choose Setup Strategy"
echo ""

STRATEGY="unknown"

# Strategy 1: Try mirrors first (simplest, no SSL issues)
if test_mirrors; then
    print_status "info" "Strategy: Use PyPI mirrors (no SSL complications)"
    STRATEGY="mirrors"
elif $IN_CODEX; then
    print_status "info" "Strategy: SSL patching for MITM proxy"
    STRATEGY="ssl_patch"
else
    print_status "info" "Strategy: Standard setup (no special handling needed)"
    STRATEGY="standard"
fi

echo ""
print_status "step" "Step 3: Run Setup"
echo ""

case $STRATEGY in
    "mirrors")
        print_status "info" "Running mirror-based setup..."
        if bash "$SCRIPT_DIR/setup_poetry_mirrors.sh"; then
            print_status "success" "Mirror setup completed successfully!"
            SETUP_SUCCESS=true
        else
            print_status "warning" "Mirror setup failed, trying SSL patch approach..."
            STRATEGY="ssl_patch"
            SETUP_SUCCESS=false
        fi
        ;;

    "ssl_patch")
        print_status "info" "Running SSL patch setup..."
        if bash "$SCRIPT_DIR/fixed_setup_poetry.sh"; then
            print_status "success" "SSL patch setup completed successfully!"
            SETUP_SUCCESS=true
        else
            print_status "error" "SSL patch setup failed"
            SETUP_SUCCESS=false
        fi
        ;;

    "standard")
        print_status "info" "Running standard Poetry install..."
        if poetry install --no-interaction --no-root --all-groups; then
            print_status "success" "Standard setup completed successfully!"
            SETUP_SUCCESS=true
        else
            print_status "error" "Standard setup failed"
            SETUP_SUCCESS=false
        fi
        ;;

    *)
        print_status "error" "Unknown strategy"
        SETUP_SUCCESS=false
        ;;
esac

# If mirror approach failed, try SSL patch
if [ "$STRATEGY" = "mirrors" ] && [ "$SETUP_SUCCESS" = false ]; then
    echo ""
    print_status "info" "Attempting SSL patch as fallback..."
    if bash "$SCRIPT_DIR/fixed_setup_poetry.sh"; then
        print_status "success" "SSL patch setup completed successfully!"
        SETUP_SUCCESS=true
    else
        print_status "error" "All setup strategies failed"
        SETUP_SUCCESS=false
    fi
fi

echo ""
print_status "step" "Step 4: Verification"
echo ""

if [ "$SETUP_SUCCESS" = true ]; then
    # Verify Poetry is working
    if test_poetry; then
        print_status "success" "Poetry verification passed"
    else
        print_status "warning" "Poetry installed but verification failed"
    fi

    # Verify package resolution
    if test_package_resolution; then
        print_status "success" "Package resolution verification passed"
    else
        print_status "warning" "Package resolution may have issues"
    fi

    # Test Python imports
    print_status "info" "Testing Python imports..."
    if python3 -c "import sys; print(f'Python {sys.version}')" 2>/dev/null; then
        print_status "success" "Python imports working"
    fi

    echo ""
    echo "╔════════════════════════════════════════════════════════════════════╗"
    echo "║  ✅ Setup Complete!                                                ║"
    echo "╚════════════════════════════════════════════════════════════════════╝"
    echo ""
    print_status "info" "Strategy used: $STRATEGY"
    print_status "info" "You can now use Poetry normally:"
    echo "    poetry install"
    echo "    poetry add <package>"
    echo "    poetry run python your_script.py"
    echo ""

    exit 0
else
    echo ""
    echo "╔════════════════════════════════════════════════════════════════════╗"
    echo "║  ❌ Setup Failed                                                   ║"
    echo "╚════════════════════════════════════════════════════════════════════╝"
    echo ""
    print_status "error" "All setup strategies failed"
    print_status "info" "For troubleshooting, run:"
    echo "    bash $SCRIPT_DIR/diagnose_poetry_ssl.sh"
    echo ""
    print_status "info" "Check the logs above for specific errors"
    echo ""

    exit 1
fi
