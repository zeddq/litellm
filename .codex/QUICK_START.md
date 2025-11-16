# Quick Start Guide

## TL;DR

```bash
# Run this in your Codex cloud startup script:
bash .codex/setup.sh
```

That's it! The script automatically:
- ✅ Detects your environment
- ✅ Tests mirror accessibility
- ✅ Chooses the best approach
- ✅ Configures Poetry and pip
- ✅ Handles SSL certificates
- ✅ Falls back if something fails

## What Gets Created

The setup creates/modifies:
- `~/.config/pip/pip.conf` - pip configuration
- `~/.cache/pypoetry/config.toml` - Poetry settings
- `{python}/site-packages/sitecustomize.py` - SSL patch (if needed)
- Environment variables for SSL handling

## Verification

After setup completes, verify everything works:

```bash
# Check Poetry
poetry --version
poetry show

# Check Python imports
python3 -c "import ssl; print('✅ SSL working')"

# Install dependencies
poetry install --all-groups
```

## Troubleshooting

If setup fails:

```bash
# Run diagnostics
bash .codex/diagnose_poetry_ssl.sh

# Test SSL patch
python3 .codex/test_ssl_patch.py

# Try manual approaches
bash .codex/setup_poetry_mirrors.sh    # Try mirrors
bash .codex/fixed_setup_poetry.sh      # Try SSL patching
```

## Files in This Directory

| File | Purpose |
|------|---------|
| `setup.sh` | 🎯 Main orchestrator (use this) |
| `fixed_setup_poetry.sh` | SSL patching approach |
| `setup_poetry_mirrors.sh` | PyPI mirrors approach |
| `diagnose_poetry_ssl.sh` | Diagnostic tool |
| `test_ssl_patch.py` | SSL verification test |
| `README.md` | Full documentation |
| `INTEGRATION_EXAMPLE.md` | Integration examples |
| `QUICK_START.md` | This file |

## Common Use Cases

### In Codex Cloud Startup Script
```bash
#!/bin/bash
set -euo pipefail
bash .codex/setup.sh
poetry install --all-groups
```

### Local Testing
```bash
docker run --rm -it \
    -v $(pwd):/workspace \
    -w /workspace \
    ghcr.io/openai/codex-universal:latest \
    bash .codex/setup.sh
```

### CI/CD
```bash
# In your CI script
bash .codex/setup.sh || exit 1
poetry install --all-groups
poetry run pytest
```

## Getting Help

1. Check `README.md` for detailed docs
2. Run `diagnose_poetry_ssl.sh` for diagnostics
3. Review `INTEGRATION_EXAMPLE.md` for examples

---

**Ready to go?** Just run: `bash .codex/setup.sh`
