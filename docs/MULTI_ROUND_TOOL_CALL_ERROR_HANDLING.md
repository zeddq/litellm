# Multi-Round Tool Call Error Handling

**Status**: ✅ Implemented  
**Date**: 2025-11-13  
**Issue**: Tool call errors lacked sufficient context for LLM self-correction  
**Solution**: Structured error responses with retry guidance  

---

## Problem Statement

When LLMs make tool calls with missing or invalid parameters, the error messages returned were too terse for the LLM to self-correct. This resulted in:

1. **User friction**: LLM asks user for clarification instead of fixing the tool call
2. **Poor UX**: Multi-round tool calls fail on first error
3. **Wasted tokens**: Extra round-trip to user when LLM could self-correct

### Example of Original Behavior

**Trace Data Analysis**:
```json
{
  "gen_ai.prompt.3.content": "Tool execution error: No query provided",
  "gen_ai.completion.0.content": "I apologize for the confusion. Could you please clarify what documents you're referring to?"
}
```

**Problem**: LLM received minimal error context and asked user instead of retrying with correct parameters.

---

## Solution: Structured Error Responses

### Architecture

```
┌─────────────────────────────────────────────────┐
│ LLM makes tool call with missing parameter      │
└─────────────────┬───────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────┐
│ ToolExecutor detects missing 'query' parameter  │
│ Returns ToolExecutionError with:                │
│  - error_type: "missing_parameter"              │
│  - parameter: "query"                           │
│  - required_parameters: ["query"]               │
│  - example: {"query": "search term"}            │
│  - retry_hint: "Retry with query parameter"     │
└─────────────────┬───────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────┐
│ format_tool_result_for_llm() creates            │
│ LLM-friendly error message with:                │
│  ✅ Clear error description                      │
│  ✅ Missing parameter identification             │
│  ✅ Concrete usage example                       │
│  ✅ Explicit retry guidance                      │
└─────────────────┬───────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────┐
│ LLM receives structured error and self-corrects │
│ Makes new tool call with correct parameters     │
└─────────────────────────────────────────────────┘
```

---

## Implementation Details

### 1. ToolExecutionError Class

**File**: `src/proxy/tool_executor.py:45-95`

```python
class ToolExecutionError:
    """
    Structured tool execution error with guidance for LLM self-correction.
    
    Attributes:
        error_type: Classification (e.g., 'missing_parameter')
        message: Human-readable error message
        parameter: Name of problematic parameter
        required_parameters: List of all required parameters
        example: Example of correct usage
        retry_hint: Explicit guidance for retrying
    """
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "type": self.error_type,
            "message": self.message,
            "parameter": self.parameter,
            "required_parameters": self.required_parameters,
            "example": self.example,
            "retry_hint": self.retry_hint,
        }
```

### 2. Enhanced Error Returns

**File**: `src/proxy/tool_executor.py:210-223`

**Before**:
```python
if not query:
    return {
        "tool_call_id": tool_call_id,
        "error": "No query provided",  # ❌ Too terse
        "results": []
    }
```

**After**:
```python
if not query:
    error = ToolExecutionError(
        error_type="missing_parameter",
        message="The 'query' parameter is required for document search",
        parameter="query",
        required_parameters=["query"],
        example={"query": "python asyncio patterns"},
        retry_hint="Retry the tool call with a search query string. "
                   "The query should describe what you're looking for."
    )
    return {
        "tool_call_id": tool_call_id,
        "error": error.to_dict(),  # ✅ Structured with guidance
        "results": []
    }
```

### 3. LLM-Friendly Formatting

**File**: `src/proxy/tool_executor.py:290-315`

**Output Format**:
```
❌ Tool Call Error: The 'query' parameter is required for document search

Missing Parameter: 'query'
Required Parameters: query

Example Usage:
{
  "query": "python asyncio patterns"
}

💡 Retry the tool call with a search query string. The query should describe what you're looking for in the user's documents.
```

---

## Testing

### Test Coverage

**File**: `tests/src/test_tool_executor_errors.py`

**Test Suites**:
1. ✅ `TestToolExecutionError` (3 tests) - Class functionality
2. ✅ `TestToolExecutorErrorHandling` (3 tests) - Error generation
3. ✅ `TestToolResultLLMFormatting` (3 tests) - LLM message formatting
4. ✅ `TestMultiRoundToolCallFlow` (2 tests) - Integration scenarios

**Total**: 11 tests, all passing

### Running Tests

```bash
# Run all error handling tests
poetry run pytest tests/src/test_tool_executor_errors.py -xvs

# Run demo script
poetry run python test_tool_error_demo.py
```

