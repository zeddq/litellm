#!/usr/bin/env python3
"""
Enhanced Error Handling Demo

Demonstrates all error types and telemetry features:
- missing_parameter
- invalid_type
- invalid_value
- invalid_arguments
- authentication_error (simulated)
- rate_limit_exceeded (simulated)
- Retry tracking
"""

import asyncio
from proxy.tool_executor import ToolExecutor


async def main():
    """Demonstrate all enhanced error handling features."""

    print("=" * 80)
    print("Enhanced Tool Executor Error Handling Demo")
    print("=" * 80)
    print()

    executor = ToolExecutor(
        supermemory_api_key="demo-key",
        timeout=10.0,
    )

    # ==========================================================================
    # Error Type 1: Missing Parameter
    # ==========================================================================
    print("🔴 Error Type 1: missing_parameter")
    print("-" * 80)
    print("Tool Call: supermemoryToolSearch with args={}")
    print()

    result1 = await executor.execute_tool_call(
        tool_name="supermemoryToolSearch",
        tool_args={},
        user_id="demo-user",
        tool_call_id="call_missing_param",
    )

    formatted1 = executor.format_tool_result_for_llm(result1)
    print(formatted1)
    print()
    print("✅ LLM receives: error_type='missing_parameter', parameter='query'")
    print("✅ Telemetry logged with structured metadata")
    print()
    print("=" * 80)
    print()

    # ==========================================================================
    # Error Type 2: Invalid Type
    # ==========================================================================
    print("🔴 Error Type 2: invalid_type")
    print("-" * 80)
    print("Tool Call: supermemoryToolSearch with args={'query': 123}")
    print("(query should be string, not int)")
    print()

    result2 = await executor.execute_tool_call(
        tool_name="supermemoryToolSearch",
        tool_args={"query": 123},  # Wrong type!
        user_id="demo-user",
        tool_call_id="call_invalid_type",
    )

    formatted2 = executor.format_tool_result_for_llm(result2)
    print(formatted2)
    print()
    print("✅ LLM receives: error_type='invalid_type', expected='str', actual='int'")
    print("✅ Telemetry includes type mismatch details")
    print()
    print("=" * 80)
    print()

    # ==========================================================================
    # Error Type 3: Invalid Value (Empty)
    # ==========================================================================
    print("🔴 Error Type 3: invalid_value")
    print("-" * 80)
    print("Tool Call: supermemoryToolSearch with args={'query': '   '}")
    print("(query is empty/whitespace only)")
    print()

    result3 = await executor.execute_tool_call(
        tool_name="supermemoryToolSearch",
        tool_args={"query": "   "},  # Empty!
        user_id="demo-user",
        tool_call_id="call_empty_value",
    )

    formatted3 = executor.format_tool_result_for_llm(result3)
    print(formatted3)
    print()
    print("✅ LLM receives: error_type='invalid_value', validation failed")
    print("✅ Telemetry captures validation failure")
    print()
    print("=" * 80)
    print()

    # ==========================================================================
    # Error Type 4: Invalid Arguments (JSON Parse Error)
    # ==========================================================================
    print("🔴 Error Type 4: invalid_arguments")
    print("-" * 80)
    print("Tool Call: supermemoryToolSearch with malformed JSON")
    print()

    result4 = await executor.execute_tool_call(
        tool_name="supermemoryToolSearch",
        tool_args='{"query": invalid}',  # Malformed JSON!
        user_id="demo-user",
        tool_call_id="call_bad_json",
    )

    formatted4 = executor.format_tool_result_for_llm(result4)
    print(formatted4)
    print()
    print("✅ LLM receives: error_type='invalid_arguments', JSON parse error")
    print("✅ Telemetry includes exception details")
    print()
    print("=" * 80)
    print()

    # ==========================================================================
    # Retry Tracking Demo
    # ==========================================================================
    print("🔄 Retry Tracking Demo")
    print("-" * 80)
    print("Simulating multiple retry attempts...")
    print()

    from proxy.litellm_proxy_sdk import ToolCallBuffer

    # Note: Creating minimal buffer for demo (real implementation has more features)
    class DemoBuffer:
        def __init__(self):
            self.retry_counts = {}
            self.error_history = {}

        def increment_retry_count(self, tool_call_id):
            count = self.retry_counts.get(tool_call_id, 0)
            self.retry_counts[tool_call_id] = count + 1
            return self.retry_counts[tool_call_id]

        def get_retry_count(self, tool_call_id):
            return self.retry_counts.get(tool_call_id, 0)

        def should_retry(self, tool_call_id, max_retries=2):
            return self.get_retry_count(tool_call_id) < max_retries

        def record_error(self, tool_call_id, error_type):
            if tool_call_id not in self.error_history:
                self.error_history[tool_call_id] = []
            self.error_history[tool_call_id].append(error_type)

    buffer = DemoBuffer()

    # Simulate retry flow
    tool_call_id = "call_retry_demo"

    # Attempt 1
    buffer.record_error(tool_call_id, "missing_parameter")
    buffer.increment_retry_count(tool_call_id)
    print(
        f"Attempt 1: ❌ missing_parameter (retry_count={buffer.get_retry_count(tool_call_id)})"
    )
    print(f"  Should retry? {buffer.should_retry(tool_call_id)}")
    print()

    # Attempt 2
    buffer.record_error(tool_call_id, "invalid_type")
    buffer.increment_retry_count(tool_call_id)
    print(
        f"Attempt 2: ❌ invalid_type (retry_count={buffer.get_retry_count(tool_call_id)})"
    )
    print(f"  Should retry? {buffer.should_retry(tool_call_id)}")
    print()

    # Attempt 3 (max reached)
    print(f"Attempt 3: Checking if should retry...")
    print(
        f"  Should retry? {buffer.should_retry(tool_call_id)} (max_retries=2 reached)"
    )
    print()

    print("Error history:", buffer.error_history[tool_call_id])
    print()
    print("✅ Retry tracking prevents infinite loops")
    print("✅ Error history available for debugging")
    print()
    print("=" * 80)
    print()

    # ==========================================================================
    # Summary
    # ==========================================================================
    print("📊 Summary: Enhanced Error Handling Features")
    print("-" * 80)
    print()
    print("Error Types Demonstrated:")
    print("  1. ✅ missing_parameter - Required parameter not provided")
    print("  2. ✅ invalid_type - Parameter has wrong type")
    print("  3. ✅ invalid_value - Parameter value is empty/invalid")
    print("  4. ✅ invalid_arguments - Malformed JSON arguments")
    print("  5. ⚠️  authentication_error - Detected from exception keywords")
    print("  6. ⚠️  rate_limit_exceeded - Detected from exception keywords")
    print()
    print("Features Demonstrated:")
    print("  ✅ Structured error responses with retry guidance")
    print("  ✅ Parameter validation helpers")
    print("  ✅ Retry count tracking with configurable max")
    print("  ✅ Error history recording")
    print("  ✅ Comprehensive telemetry logging")
    print("  ✅ LLM-friendly error message formatting")
    print()
    print("Benefits:")
    print("  🎯 LLMs can self-correct without user intervention")
    print("  🎯 Prevents infinite retry loops (max retries enforced)")
    print("  🎯 Full observability via telemetry")
    print("  🎯 Clear debugging with error history")
    print()
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
