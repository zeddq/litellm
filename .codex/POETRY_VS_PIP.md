# Poetry vs pip: Configuration Behavior

## TL;DR

**No, Poetry does NOT respect pip settings without additional configuration.**

Poetry 2.x uses its own installer and completely ignores `~/.config/pip/pip.conf`. You must configure Poetry directly using `poetry source add` or `[[tool.poetry.source]]` in `pyproject.toml`.

## Why This Matters

### Poetry's Architecture (2.0+)

```
Poetry 2.x (Modern Installer)
│
├─ Own HTTP client
├─ Own package resolver
├─ Own wheel installer
└─ Does NOT use pip

Poetry 1.x (Legacy Installer)
│
└─ Uses pip underneath
   └─ Respects ~/.config/pip/pip.conf ✅
```

**Key Point**: The `installer.modern-installation` setting that toggled between these no longer exists in Poetry 2.2+. Poetry 2.x **always** uses its own installer.

## What Our Scripts Do

### 1. Configure Poetry Directly (Primary)

```bash
# This configures Poetry's own HTTP client
poetry source add --priority=primary aliyun https://mirrors.aliyun.com/pypi/simple/

# This tells Poetry to skip SSL verification
poetry config certificates.aliyun.cert false
```

**Result**: Poetry will use the mirror directly, bypassing pip entirely.

### 2. Configure pip (Fallback Only)

```bash
# This is ONLY used if Poetry fails and we fall back to pip
cat > ~/.config/pip/pip.conf << EOF
[global]
index-url = https://mirrors.aliyun.com/pypi/simple/
EOF
```

**Result**: Only used in emergency fallback:
```bash
poetry export -f requirements.txt --output /tmp/requirements.txt
pip install -r /tmp/requirements.txt  # ← pip config used here
```

## How to Verify Poetry Configuration

### Check Poetry Sources

```bash
poetry source show
```

Expected output:
```
 name      : aliyun
 url       : https://mirrors.aliyun.com/pypi/simple/
 priority  : primary
```

### Check Where Poetry Downloads From

```bash
poetry install -vvv 2>&1 | grep -i "downloading\|fetching"
```

You should see requests going to your configured mirror (e.g., `mirrors.aliyun.com`), not `pypi.org`.

## Permanent Configuration Options

### Option 1: pyproject.toml (Recommended)

Add to your `pyproject.toml`:

```toml
[[tool.poetry.source]]
name = "aliyun"
url = "https://mirrors.aliyun.com/pypi/simple/"
priority = "primary"

[[tool.poetry.source]]
name = "pypi"
url = "https://pypi.org/simple/"
priority = "supplemental"
```

**Pros**:
- ✅ Committed to git
- ✅ Works for all team members
- ✅ Project-specific

**Cons**:
- ❌ Applies to this project only

### Option 2: Global Poetry Config

```bash
poetry config repositories.aliyun https://mirrors.aliyun.com/pypi/simple/
```

**Pros**:
- ✅ Works across all projects
- ✅ User-specific

**Cons**:
- ❌ Not committed to git
- ❌ Each developer must configure

### Option 3: Dynamic (Our Approach)

The scripts use `poetry source add` at runtime, which modifies the local Poetry config for this project.

**Pros**:
- ✅ Works in Codex cloud automatically
- ✅ No git changes needed
- ✅ Environment-aware (detects accessible mirrors)

**Cons**:
- ❌ Must run setup script each time

## Testing If Poetry Uses Your Configuration

### Test 1: Dry Run

```bash
poetry add --dry-run httpx
```

Watch the output - it should show downloading from your mirror.

### Test 2: Verbose Install

```bash
poetry install -vvv 2>&1 | head -50
```

Look for lines like:
```
Source (aliyun): Downloading https://mirrors.aliyun.com/pypi/simple/httpx/
```

### Test 3: Check Lock File

```bash
poetry lock --no-update -vvv 2>&1 | grep -i "using\|source"
```

## Common Pitfalls

### ❌ Pitfall 1: Only Configuring pip

```bash
# This does NOTHING for Poetry 2.x!
cat > ~/.config/pip/pip.conf << EOF
[global]
index-url = https://mirror.example.com/pypi/simple/
EOF

poetry install  # Still uses pypi.org ❌
```

### ✅ Correct: Configure Poetry

```bash
# This actually works
poetry source add my-mirror https://mirror.example.com/pypi/simple/
poetry install  # Uses mirror ✅
```

### ❌ Pitfall 2: Expecting pip Config to Work

```bash
export PIP_INDEX_URL=https://mirror.example.com/pypi/simple/
poetry install  # Ignores PIP_INDEX_URL ❌
```

### ✅ Correct: Use Poetry Environment Variables

```bash
export POETRY_REPOSITORIES_MYMIRROR_URL=https://mirror.example.com/pypi/simple/
poetry install  # Works ✅
```

## What About `installer.modern-installation`?

This setting **no longer exists** in Poetry 2.2+. If you see it in old scripts/documentation:

- **Poetry 1.2-1.7**: Setting existed, could toggle between modern/legacy
- **Poetry 2.0+**: Setting removed, always uses modern installer
- **Our scripts**: Use `installer.parallel false` instead (different purpose but ensures sequential installs)

## Summary

| Configuration | Poetry 2.x Respects? | When Used |
|---------------|---------------------|-----------|
| `~/.config/pip/pip.conf` | ❌ No | Only in pip fallback |
| `poetry source add` | ✅ Yes | Always |
| `[[tool.poetry.source]]` in pyproject.toml | ✅ Yes | Always |
| `PIP_INDEX_URL` env var | ❌ No | Only in pip fallback |
| `POETRY_REPOSITORIES_*` env vars | ✅ Yes | Always |

## Recommendations for Codex Cloud

1. **Use our setup scripts** - they configure Poetry correctly
2. **Add mirrors to pyproject.toml** - for permanent configuration
3. **Keep pip config as fallback** - emergency safety net
4. **Test with `poetry install -vvv`** - verify mirror usage

## Further Reading

- [Poetry Repositories Documentation](https://python-poetry.org/docs/repositories/)
- [Poetry Configuration](https://python-poetry.org/docs/configuration/)
- [Poetry 2.0 Release Notes](https://python-poetry.org/blog/announcing-poetry-2.0.0/)

---

**Key Takeaway**: Always configure Poetry directly. pip configuration is only a fallback safety net.
