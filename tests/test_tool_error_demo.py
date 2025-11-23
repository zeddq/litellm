#!/usr/bin/env python3
"""
Demo script showing improved tool error handling.

This demonstrates how structured errors help LLMs self-correct
in multi-round tool call scenarios.
"""

import asyncio

from proxy.tool_executor import ToolExecutor


async def main():
    """Demonstrate improved error handling."""

    print("=" * 70)
    print("Tool Executor Error Handling Demo")
    print("=" * 70)
    print()

    # Initialize executor
    executor = ToolExecutor(
        supermemory_api_key="demo-key",
        timeout=10.0,
    )

    # Scenario 1: Missing query parameter (common error)
    print("Scenario 1: Missing Query Parameter")
    print("-" * 70)
    print("Tool Call: supermemoryToolSearch with args={}")
    print()

    result = await executor.execute_tool_call(
        tool_name="supermemoryToolSearch",
        tool_args={},  # Missing query!
        user_id="demo-user",
        tool_call_id="call_demo_1",
    )

    # Show raw structured error
    print("Raw Error Response:")
    import json

    print(json.dumps(result, indent=2))
    print()

    # Show LLM-formatted error
    print("LLM-Formatted Error Message:")
    formatted = executor.format_tool_result_for_llm(result)
    print(formatted)
    print()
    print("=" * 70)
    print()

    # Scenario 2: Empty query parameter
    print("Scenario 2: Empty Query Parameter")
    print("-" * 70)
    print("Tool Call: supermemoryToolSearch with args={'query': ''}")
    print()

    result2 = await executor.execute_tool_call(
        tool_name="supermemoryToolSearch",
        tool_args={"query": ""},  # Empty query!
        user_id="demo-user",
        tool_call_id="call_demo_2",
    )

    formatted2 = executor.format_tool_result_for_llm(result2)
    print("LLM-Formatted Error Message:")
    print(formatted2)
    print()
    print("=" * 70)
    print()

    # Demonstrate what LLM should see
    print("Summary: What the LLM Receives")
    print("-" * 70)
    print("✅ Error type classification: 'missing_parameter'")
    print("✅ Missing parameter identified: 'query'")
    print("✅ List of required parameters: ['query']")
    print("✅ Concrete usage example: {'query': 'python asyncio patterns'}")
    print("✅ Explicit retry hint with guidance")
    print()
    print("With this information, the LLM can:")
    print("  1. Understand what went wrong")
    print("  2. See exactly what parameter is missing")
    print("  3. Get a concrete example of correct usage")
    print("  4. Receive explicit guidance to retry")
    print()
    print("Result: LLM can self-correct instead of asking user for help!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
