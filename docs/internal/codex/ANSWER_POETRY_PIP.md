# Answer: Will Poetry Respect pip Settings?

## Short Answer

**No, Poetry 2.2+ will NOT respect pip settings.** But our scripts already handle this correctly! 🎉

## What Our Scripts Actually Do

### ✅ Scripts Configure Poetry Directly

Our scripts already use **Poetry's native configuration**, not just pip:

#### `setup_poetry_mirrors.sh` (Line 76):
```bash
poetry source add --priority=primary "$MIRROR_NAME" "$MIRROR_URL"
poetry config certificates."$MIRROR_NAME".cert false
```

#### `fixed_setup_poetry.sh` (Lines 118-125):
```bash
poetry source add --priority=primary pypi-main https://pypi.org/simple/
poetry config certificates.pypi-main.cert false
```

**Result**: Poetry's own HTTP client uses these settings, **not pip's configuration**.

## Why We Also Configure pip

The pip configuration in our scripts is **only a fallback** for this scenario:

```bash
# If Poetry fails completely:
poetry export -f requirements.txt  # Export dependencies
pip install -r requirements.txt     # ← pip config used HERE
```

This is the emergency fallback path when Poetry itself fails.

## Verification

### What Poetry Will Actually Use

When you run our scripts in Codex cloud:

1. **Mirror approach** (`setup_poetry_mirrors.sh`):
   ```bash
   poetry source add aliyun https://mirrors.aliyun.com/pypi/simple/
   poetry install  # ← Uses Aliyun mirror via Poetry's HTTP client
   ```

2. **SSL patch approach** (`fixed_setup_poetry.sh`):
   ```bash
   poetry source add pypi-main https://pypi.org/simple/
   # + sitecustomize.py patches SSL globally
   poetry install  # ← Uses patched SSL context
   ```

### Test It

After running setup, verify Poetry is using the correct source:

```bash
# Check configured sources
poetry source show

# Verbose install to see where it downloads from
poetry install -vvv 2>&1 | grep -i "downloading\|source"
```

You should see requests going to your mirror (e.g., `mirrors.aliyun.com`), not `pypi.org`.

## Summary Table

| What | Poetry 2.2+ Respects? | When Our Scripts Use It |
|------|----------------------|------------------------|
| `~/.config/pip/pip.conf` | ❌ No | Only in pip fallback |
| `poetry source add` | ✅ Yes | **Primary method** |
| `poetry config certificates` | ✅ Yes | **Primary method** |
| `sitecustomize.py` SSL patch | ✅ Yes | SSL patch approach |

## Conclusion

**You don't need to worry about this!** Our scripts are already doing the right thing:

✅ Configure Poetry directly with `poetry source add`
✅ Configure Poetry certificates with `poetry config certificates`
✅ Configure pip as fallback only
✅ Use sitecustomize.py for SSL patching when needed

The scripts will work correctly in Codex cloud without needing the old `installer.modern-installation` setting.

## Related Documentation

- See `POETRY_VS_PIP.md` for detailed explanation
- See `README.md` for full setup documentation
- See `QUICK_START.md` for usage

---

**TL;DR**: Scripts already configure Poetry correctly. pip config is just a safety fallback. Everything will work! 🚀