---

## Benefits

### 1. LLM Self-Correction
- **Before**: LLM asks user for clarification on every tool error
- **After**: LLM can retry tool calls with correct parameters

### 2. Better User Experience
- **Before**: "I don't have access to that. What do you mean?"
- **After**: LLM silently fixes tool call and returns results

### 3. Reduced Token Usage
- Eliminates unnecessary user round-trips
- Fewer clarification messages needed

### 4. Backward Compatibility
- Legacy string errors still supported
- Graceful degradation for external tools

---

## Usage Examples

### Example 1: Missing Parameter Recovery

```python
# First attempt (missing query)
result = await executor.execute_tool_call(
    tool_name="supermemoryToolSearch",
    tool_args={},  # Missing query!
    user_id="user-123",
    tool_call_id="call_1"
)

# LLM receives structured error with guidance
error_msg = executor.format_tool_result_for_llm(result)
# Contains: parameter name, example, retry hint

# LLM automatically retries with correct params
result2 = await executor.execute_tool_call(
    tool_name="supermemoryToolSearch",
    tool_args={"query": "python async"},  # Fixed!
    user_id="user-123",
    tool_call_id="call_2"
)
# Returns successful results
```

### Example 2: Error Type Classification

```python
error = ToolExecutionError(
    error_type="missing_parameter",  # Classifies error type
    message="The 'query' parameter is required",
    parameter="query",
    required_parameters=["query"],
    example={"query": "search term"},
    retry_hint="Provide a search query"
)
```

---

## Enhanced Features (2025-11-13 Update)

### ✅ 1. Additional Error Types (Implemented)

**File**: `src/proxy/tool_executor.py:290-540`

The following error types are now fully supported with structured responses:

#### `invalid_type`
Detects when a parameter has the wrong type:
```python
# Example: query is int instead of str
{"query": 123}  # Error: Parameter 'query' must be str, got int
```

#### `invalid_value`
Detects empty or invalid parameter values:
```python
# Example: empty query string
{"query": "   "}  # Error: Parameter 'query' cannot be empty
```

#### `authentication_error`
Automatically detects authentication failures:
```python
# Detects: "authentication", "unauthorized", "api key", "401", "403"
# Error: Authentication failed. Please check the API key configuration.
```

#### `rate_limit_exceeded`
Automatically detects rate limiting:
```python
# Detects: "rate limit", "too many requests", "429"
# Error: Rate limit exceeded. Please try again in a few moments.
```

#### `execution_error`
Generic fallback for other execution failures:
```python
# Catches all other exceptions with structured guidance
```

### ✅ 2. Retry Counter (Implemented)

**File**: `src/proxy/litellm_proxy_sdk.py:585-680`

```python
class ToolCallBuffer:
    def __init__(self):
        self.retry_counts: Dict[str, int] = {}
        self.error_history: Dict[str, List[str]] = {}
    
    def increment_retry_count(self, tool_call_id: str) -> int:
        """Increment retry count and return new count."""
        
    def get_retry_count(self, tool_call_id: str) -> int:
        """Get current retry count."""
        
    def should_retry(self, tool_call_id: str, max_retries: int = 2) -> bool:
        """Check if tool call should be retried."""
        return self.get_retry_count(tool_call_id) < max_retries
    
    def record_error(self, tool_call_id: str, error_type: str) -> None:
        """Record an error for telemetry and debugging."""
        
    def get_error_history(self, tool_call_id: str) -> List[str]:
        """Get list of all errors for this tool call."""
```

**Usage Example**:
```python
buffer = ToolCallBuffer()

# Tool call fails with error
buffer.record_error("call_123", "missing_parameter")
buffer.increment_retry_count("call_123")

# Check if should retry
if buffer.should_retry("call_123", max_retries=2):
    # Retry the tool call
    pass
else:
    # Max retries exceeded, escalate to user
    pass
```

### ✅ 3. Parameter Validation Helpers (Implemented)

**File**: `src/proxy/tool_executor.py:45-105`

```python
def validate_parameter_type(
    param_name: str,
    value: Any,
    expected_type: type,
    example_value: Any = None,
) -> Optional[ToolExecutionError]:
    """Validate parameter type and return structured error if invalid."""
    if not isinstance(value, expected_type):
        return ToolExecutionError(
            error_type="invalid_type",
            message=f"Parameter '{param_name}' must be {expected_type.__name__}, got {type(value).__name__}",
            parameter=param_name,
            example={param_name: example_value}
        )
    return None

def validate_parameter_not_empty(
    param_name: str,
    value: str,
    example_value: str = None,
) -> Optional[ToolExecutionError]:
    """Validate parameter is not empty and return structured error if invalid."""
    if not value or not value.strip():
        return ToolExecutionError(
            error_type="invalid_value",
            message=f"Parameter '{param_name}' cannot be empty",
            parameter=param_name,
            example={param_name: example_value}
        )
    return None
```

