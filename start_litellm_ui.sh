#!/bin/bash
# Start LiteLLM Binary Proxy with Admin UI

# Load environment
source .envrc

echo "🚀 Starting LiteLLM Proxy with Admin UI..."
echo ""
echo "Configuration:"
echo "  - Port: 8765"
echo "  - Config: config/config.yaml"
echo "  - Database: PostgreSQL (localhost:5432/litellm)"
echo "  - Admin UI: http://localhost:8765/ui"
echo ""
echo "Login credentials:"
echo "  - Username: $UI_USERNAME"
echo "  - Password: $UI_PASSWORD"
echo ""

# Start LiteLLM
litellm --config config/config.yaml --port 8765 --detailed_debug
