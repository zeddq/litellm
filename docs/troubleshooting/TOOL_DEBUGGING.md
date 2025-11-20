# Tool Call Debugging with OpenTelemetry & Custom Callbacks

## Problem
The LLM enters a loop of calling tools with invalid parameters because it fails to "correct" its input based on the error feedback provided by the proxy.

## Debugging Strategy
We have implemented a **Custom LiteLLM Callback** (`ToolDebugLogger`) to provide granular visibility into this "Tool Error -> LLM Reaction" loop.

### 1. ToolDebugLogger
Located in `src/proxy/tool_debug_logger.py`.
This logger hooks into `log_success_event` (triggered after every successful LLM generation).

**Logic:**
1.  It checks if the *input messages* to the LLM contained a `tool` role message (the result of the previous turn).
2.  It checks if that tool result contained an "Error".
3.  If so, it logs a structured "Round Analysis":
    *   **Sent Context:** The error message we gave the LLM.
    *   **LLM Reaction:** The new tool call (or text) the LLM generated in response.

### 2. OpenTelemetry Integration
The logger runs alongside standard OpenTelemetry callbacks.
*   **Traces:** Each LLM call (including the retries) is traced by OTel.
*   **Logs:** The `ToolDebugLogger` emits standard Python logs (visible in Docker/Console) which can be aggregated by your logging stack (e.g., Fluentd/Datadog).

## How to Use

1.  **Start the Proxy:**
    ```bash
    poetry run start-proxies
    ```
2.  **Trigger the Error:**
    Send a request that triggers the tool loop (e.g., a query that is ambiguous or missing params).
3.  **Inspect Logs:**
    Look for `[ToolDebug]` in the console output.

    ```text
    WARNING:root:🔍 [ToolDebug] Round Analysis (ToolCallID: call_123)
    WARNING:root:   ➡️ Sent Context (Last Message):
    ❌ Tool Call Error: Parameter 'query' must be str...
    
    WARNING:root:   ⬅️ LLM Reaction (New Tool Call): supermemoryToolSearch({"query": ["wrong type again"]})
    ```

## Next Steps
If the logs show the LLM is receiving the correct error but *ignoring* it:
1.  **Refine Error Message:** Edit `src/proxy/tool_executor.py` -> `format_tool_result_for_llm` to make the error more "scolding" or explicit for the specific model.
2.  **Model Specifics:** Some models (e.g., smaller ones) have poor instruction following for tool corrections. You might need to simplify the tool schema.
