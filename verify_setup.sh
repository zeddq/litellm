#!/bin/bash
# Verification Script for Binary-Based LiteLLM Architecture
# This script checks that everything is set up correctly

set -e

echo "========================================"
echo "LiteLLM Binary Architecture Verification"
echo "========================================"
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check 1: LiteLLM binary exists
echo "1. Checking LiteLLM binary..."
if command -v litellm &> /dev/null; then
    echo -e "${GREEN}✓${NC} LiteLLM binary found: $(which litellm)"
else
    echo -e "${RED}✗${NC} LiteLLM binary not found"
    echo "   Install with: pip install litellm"
    exit 1
fi

# Check 2: Config file exists
echo ""
echo "2. Checking config.yaml..."
if [ -f "config.yaml" ]; then
    echo -e "${GREEN}✓${NC} config.yaml found"
else
    echo -e "${RED}✗${NC} config.yaml not found"
    exit 1
fi

# Check 3: Python dependencies
echo ""
echo "3. Checking Python dependencies..."
python3 -c "import fastapi, httpx, uvicorn, yaml" 2>/dev/null
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓${NC} Required Python packages installed"
else
    echo -e "${RED}✗${NC} Missing Python packages"
    echo "   Run: poetry install"
    exit 1
fi

# Check 4: Memory router module
echo ""
echo "4. Checking memory_router module..."
if [ -f "memory_router.py" ]; then
    echo -e "${GREEN}✓${NC} memory_router.py found"
else
    echo -e "${RED}✗${NC} memory_router.py not found"
    exit 1
fi

# Check 5: Start script
echo ""
echo "5. Checking start_proxies.py..."
if [ -f "start_proxies.py" ]; then
    echo -e "${GREEN}✓${NC} start_proxies.py found"
else
    echo -e "${RED}✗${NC} start_proxies.py not found"
    exit 1
fi

# Check 6: Environment variables
echo ""
echo "6. Checking environment variables..."
if [ -n "$OPENAI_API_KEY" ]; then
    echo -e "${GREEN}✓${NC} OPENAI_API_KEY is set"
else
    echo -e "${YELLOW}⚠${NC} OPENAI_API_KEY not set (may be required)"
fi

if [ -n "$ANTHROPIC_API_KEY" ]; then
    echo -e "${GREEN}✓${NC} ANTHROPIC_API_KEY is set"
else
    echo -e "${YELLOW}⚠${NC} ANTHROPIC_API_KEY not set (may be required)"
fi

if [ -n "$SUPERMEMORY_API_KEY" ]; then
    echo -e "${GREEN}✓${NC} SUPERMEMORY_API_KEY is set"
else
    echo -e "${YELLOW}⚠${NC} SUPERMEMORY_API_KEY not set (optional)"
fi

# Check 7: Port availability
echo ""
echo "7. Checking port availability..."
if ! lsof -i :8765 &> /dev/null; then
    echo -e "${GREEN}✓${NC} Port 8765 (LiteLLM) is available"
else
    echo -e "${YELLOW}⚠${NC} Port 8765 is in use"
    echo "   Process: $(lsof -i :8765 | tail -n 1)"
fi

if ! lsof -i :8764 &> /dev/null; then
    echo -e "${GREEN}✓${NC} Port 8764 (Memory Proxy) is available"
else
    echo -e "${YELLOW}⚠${NC} Port 8764 is in use"
    echo "   Process: $(lsof -i :8764 | tail -n 1)"
fi

# Check 8: Test LiteLLM binary
echo ""
echo "8. Testing LiteLLM binary..."
litellm --help &> /dev/null
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓${NC} LiteLLM binary is functional"
else
    echo -e "${RED}✗${NC} LiteLLM binary test failed"
    exit 1
fi

# Summary
echo ""
echo "========================================"
echo -e "${GREEN}✓ All checks passed!${NC}"
echo "========================================"
echo ""
echo "Next steps:"
echo "1. Set required API keys (if not already set):"
echo "   export OPENAI_API_KEY='sk-...'"
echo "   export ANTHROPIC_API_KEY='sk-ant-...'"
echo ""
echo "2. Start the proxies:"
echo "   poetry run start-proxies"
echo ""
echo "3. Test the setup:"
echo "   curl http://localhost:8765/health  # LiteLLM"
echo "   curl http://localhost:8764/health  # Memory Proxy"
echo ""