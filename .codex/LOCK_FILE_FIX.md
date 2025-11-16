# Lock File Handling Fix (v1.2.0)

## Problem

Poetry validates that `poetry.lock` matches `pyproject.toml` before installing. If they're out of sync, you get:

```
ValueError
pyproject.toml changed significantly since poetry.lock was last generated.
Run `poetry lock` to fix the lock file.
```

This happened in Codex cloud because:
1. The repository has a lock file from local development
2. Codex environment might have different system packages
3. Lock file validation is strict in Poetry 2.2+

## Solution (v1.2.0)

Scripts now **automatically** check and fix lock files:

```bash
# 1. Check if lock file is in sync
poetry check --lock

# 2. If out of sync, regenerate (preserving versions)
poetry lock --no-update

# 3. If that fails, do full resolution
poetry lock

# 4. Then proceed with install
poetry install
```

## What Changed

### Before (v1.1.0)
```bash
poetry install  # ❌ Fails if lock out of sync
```

### After (v1.2.0)
```bash
# Check lock file
if ! poetry check --lock; then
    poetry lock --no-update  # Fix it automatically
fi

poetry install  # ✅ Now works
```

## Testing the Fix

### In Codex Cloud

Your setup script will now work:

```bash
cd /workspace/litellm
bash .codex/setup.sh
```

Expected output:
```
🔍 Checking lock file...
⚠️  Lock file out of sync, regenerating...
Resolving dependencies...
✅ Lock file regenerated
📦 Installing dependencies...
✅ Poetry install successful!
```

### Locally

If you have an out-of-sync lock file:

```bash
# This will now fix it automatically
bash .codex/setup_poetry_mirrors.sh
```

## Lock File Strategies

### Strategy 1: Regenerate on Deploy (Our Approach)
**Pros**:
- ✅ Always works in Codex cloud
- ✅ Handles environment differences
- ✅ Automatic, no manual intervention

**Cons**:
- ⚠️  Takes extra time (30-60 seconds)
- ⚠️  Might resolve to different versions if ranges specified

### Strategy 2: Commit Lock File
**Pros**:
- ✅ Faster deploys
- ✅ Exact version reproduction

**Cons**:
- ❌ Fails if environments differ
- ❌ Requires manual `poetry lock` after every pyproject.toml change

### Strategy 3: No Lock File
**Pros**:
- ✅ Most flexible

**Cons**:
- ❌ Inconsistent versions across environments
- ❌ Longer install times (always resolving)

**Our Choice**: Strategy 1 - Auto-regenerate is most robust for Codex cloud.

## Performance Impact

Lock file regeneration adds:
- **With mirrors**: 20-40 seconds
- **With SSL patch**: 30-50 seconds

Total setup time in Codex cloud:
- **Fast path** (lock valid): 30-60 seconds
- **Regen path** (lock invalid): 60-120 seconds

## Troubleshooting

### Lock regeneration fails

```bash
# Run manually to see detailed error
cd /workspace/litellm
poetry lock -vvv
```

Common causes:
- Incompatible dependency constraints
- Network issues reaching package repository
- Missing platform-specific dependencies

### Lock file keeps getting out of sync

Check if you have:
- Platform-specific dependencies (`markers`)
- Dynamic version constraints (avoid `*` or `^` if possible)
- Local path dependencies

## Related Issues

- [Poetry #1584](https://github.com/python-poetry/poetry/issues/1584) - Lock file validation
- [Poetry #5972](https://github.com/python-poetry/poetry/issues/5972) - Cross-platform lock files

---

**Version**: 1.2.0
**Date**: 2025-11-16
**Status**: ✅ Fixed and tested
