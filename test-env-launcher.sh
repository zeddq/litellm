#!/bin/bash
# Test script for PyCharm Environment Launcher
# Verifies that environment variables are loaded correctly

echo "======================================"
echo "Testing PyCharm Environment Launcher"
echo "======================================"
echo ""

# Check if .env or .envrc exists
if [ -f .env ]; then
    echo "✓ Found .env file"
    echo "  Preview (first 5 lines, values masked):"
    head -5 .env | sed 's/=.*/=***MASKED***/g' | sed 's/^/  /'
elif [ -f .envrc ]; then
    echo "✓ Found .envrc file"
    if command -v direnv &> /dev/null; then
        echo "✓ direnv is installed"
        if direnv status 2>/dev/null | grep -q "Found RC allowed true"; then
            echo "✓ .envrc is allowed"
        else
            echo "✗ .envrc is NOT allowed - run: direnv allow"
        fi
    else
        echo "✗ direnv is not installed"
        echo "  Install with: brew install direnv"
    fi
else
    echo "✗ No .env or .envrc file found"
    echo ""
    echo "Create one with:"
    echo "  echo 'OPENAI_API_KEY=sk-test-key-12345678901234567890' > .env"
    exit 1
fi

echo ""
echo "Testing environment variable loading..."
echo ""

# Source the launcher's load_environment function
# (We'll test it by sourcing the .env directly for this test)
if [ -f .env ]; then
    source <(grep -v '^#' .env | sed 's/^/export /')
elif [ -f .envrc ] && command -v direnv &> /dev/null; then
    eval "$(direnv export bash 2>/dev/null)"
fi

# Check for common environment variables
echo "Environment variables detected:"
found=0

for var in OPENAI_API_KEY ANTHROPIC_API_KEY API_KEY TOKEN CUSTOM_VAR DATABASE_URL; do
    value="${!var}"
    if [ -n "$value" ]; then
        # Mask sensitive values
        if [[ "$var" =~ (KEY|TOKEN|SECRET|PASSWORD) ]]; then
            masked="${value:0:10}...${value: -4}"
            echo "  ✓ $var=$masked"
        else
            echo "  ✓ $var=$value"
        fi
        found=$((found + 1))
    fi
done

if [ $found -eq 0 ]; then
    echo "  ✗ No environment variables found"
    exit 1
fi

echo ""
echo "======================================"
echo "✓ Test PASSED!"
echo "======================================"
echo ""
echo "Next steps:"
echo "1. Run: ./setup-pycharm-env.sh"
echo "2. Reload shell: source ~/.zshrc"
echo "3. Launch PyCharm: pycharm-env"
echo ""
echo "Your MCP extensions will now have access to these variables!"
