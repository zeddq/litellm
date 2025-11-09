# Group 6 Fix Report: uvicorn/python PATH Issues

## Issue Summary
**Error Type**: FileNotFoundError  
**Error Message**: `FileNotFoundError: [Errno 2] No such file or directory: 'uvicorn'`  
**Affected Test**: `tests/test_interceptor_known_issues.py::TestSupermemoryEndpointCrash::test_direct_provider_workaround`

## Root Cause
Subprocess calls in test helper functions were using bare command names (`'uvicorn'`, `'python'`) which weren't found in the PATH during test execution. This is because subprocess.Popen doesn't inherit the poetry shell environment's PATH modifications.

## Fix Strategy
**Chosen**: Option A - Use `sys.executable` to get full path to Python executable

### Why This Approach?
1. **Portable**: Works across all virtual environments (poetry, venv, conda)
2. **Reliable**: Guarantees correct Python interpreter is used
3. **Standard**: Common pattern in Python testing
4. **Module Support**: Using `-m` flag ensures packages are found

## Implementation

### Files Modified
1. `tests/helpers/pipeline_helpers.py`
2. `tests/fixtures/interceptor_fixtures.py`

### Changes Made

#### 1. Added sys import
```python
import sys  # Added to both files
```

#### 2. Fixed uvicorn calls (2 instances)
**Before**:
```python
['uvicorn', 'proxy.litellm_proxy_sdk:app', '--port', str(memory_port)]
```

**After**:
```python
[sys.executable, '-m', 'uvicorn', 'proxy.litellm_proxy_sdk:app', '--port', str(memory_port)]
```

#### 3. Fixed python calls (2 instances)
**Before**:
```python
['python', '-m', 'src.interceptor.cli', 'run']
```

**After**:
```python
[sys.executable, '-m', 'src.interceptor.cli', 'run']
```

## Validation

### Before Fix
```
E   FileNotFoundError: [Errno 2] No such file or directory: 'uvicorn'
```

### After Fix
```
E   TimeoutError: Services failed to start within timeout
```

**Result**: FileNotFoundError is eliminated. The test now fails at a later stage (service startup timeout), confirming the PATH issue is resolved.

## Test Results

### Command
```bash
poetry run python -m pytest tests/test_interceptor_known_issues.py::TestSupermemoryEndpointCrash::test_direct_provider_workaround -xvs
```

### Result
- ✅ No FileNotFoundError for 'uvicorn'
- ✅ No FileNotFoundError for 'python'
- ⚠️ Test still fails due to service startup timeout (different issue, not in scope)

## Success Criteria Met

- ✅ No FileNotFoundError for uvicorn
- ✅ Test progresses past subprocess creation
- ✅ Fix is minimal and doesn't affect other tests
- ✅ Solution is portable across environments

## Commit

```
jj commit -m "Fix Group 6: uvicorn and python PATH issues in subprocess calls"
```

**Commit ID**: e9762521

## Side Effects
None. This change only affects subprocess execution paths and doesn't alter test logic or behavior.

## Notes
- The test still fails with TimeoutError, which is out of scope for Group 6 (environment issues)
- This fix ensures all subprocess calls in test helpers use the correct virtual environment
- Pattern can be applied to other subprocess calls if similar issues arise