### ✅ 4. Comprehensive Telemetry Logging (Implemented)

**File**: `src/proxy/tool_executor.py:290-540`

All error types now include structured logging with telemetry metadata:

```python
logger.warning(
    f"Tool execution error: {error_type}",
    extra={
        "tool_name": "supermemoryToolSearch",
        "error_type": error_type,
        "parameter": parameter_name,
        "user_id": user_id,
        "tool_call_id": tool_call_id,
        "exception": str(e),  # For execution errors
        "expected_type": "str",  # For type errors
        "actual_type": "int",  # For type errors
    }
)
```

**Telemetry Metadata Captured**:
- Tool name
- Error type classification
- Parameter name (if applicable)
- User ID
- Tool call ID
- Exception details
- Type information (for type errors)

### 🔄 5. Future Enhancements

#### Tool Schema Validation (Planned)
- JSON Schema for tool parameters
- Automatic validation before execution
- Auto-generated error messages from schema

#### Retry Strategies (Planned)
- Exponential backoff for rate limits
- Different max retries per error type
- Smart retry decisions based on error history

---

## Related Files

### Core Implementation
- `src/proxy/tool_executor.py` - Main implementation
- `src/proxy/litellm_proxy_sdk.py` - Integration point (lines 1528-1860)

### Tests
- `tests/src/test_tool_executor_errors.py` - Comprehensive test suite (21 tests, all passing)
  - ToolExecutionError class tests (3 tests)
  - Error handling tests (3 tests)
  - LLM formatting tests (3 tests)
  - Multi-round flow tests (2 tests)
  - New error types tests (3 tests)
  - Retry tracking tests (7 tests)
- `test_tool_error_demo.py` - Interactive demo script

### Documentation
- `docs/architecture/OVERVIEW.md` - System architecture
- `docs/guides/TESTING.md` - Testing strategies

---

## Monitoring & Observability

### Telemetry Integration

The structured errors are automatically captured in OpenTelemetry traces:

```json
{
  "metadata.mcp_tool_call_metadata": {
    "tool_name": "supermemoryToolSearch",
    "error_type": "missing_parameter",
    "parameter": "query",
    "retry_attempt": 1
  }
}
```

### Metrics to Track
- Tool call error rate by type
- Retry success rate
- Average retries per tool call
- Time to successful tool execution

### Query Examples
```sql
-- Find most common tool errors
SELECT error_type, COUNT(*) as count
FROM tool_execution_errors
GROUP BY error_type
ORDER BY count DESC;

-- Measure retry success rate
SELECT 
  COUNT(DISTINCT session_id) as total_errors,
  COUNT(DISTINCT CASE WHEN retry_succeeded THEN session_id END) as successful_retries
FROM tool_execution_sessions
WHERE has_errors = true;
```

---

## Conclusion

The structured error handling implementation with comprehensive telemetry and retry tracking enables LLMs to self-correct tool call errors without user intervention. This improves:

✅ **User Experience** - Fewer interruptions, seamless error recovery  
✅ **LLM Autonomy** - Self-correction capability with intelligent retry logic  
✅ **Token Efficiency** - Reduced round-trips, max retry limits prevent infinite loops  
✅ **Developer Experience** - Clear error debugging, comprehensive telemetry  
✅ **Observability** - Structured logging with full error context for monitoring  
✅ **Error Detection** - Automatic detection of authentication, rate limit, and type errors  

### Implementation Summary

**Phase 1 (Original)**: Basic structured errors
- ToolExecutionError class
- Missing parameter detection
- LLM-friendly formatting

**Phase 2 (Current)**: Enhanced error handling & telemetry
- 5 additional error types (invalid_type, invalid_value, authentication_error, rate_limit_exceeded, execution_error)
- Parameter validation helpers
- Retry tracking with configurable max retries
- Error history recording
- Comprehensive telemetry logging with structured metadata

**Test Coverage**: 21 tests, all passing
- 3 error class tests
- 3 error handling tests
- 3 LLM formatting tests
- 2 multi-round flow tests
- 3 new error type tests
- 7 retry tracking tests

**Status**: ✅ Production-ready with comprehensive test coverage and telemetry integration.

**Next Steps**: Ready for manual testing with real LLM requests. Telemetry will be visible in OpenTelemetry traces.
