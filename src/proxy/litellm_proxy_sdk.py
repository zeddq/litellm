"""
LiteLLM SDK-Based Proxy with Memory Routing

Main FastAPI application that uses LiteLLM SDK with persistent sessions.
Integrates all modular components: session manager, config parser, error handlers, streaming.

Architecture:
    - Persistent httpx.AsyncClient injected into LiteLLM SDK
    - Cookie persistence for Cloudflare (cf_clearance)
    - Memory routing with user ID detection
    - OpenAI-compatible API endpoints
    - Comprehensive error handling
    - SSE streaming support

Key Components:
    - session_manager: Manages persistent httpx.AsyncClient
    - config_parser: Loads and parses config.yaml
    - error_handlers: Maps LiteLLM exceptions to HTTP responses
    - streaming_utils: Handles SSE streaming format
    - memory_router: Detects user IDs from headers (existing)

Example:
    ```bash
    # Start server
    uvicorn src.proxy.litellm_proxy_sdk:app --host 0.0.0.0 --port 8764
    
    # Test request
    curl http://localhost:8764/v1/chat/completions \\
      -H "Content-Type: application/json" \\
      -H "Authorization: Bearer sk-1234" \\
      -d '{"model": "claude-sonnet-4.5", "messages": [{"role": "user", "content": "Hello"}]}'
    ```

References:
    - LITELLM_SDK_INTEGRATION_PATTERNS.md: Complete patterns
    - SDK_MIGRATION_ROLLOUT_ARCHITECTURE.md: Architecture design
    - poc_litellm_sdk_proxy.py: Working proof of concept
"""

import json
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

import litellm
from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse, JSONResponse
from litellm.integrations.custom_logger import CustomLogger
from litellm.litellm_core_utils.streaming_handler import CustomStreamWrapper
from litellm.types.utils import ModelResponseStream

from integrations.prisma_proxy import PrismaProxyLogger
from proxy.config_parser import LiteLLMConfig
from proxy.context_retriever import ContextRetriever, retrieve_and_inject_context
from proxy.error_handlers import LiteLLMErrorHandler, register_exception_handlers
from proxy.memory_router import MemoryRouter
from proxy.session_manager import LiteLLMSessionManager
from proxy.tool_executor import ToolExecutor, ToolExecutionConfig, should_execute_tools

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


# ============================================================================
# Tool Call Buffer Management
# ============================================================================


class ToolCallBuffer:
    """
    Buffer for managing tool call state during streaming/non-streaming responses.

    This class handles edge cases in tool call processing:
    - Empty or None arguments
    - Already-parsed dictionary arguments
    - Truncated/incomplete JSON in arguments
    - Validation that tool calls are complete and executable
    - Streaming: incremental argument buffering
    - Streaming: finish_reason tracking for completion detection

    The buffer is keyed by tool_call_id to track each tool call independently.

    In STREAMING mode:
    - Tool call arguments arrive incrementally across multiple chunks
    - Each chunk adds more text to the arguments string
    - The LAST chunk has finish_reason set (not None)
    - Tool calls are marked "finished" only when finish_reason is present
    - Tool execution happens AFTER finish_reason indicates completion

    Attributes:
        buffer: Dict mapping tool_call_id -> tool call data
        finished_tool_ids: Set of tool_call_ids that have seen finish_reason

    Example:
        ```python
        # Non-streaming: single add
        buffer = ToolCallBuffer()
        buffer.add_tool_call(
            tool_call_id="call_abc123",
            tool_name="search",
            arguments='{"query": "python async"}',
            tool_type="function"
        )

        # Streaming: incremental adds + finish_reason
        buffer = ToolCallBuffer()
        # Chunk 1: initial tool call with partial args
        buffer.add_tool_call("call_123", "search", '{"query":', "function")
        # Chunk 2: more args
        buffer.append_arguments("call_123", ' "python')
        # Chunk 3: final args, but no finish_reason yet
        buffer.append_arguments("call_123", ' async"}')
        # Chunk 4: finish_reason signals completion
        buffer.mark_finished_by_finish_reason("call_123")

        # Now ready for execution
        if buffer.is_finished("call_123"):
            tool_data = buffer.get_tool_call("call_123")
            parsed_args = buffer.parse_arguments("call_123")
        ```
    """

    def __init__(self):
        """Initialize empty tool call buffer."""
        self.buffer: Dict[str, Dict[str, Any]] = {}
        self.finished_tool_ids: set[str] = set()  # Track which tools saw finish_reason
        self.retry_counts: Dict[str, int] = {}  # Track retry attempts per tool call
        self.error_history: Dict[str, List[str]] = {}  # Track error types per tool call
        self.id_mapping: Dict[str, str] = (
            {}
        )  # Maps chunk_id -> tool_call_id for streaming correlation

    def add_tool_call(
        self,
        tool_call_id: Optional[str],
        tool_name: str,
        arguments: Any,
        chunk_id: str,
        tool_type: str = "function",
    ) -> None:
        """
        Add or update a tool call in the buffer.

        In streaming mode, this may be called multiple times for the same
        tool_call_id as arguments arrive incrementally. Use append_arguments()
        for subsequent chunks.

        Handles ID correlation in streaming mode:
        - First chunk may contain BOTH tool_call_id and chunk_id
        - Tool call ID: actual tool identifier (e.g., 'toolu_xxx')
        - Chunk ID: completion/chunk identifier (e.g., 'chatcmpl-xxx')
        - Arguments may arrive with chunk_id instead of tool_call_id
        - Establishes mapping: chunk_id -> tool_call_id

        Args:
            tool_call_id: Unique identifier for this tool call
            tool_name: Name of the tool/function to call
            arguments: Arguments as string, dict, or None
            tool_type: Type of tool call (usually "function")
            chunk_id: Optional chunk/completion ID for correlation
        """

        # Establish ID correlation if chunk_id is provided and different from tool_call_id
        if chunk_id and tool_call_id:
            self.id_mapping[chunk_id] = tool_call_id
            logger.info(
                f"ToolCallBuffer: Established mapping chunk_id={chunk_id} -> tool_call_id={tool_call_id}"
            )

        # Check if this is a chunk_id that maps to a known tool_call_id
        if chunk_id in self.id_mapping:
            # This is a chunk_id - resolve to actual tool_call_id
            actual_tool_call_id = self.id_mapping[chunk_id]
            logger.info(
                f"ToolCallBuffer: Resolved chunk_id={tool_call_id} -> tool_call_id={actual_tool_call_id}"
            )
            tool_call_id = actual_tool_call_id
        if not tool_call_id:
            logger.error(
                f"ToolCallBuffer: ToolCallBuffer: No tool_call_id={tool_call_id}"
            )
            return

        if tool_call_id in self.buffer:
            # Update existing - preserve name if new name is empty/None
            existing = self.buffer[tool_call_id]
            updated_name = (
                existing["name"] if not tool_name else existing["name"] + tool_name
            )

            # For arguments, replace (don't append - use append_arguments for that)
            self.append_arguments(tool_call_id, arguments)
            existing = self.buffer[tool_call_id]

            self.buffer[tool_call_id] = {
                "id": tool_call_id,
                "name": updated_name,
                "arguments": existing["arguments"],
                "type": tool_type,
                "complete": existing["complete"],
                # "complete": self._is_arguments_complete(updated_arguments),
            }

            logger.debug(
                f"ToolCallBuffer: Updated tool_call_id={tool_call_id}, "
                f"name={updated_name}, complete={self.buffer[tool_call_id]['complete']}"
            )
        else:
            # New tool call
            self.buffer[tool_call_id] = {
                "id": tool_call_id,
                "name": tool_name,
                "arguments": arguments,
                "type": tool_type,
                "complete": self._is_arguments_complete(arguments),
            }

            logger.debug(
                f"ToolCallBuffer: Added tool_call_id={tool_call_id}, "
                f"name={tool_name}, complete={self.buffer[tool_call_id]['complete']}"
            )

    def append_arguments(self, tool_call_id: str, additional_arguments: str) -> None:
        """
        Append additional arguments to an existing tool call (STREAMING mode).

        In streaming mode, tool call arguments arrive incrementally. This method
        allows appending each chunk's arguments to the existing buffer.

        Handles ID resolution: if tool_call_id is actually a chunk_id that maps
        to a real tool_call_id, resolves it before appending.

        Args:
            tool_call_id: ID of existing tool call (or chunk_id that maps to one)
            additional_arguments: Additional argument text to append

        Raises:
            KeyError: If tool_call_id not found in buffer
        """
        # Check if this is a chunk_id that maps to a known tool_call_id
        if tool_call_id in self.id_mapping:
            actual_tool_call_id = self.id_mapping[tool_call_id]
            logger.debug(
                f"ToolCallBuffer: Resolved chunk_id={tool_call_id} -> tool_call_id={actual_tool_call_id} for append"
            )
            tool_call_id = actual_tool_call_id

        if tool_call_id not in self.buffer:
            raise KeyError(
                f"Cannot append to unknown tool_call_id: {tool_call_id}. "
                f"Call add_tool_call() first."
            )

        tool_data = self.buffer[tool_call_id]
        current_args = tool_data["arguments"]

        # Convert current args to string if needed
        if current_args is None or current_args == "":
            current_args = ""
        elif isinstance(current_args, dict):
            # Already parsed - this shouldn't happen in streaming, but handle gracefully
            logger.warning(
                f"ToolCallBuffer: Attempting to append to already-parsed dict args "
                f"for tool_call_id={tool_call_id}. Converting dict to JSON string."
            )
            current_args = json.dumps(current_args)
        elif not isinstance(current_args, str):
            current_args = str(current_args)

        # Append new arguments
        if additional_arguments:
            updated_args = current_args + additional_arguments
        else:
            updated_args = current_args

        # Update buffer
        tool_data["arguments"] = updated_args
        # tool_data["complete"] = self._is_arguments_complete(updated_args)

        logger.debug(
            f"ToolCallBuffer: Appended {len(additional_arguments) if additional_arguments else 0} chars "
            f"to tool_call_id={tool_call_id}, total length={len(updated_args)}, "
            f"complete={tool_data['complete']}"
        )

    def mark_finished_by_finish_reason(
        self, tool_call_id: Optional[str] = None
    ) -> None:
        """
        Mark tool call(s) as finished because finish_reason was received.

        In STREAMING mode, the last chunk has finish_reason set (not None).
        This is the authoritative signal that a tool call is complete and
        ready for execution.

        Args:
            tool_call_id: Specific tool call ID to mark finished.
                         If None, marks ALL buffered tool calls as finished
                         (useful when finish_reason applies to entire response).
        """
        if tool_call_id is not None:
            # Mark specific tool call as finished
            if tool_call_id in self.buffer:
                self.finished_tool_ids.add(tool_call_id)
                logger.debug(
                    f"ToolCallBuffer: Marked tool_call_id={tool_call_id} as finished "
                    f"(finish_reason received)"
                )
            else:
                logger.warning(
                    f"ToolCallBuffer: Cannot mark unknown tool_call_id={tool_call_id} as finished"
                )
        else:
            # Mark ALL tool calls as finished
            for tid in self.buffer.keys():
                self.finished_tool_ids.add(tid)
            logger.debug(
                f"ToolCallBuffer: Marked ALL {len(self.buffer)} tool call(s) as finished "
                f"(finish_reason received)"
            )

    def is_finished(self, tool_call_id: str) -> bool:
        """
        Check if a tool call is finished and ready for execution.

        A tool call is "finished" when:
        1. It exists in the buffer
        2. Its arguments are complete (valid JSON or empty)
        3. It has been explicitly marked finished by finish_reason

        Args:
            tool_call_id: ID of tool call to check

        Returns:
            True if tool call is finished and executable
        """
        if tool_call_id not in self.buffer:
            return False

        # Check if arguments are complete (valid JSON)
        if not self.buffer[tool_call_id]["complete"]:
            return False

        # Must be explicitly marked finished (finish_reason received)
        return tool_call_id in self.finished_tool_ids

    def _is_arguments_complete(self, arguments: Any) -> bool:
        """
        Check if arguments appear complete and parseable.

        Handles:
        - None or empty string -> complete (no args needed)
        - Already a dict -> complete
        - String: check if valid JSON
        - Truncated JSON -> incomplete

        Args:
            arguments: The arguments to validate

        Returns:
            True if arguments are complete and usable
        """
        # Case 1: None or empty string (no arguments needed)
        if arguments is None or arguments == "":
            return True

        # Case 2: Already parsed as dict
        if isinstance(arguments, dict):
            return True

        # Case 3: String - attempt JSON parse
        if isinstance(arguments, str):
            # Empty string already handled above
            arguments_stripped = arguments.strip()
            if not arguments_stripped:
                return True

            # Try to parse JSON
            try:
                json.loads(arguments_stripped)
                return True
            except json.JSONDecodeError as e:
                logger.warning(
                    f"ToolCallBuffer: Incomplete/invalid JSON arguments: {e}\n"
                    f"Arguments: {arguments_stripped[:100]}..."
                )
                return False

        # Case 4: Unknown type - log warning but consider complete
        logger.warning(
            f"ToolCallBuffer: Unexpected argument type {type(arguments)}, "
            f"treating as complete"
        )
        return True

    def is_complete(self, tool_call_id: str) -> bool:
        """
        Check if a tool call's arguments are complete (valid JSON).

        DEPRECATED: Use is_finished() instead, which also checks finish_reason.

        This method only checks if arguments are parseable JSON, but does NOT
        check if finish_reason was received (streaming mode). For proper
        execution readiness, use is_finished().

        Args:
            tool_call_id: ID of tool call to check

        Returns:
            True if tool call exists and arguments are complete
        """
        if tool_call_id not in self.buffer:
            return False
        return self.buffer[tool_call_id]["complete"]

    def get_tool_call(self, tool_call_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve tool call data by ID.

        Args:
            tool_call_id: ID of tool call to retrieve

        Returns:
            Tool call data dict or None if not found
        """
        return self.buffer.get(tool_call_id)

    def parse_arguments(self, tool_call_id: str) -> Dict[str, Any]:
        """
        Parse and return arguments for a tool call.

        This method handles multiple argument formats defensively:
        - None or empty string -> return {}
        - Already a dict -> return as-is
        - Valid JSON string -> parse and return
        - Invalid JSON -> raise ValueError with context

        Args:
            tool_call_id: ID of tool call

        Returns:
            Parsed arguments as dictionary

        Raises:
            KeyError: If tool_call_id not found in buffer
            ValueError: If arguments cannot be parsed
        """
        if tool_call_id not in self.buffer:
            raise KeyError(f"Tool call ID {tool_call_id} not found in buffer")

        tool_data = self.buffer[tool_call_id]
        arguments = tool_data["arguments"]
        tool_name = tool_data["name"]

        # Case 1: None or empty -> no arguments
        if arguments is None or arguments == "":
            logger.debug(f"Tool {tool_name} ({tool_call_id}): No arguments")
            return {}

        # Case 2: Already a dict
        if isinstance(arguments, dict):
            logger.debug(f"Tool {tool_name} ({tool_call_id}): Arguments already parsed")
            return arguments

        # Case 3: String - parse JSON
        if isinstance(arguments, str):
            arguments_stripped = arguments.strip()

            # Empty after stripping
            if not arguments_stripped:
                logger.debug(
                    f"Tool {tool_name} ({tool_call_id}): Empty arguments string"
                )
                return {}

            # Parse JSON
            try:
                parsed = json.loads(arguments_stripped)
                logger.debug(
                    f"Tool {tool_name} ({tool_call_id}): "
                    f"Parsed {len(parsed) if isinstance(parsed, dict) else 0} arguments"
                )
                return parsed if isinstance(parsed, dict) else {}

            except json.JSONDecodeError as e:
                error_msg = (
                    f"Tool {tool_name} ({tool_call_id}): Failed to parse arguments JSON: {e}\n"
                    f"Arguments (first 200 chars): {arguments_stripped[:200]}"
                )
                logger.error(error_msg)
                raise ValueError(error_msg) from e

        # Case 4: Unexpected type
        error_msg = (
            f"Tool {tool_name} ({tool_call_id}): "
            f"Unexpected argument type {type(arguments)}: {arguments}"
        )
        logger.error(error_msg)
        raise ValueError(error_msg)

    def get_all_finished_tool_calls(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all finished tool calls ready for execution.

        This respects both argument completeness AND finish_reason status.
        Use this method to get executable tool calls.

        Returns:
            Dict mapping tool_call_id -> tool call data for finished calls
        """
        return {
            call_id: call_data
            for call_id, call_data in self.buffer.items()
            if self.is_finished(call_id)
        }

    def get_all_complete_tool_calls(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all tool calls with complete arguments (valid JSON).

        DEPRECATED: Use get_all_finished_tool_calls() instead.

        This method only checks argument completeness, NOT finish_reason.
        For proper execution readiness, use get_all_finished_tool_calls().

        Returns:
            Dict mapping tool_call_id -> tool call data for complete calls
        """
        return {
            call_id: call_data
            for call_id, call_data in self.buffer.items()
            if call_data["complete"]
        }

    def get_incomplete_tool_calls(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all incomplete tool calls (for debugging/logging).

        Returns:
            Dict mapping tool_call_id -> tool call data for incomplete calls
        """
        return {
            call_id: call_data
            for call_id, call_data in self.buffer.items()
            if not call_data["complete"]
        }

    def get_unfinished_tool_calls(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all unfinished tool calls (haven't seen finish_reason yet).

        Useful for debugging streaming issues.

        Returns:
            Dict mapping tool_call_id -> tool call data for unfinished calls
        """
        return {
            call_id: call_data
            for call_id, call_data in self.buffer.items()
            if not self.is_finished(call_id)
        }

    def clear(self) -> None:
        """Clear all buffered tool calls."""
        self.buffer.clear()
        logger.debug("ToolCallBuffer: Cleared all tool calls")

    def __len__(self) -> int:
        """Return number of tool calls in buffer."""
        return len(self.buffer)

    def __contains__(self, tool_call_id: str) -> bool:
        """Check if tool_call_id exists in buffer."""
        return tool_call_id in self.buffer

    def increment_retry_count(self, tool_call_id: str) -> int:
        """
        Increment retry count for a tool call.

        Args:
            tool_call_id: ID of the tool call

        Returns:
            Current retry count after incrementing
        """
        current_count = self.retry_counts.get(tool_call_id, 0)
        self.retry_counts[tool_call_id] = current_count + 1
        
        logger.info(
            f"ToolCallBuffer: Retry count for {tool_call_id}: {self.retry_counts[tool_call_id]}",
            extra={
                "tool_call_id": tool_call_id,
                "retry_count": self.retry_counts[tool_call_id]
            }
        )
        
        return self.retry_counts[tool_call_id]

    def get_retry_count(self, tool_call_id: str) -> int:
        """
        Get current retry count for a tool call.

        Args:
            tool_call_id: ID of the tool call

        Returns:
            Current retry count (0 if never retried)
        """
        return self.retry_counts.get(tool_call_id, 0)

    def should_retry(self, tool_call_id: str, max_retries: int = 2) -> bool:
        """
        Check if a tool call should be retried based on retry count.

        Args:
            tool_call_id: ID of the tool call
            max_retries: Maximum number of retries allowed (default: 2)

        Returns:
            True if retry count is below max_retries
        """
        current_count = self.get_retry_count(tool_call_id)
        should_retry = current_count < max_retries
        
        logger.debug(
            f"ToolCallBuffer: Retry check for {tool_call_id}: "
            f"count={current_count}, max={max_retries}, should_retry={should_retry}"
        )
        
        return should_retry

    def record_error(self, tool_call_id: str, error_type: str) -> None:
        """
        Record an error for a tool call.

        Args:
            tool_call_id: ID of the tool call
            error_type: Type of error that occurred
        """
        if tool_call_id not in self.error_history:
            self.error_history[tool_call_id] = []
        
        self.error_history[tool_call_id].append(error_type)
        
        logger.info(
            f"ToolCallBuffer: Recorded error for {tool_call_id}: {error_type}",
            extra={
                "tool_call_id": tool_call_id,
                "error_type": error_type,
                "error_count": len(self.error_history[tool_call_id])
            }
        )

    def get_error_history(self, tool_call_id: str) -> List[str]:
        """
        Get error history for a tool call.

        Args:
            tool_call_id: ID of the tool call

        Returns:
            List of error types that occurred
        """
        return self.error_history.get(tool_call_id, [])


# ============================================================================
# Application Lifecycle Management
# ============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    FastAPI lifespan context manager for startup and shutdown.

    Startup:
        1. Initialize session manager (persistent httpx.AsyncClient)
        2. Inject client into LiteLLM SDK
        3. Load configuration from config.yaml
        4. Initialize memory router
        5. Configure LiteLLM settings

    Shutdown:
        1. Close persistent session
        2. Log final statistics

    Args:
        app: FastAPI application instance

    Yields:
        None during application runtime
    """
    logger.info("=" * 70)
    logger.info("STARTUP: Initializing LiteLLM SDK Proxy")
    logger.info("=" * 70)

    # Startup Phase
    try:
        # 1. Initialize session manager
        logger.info("Step 1/5: Initializing session manager...")
        client = await LiteLLMSessionManager.get_client()
        logger.info(f"  Client ID: {id(client)}")
        logger.info(f"  Session info: {LiteLLMSessionManager.get_session_info()}")

        # 2. Inject into LiteLLM SDK
        logger.info("Step 2/5: Injecting client into LiteLLM SDK...")
        litellm.aclient_session = client
        logger.info(
            f"  Verified: litellm.aclient_session ID = {id(litellm.aclient_session)}"
        )

        # 3. Load configuration
        logger.info("Step 3/5: Loading configuration...")
        config_path = os.getenv("LITELLM_CONFIG_PATH", "config/config.yaml")
        config = LiteLLMConfig(config_path=config_path)
        app.state.config = config
        # Resilient len() check for Mock objects in tests
        model_count = (
            len(config.get_all_models())
            if hasattr(config, "get_all_models")
            and hasattr(config.get_all_models(), "__len__")
            else "unknown"
        )
        logger.info(f"  Loaded {model_count} model configurations:")
        logger.info(Path(config_path).read_text())
        logger.info(f"  Master key configured: {bool(config.get_master_key())}")

        # 4. Initialize memory router
        logger.info("Step 4/5: Initializing memory router...")
        memory_router = MemoryRouter(config=config.config)
        app.state.memory_router = memory_router
        # Resilient len() check for Mock objects in tests
        pattern_count = (
            len(memory_router.header_patterns)
            if hasattr(memory_router.header_patterns, "__len__")
            else "unknown"
        )
        logger.info(f"  Memory router initialized with {pattern_count} patterns")

        # 5. Configure LiteLLM settings
        logger.info("Step 5/6: Configuring LiteLLM settings...")
        litellm_cfg = config.get_litellm_settings()
        
        litellm.set_verbose = litellm_cfg.get("set_verbose", True)
        litellm.drop_params = litellm_cfg.get("drop_params", True)
        logger.info(f"  Verbose logging: {litellm.set_verbose}")
        logger.info(f"  Drop unknown params: {litellm.drop_params}")

        # Initialize Callbacks (OTel, Prisma, Debug)
        logger.info("  Initializing callbacks...")
        callbacks = []
        callback_names = []

        # 1. Tool Debug Logger (Always enabled for debugging)
        from proxy.tool_debug_logger import ToolDebugLogger
        tool_debug = ToolDebugLogger()
        callbacks.append(tool_debug)
        # Custom loggers don't need to be in callback_names for success_callback list if passed in 'callbacks'
        # but for clarity we manage the global list
        
        # 2. OpenTelemetry
        if litellm_cfg.get("otel", False):
            logger.info("  + Enabling OpenTelemetry callback")
            callback_names.append("otel")
            
        # 3. Prisma/Postgres
        if litellm_cfg.get("database_url"):
            logger.info("  + Enabling Prisma/Postgres callback")
            postgres_logger = PrismaProxyLogger(use_redis_buffer=False)
            callbacks.append(postgres_logger)
            callback_names.append("prisma_proxy")

        # Register callbacks globally
        litellm.callbacks = callbacks
        litellm.success_callback = callback_names
        litellm.failure_callback = callback_names
        logger.info(f"  Active callbacks: {callback_names} + ToolDebugLogger")

        # Initialize error handler
        app.state.error_handler = LiteLLMErrorHandler(
            include_debug_info=litellm_cfg.get("set_verbose", False)
        )

        # 6. Initialize tool executor
        logger.info("Step 6/6: Initializing tool executor...")
        tool_exec_config_dict = config.config.tool_execution or {}
        tool_exec_config = ToolExecutionConfig.from_config_dict(tool_exec_config_dict)

        if should_execute_tools(tool_exec_config):
            try:
                tool_executor = ToolExecutor(
                    supermemory_api_key=tool_exec_config.supermemory_api_key,
                    supermemory_base_url=tool_exec_config.supermemory_base_url,
                    timeout=tool_exec_config.timeout_per_tool,
                    max_results=(
                        tool_exec_config_dict.get("max_results", 5)
                        if isinstance(tool_exec_config_dict, dict)
                        else 5
                    ),
                )
                app.state.tool_executor = tool_executor
                app.state.tool_exec_config = tool_exec_config
                logger.info(
                    f"  ✅ Tool executor initialized (max_iterations={tool_exec_config.max_iterations})"
                )
            except Exception as e:
                logger.warning(f"  ⚠️  Tool executor initialization failed: {e}")
                app.state.tool_executor = None
                app.state.tool_exec_config = None
        else:
            logger.info("  Tool execution disabled")
            app.state.tool_executor = None
            app.state.tool_exec_config = None

        logger.info("=" * 70)
        logger.info("STARTUP COMPLETE - Server ready to accept requests")
        logger.info("=" * 70)

        logger.info("STARTUP ENVIRONMENT VARIABLES: %s", dict(os.environ))
        yield  # Application runs here

    except Exception as e:
        logger.error(f"STARTUP FAILED: {e}", exc_info=True)
        raise

    # Shutdown Phase
    logger.info("=" * 70)
    logger.info("SHUTDOWN: Cleaning up resources")
    logger.info("=" * 70)

    try:
        # Get final statistics
        session_info = LiteLLMSessionManager.get_session_info()
        logger.info(f"Final session stats: {session_info}")

        # Close session manager
        await LiteLLMSessionManager.close()
        logger.info("Session manager closed successfully")

    except Exception as e:
        logger.error(f"Error during shutdown: {e}", exc_info=True)

    logger.info("=" * 70)
    logger.info("SHUTDOWN COMPLETE")
    logger.info("=" * 70)


# ============================================================================
# FastAPI Application
# ============================================================================

app = FastAPI(
    title="LiteLLM SDK Proxy with Memory Routing",
    description="OpenAI-compatible proxy using LiteLLM SDK with persistent sessions and memory isolation",
    version="1.0.0",
    lifespan=lifespan,
    debug=True,
)

# Register error handlers
register_exception_handlers(app, include_debug_info=bool(os.getenv("DEBUG", False)))


# ============================================================================
# HTTPException Handler (OpenAI Format Compatibility)
# ============================================================================


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """
    Convert FastAPI HTTPException to OpenAI-compatible error format.

    This handler ensures all HTTP errors return OpenAI's standard error format:
    {"error": {"message": "...", "type": "...", "code": "..."}}

    Args:
        request: FastAPI request object
        exc: HTTPException instance

    Returns:
        JSONResponse with OpenAI-compatible error format
    """
    # Map status codes to OpenAI error types
    error_type_map = {
        400: "invalid_request_error",
        401: "authentication_error",
        403: "permission_error",
        404: "not_found_error",
        408: "timeout_error",
        429: "rate_limit_error",
        500: "api_error",
        503: "service_unavailable_error",
    }

    error_type = error_type_map.get(exc.status_code, "api_error")

    # Build base error response
    error_content: Dict[str, Any] = {
        "message": exc.detail,
        "type": error_type,
    }

    # Add specific error codes based on status and message
    detail_lower = str(exc.detail).lower()

    if exc.status_code == 401:
        error_content["code"] = "invalid_api_key"
    elif exc.status_code == 404:
        error_content["code"] = "model_not_found"
    elif exc.status_code == 400:
        if "model" in detail_lower and "missing" in detail_lower:
            error_content["code"] = "missing_parameter"
            error_content["param"] = "model"
        elif "messages" in detail_lower and "missing" in detail_lower:
            error_content["code"] = "missing_parameter"
            error_content["param"] = "messages"
        elif "json" in detail_lower or "invalid" in detail_lower:
            error_content["code"] = "invalid_request"
        else:
            error_content["code"] = "invalid_parameter"

    # Log the error
    logger.warning(
        f"HTTP {exc.status_code}: {exc.detail}",
        extra={"status_code": exc.status_code, "path": request.url.path},
    )

    return JSONResponse(
        status_code=exc.status_code,
        content={"error": error_content},
    )


# ============================================================================
# Dependency Injection
# ============================================================================


def get_config() -> LiteLLMConfig:
    """Dependency: Get LiteLLM configuration."""
    return app.state.config


def get_memory_router() -> MemoryRouter:
    """Dependency: Get memory router."""
    return app.state.memory_router


def get_error_handler() -> LiteLLMErrorHandler:
    """Dependency: Get error handler."""
    return app.state.error_handler


def get_tool_executor() -> Optional[ToolExecutor]:
    """Dependency: Get tool executor (may be None if disabled)."""
    return getattr(app.state, "tool_executor", None)


def get_tool_exec_config() -> Optional[ToolExecutionConfig]:
    """Dependency: Get tool execution config (may be None if disabled)."""
    return getattr(app.state, "tool_exec_config", None)


def should_use_context_retrieval(model_name: str, config: LiteLLMConfig) -> bool:
    """
    Check if context retrieval should be used for the given model.

    Args:
        model_name: The model name to check
        config: LiteLLM configuration

    Returns:
        True if context retrieval is enabled and model is allowed, False otherwise
    """
    try:
        # Get context retrieval config - handle both Pydantic models and dicts
        if hasattr(config.config, "context_retrieval"):
            # Pydantic model (production)
            context_retrieval_obj = config.config.context_retrieval
            if context_retrieval_obj is None:
                return False
            context_config = (
                context_retrieval_obj.model_dump()
                if hasattr(context_retrieval_obj, "model_dump")
                else context_retrieval_obj
            )
        elif isinstance(config.config, dict):
            # Dict (tests)
            context_config = config.config.get("context_retrieval")
            if context_config is None:
                return False
        else:
            logger.debug("Context retrieval config not found")
            return False

        if not context_config or not context_config.get("enabled", False):
            logger.debug("Context retrieval is disabled globally")
            return False

        # Check model-specific filters
        enabled_for_models = context_config.get("enabled_for_models")
        disabled_for_models = context_config.get("disabled_for_models")

        # If enabled_for_models is specified, only those models are allowed
        if enabled_for_models is not None:
            if model_name in enabled_for_models:
                logger.debug(f"Context retrieval enabled for model: {model_name}")
                return True
            else:
                logger.debug(f"Context retrieval not enabled for model: {model_name}")
                return False

        # If disabled_for_models is specified, those models are disallowed
        if disabled_for_models is not None:
            if model_name in disabled_for_models:
                logger.debug(f"Context retrieval disabled for model: {model_name}")
                return False
            else:
                logger.debug(f"Context retrieval enabled for model: {model_name}")
                return True

        # If neither filter is specified, enable for all models
        logger.debug(f"Context retrieval enabled for all models (no filters)")
        return True

    except Exception as e:
        logger.error(f"Error checking context retrieval config: {e}")
        return False


async def apply_context_retrieval(
    messages: list,
    model_name: str,
    user_id: str,
    config: LiteLLMConfig,
) -> list:
    """
    Apply context retrieval to messages if enabled.

    Args:
        messages: Original chat messages
        model_name: Model name for filtering
        user_id: User ID for memory isolation
        config: LiteLLM configuration

    Returns:
        Enhanced messages with context, or original messages if retrieval fails/disabled
    """
    if not should_use_context_retrieval(model_name, config):
        return messages

    try:
        # Get context retrieval configuration - handle both Pydantic models and dicts
        if hasattr(config.config, "context_retrieval"):
            # Pydantic model (production)
            context_retrieval_obj = config.config.context_retrieval
            if context_retrieval_obj is None:
                return messages
            context_config = (
                context_retrieval_obj.model_dump()
                if hasattr(context_retrieval_obj, "model_dump")
                else context_retrieval_obj
            )
        elif isinstance(config.config, dict):
            # Dict (tests)
            context_config = config.config.get("context_retrieval", {})
        else:
            logger.warning("Context retrieval config not found")
            return messages

        # Get API key (resolve environment variable if needed)
        api_key = context_config.get("api_key")
        if isinstance(api_key, str) and api_key.startswith("os.environ/"):
            env_var = api_key.split("/", 1)[1]
            api_key = os.getenv(env_var)

        if not api_key:
            logger.warning("Context retrieval enabled but SUPERMEMORY_API_KEY not set")
            return messages

        # Get persistent HTTP client from session manager
        http_client = await LiteLLMSessionManager.get_client()

        # Initialize ContextRetriever with config values
        retriever = ContextRetriever(
            api_key=api_key,
            base_url=context_config.get("base_url", "https://api.supermemory.ai"),
            http_client=http_client,
            default_container_tag=context_config.get("container_tag", "supermemory"),
            max_context_length=context_config.get("max_context_length", 4000),
            timeout=context_config.get("timeout", 10.0),
        )

        # Retrieve and inject context
        enhanced_messages, metadata = await retrieve_and_inject_context(
            retriever=retriever,
            messages=messages,
            user_id=user_id,
            query_strategy=context_config.get("query_strategy", "last_user"),
            injection_strategy=context_config.get("injection_strategy", "system"),
            container_tag=context_config.get("container_tag"),
        )

        if metadata:
            logger.info(
                f"Context retrieval successful: {metadata.get('results_count', 0)} results, "
                f"query='{metadata.get('query', 'N/A')}'"
            )
        else:
            logger.info("Context retrieval returned no results")

        return enhanced_messages

    except Exception as e:
        logger.error(
            f"Context retrieval failed, using original messages: {e}", exc_info=True
        )
        return messages


# ============================================================================
# Authentication Middleware
# ============================================================================


async def verify_api_key(request: Request) -> None:
    """
    Verify API key from Authorization header.

    Args:
        request: FastAPI request object

    Raises:
        HTTPException: 401 if invalid or missing API key
    """
    config = get_config()
    auth_header = request.headers.get("authorization", "")

    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
        )

    provided_key = auth_header[7:]  # Remove "Bearer " prefix

    if provided_key != config.get_master_key():
        logger.warning(f"Invalid API key attempt from {request.client.host}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )


# ============================================================================
# API Endpoints
# ============================================================================


@app.get("/health")
async def health_check() -> Dict[str, Any]:
    """
    Health check endpoint.

    Returns:
        Dict with status and session information
    """
    session_info = LiteLLMSessionManager.get_session_info()
    config = get_config()

    # Resilient len() check for Mock objects in tests
    models = config.get_all_models()
    models_count = len(models) if hasattr(models, "__len__") else "unknown"

    return {
        "status": "healthy",
        "version": "1.0.0",
        "session": session_info,
        "models_configured": models_count,
        "litellm_sdk_injected": litellm.aclient_session is not None,
    }


@app.get("/memory-routing/info")
async def memory_routing_info(request: Request) -> Dict[str, Any]:
    """
    Get memory routing information for debugging.

    Returns detailed information about how the current request would be routed,
    including user ID detection and pattern matching.

    Args:
        request: FastAPI request object

    Returns:
        Dict with routing information
    """
    memory_router = get_memory_router()
    routing_info = memory_router.get_routing_info(request.headers)

    return {
        "routing": routing_info,
        "request_headers": dict(request.headers),
        "session_info": LiteLLMSessionManager.get_session_info(),
    }


@app.get("/v1/models")
async def list_models(request: Request) -> Dict[str, Any]:
    """
    List available models (OpenAI-compatible endpoint).

    Args:
        request: FastAPI request object

    Returns:
        Dict with list of available models
    """
    await verify_api_key(request)

    config = get_config()

    models = [
        {
            "id": model_config.model_name,
            "object": "model",
            "created": int(time.time()),
            "owned_by": "litellm",
            "permission": [],
            "root": model_config.model_name,
            "parent": None,
        }
        for model_name in config.get_all_models()
        if (model_config := config.get_model_config(model_name))
    ]

    return {
        "object": "list",
        "data": models,
    }


@app.post("/v1/chat/completions")
async def chat_completions(request: Request) -> Response:
    """
    OpenAI-compatible chat completions endpoint.

    Supports both streaming and non-streaming responses.
    Automatically injects memory routing headers based on client detection.

    Args:
        request: FastAPI request object

    Returns:
        JSONResponse for non-streaming, StreamingResponse for streaming

    Raises:
        HTTPException: For various error conditions
    """
    # Verify API key
    await verify_api_key(request)

    # Parse request body
    try:
        body = await request.json()
    except Exception as e:
        logger.error(f"Failed to parse request body: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid JSON in request body: {e}",
        )

    logger.info(f"Request headers: {request.headers.items()}")
    logger.info(f"Request body: {body}")

    # Extract parameters
    model_name = body.get("model")
    messages = body.get("messages")
    stream = body.get("stream", False)

    if not model_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required parameter: model",
        )

    if not messages:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required parameter: messages",
        )

    # Get configuration and routing
    config = get_config()
    memory_router = get_memory_router()
    error_handler = get_error_handler()

    # Get LiteLLM parameters for this model
    try:
        litellm_params = config.get_litellm_params(model_name)
    except ValueError as e:
        logger.error(f"Model not found: {model_name}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )

    # Inject memory routing headers
    user_id = memory_router.detect_user_id(request.headers)
    logger.info(f"Request for model '{model_name}' routed to user_id: {user_id}")

    # Merge extra headers (memory routing + any from config)
    extra_headers = litellm_params.get("extra_headers", {}).copy()
    extra_headers["x-sm-user-id"] = user_id

    # Check if we need to inject Supermemory API key
    supermemory_key = os.getenv("SUPERMEMORY_API_KEY")
    if supermemory_key and memory_router.should_use_supermemory(model_name):
        extra_headers["x-supermemory-api-key"] = supermemory_key
        logger.debug(f"Injected Supermemory API key for model: {model_name}")

    litellm_params["extra_headers"] = extra_headers

    # Merge additional parameters from request body
    for key, value in body.items():
        if key not in ["model", "messages"]:
            litellm_params[key] = value

    # Generate request ID for tracking
    request_id = f"req_{int(time.time() * 1000)}"

    # Log request details
    logger.info(
        f"[{request_id}] Starting {'streaming' if stream else 'non-streaming'} request"
    )
    logger.info(f"[{request_id}] Model: {model_name}, User ID: {user_id}")

    # Apply context retrieval if enabled
    messages = await apply_context_retrieval(
        messages=messages,
        model_name=model_name,
        user_id=user_id,
        config=config,
    )

    # Initialize tool executor (if tools are configured)
    tool_executor = None
    # Get global config for defaults
    global_tool_config = get_tool_exec_config()
    max_iterations = global_tool_config.max_iterations if global_tool_config else 10
    
    tool_config = ToolExecutionConfig(
        supermemory_api_key=supermemory_key,
        enabled=memory_router.should_use_supermemory(model_name),
    )
    if tool_config.enabled:
        tool_executor = ToolExecutor(
            tool_config.supermemory_api_key or "",
            tool_config.supermemory_base_url,
            tool_config.timeout_per_tool,
            max_results=5,  # Explicit max_results
        )
        logger.info(f"[{request_id}] Tool execution enabled (max_iterations={max_iterations})")
        
        # Inject tool definitions if not already present
        if "tools" not in litellm_params:
            litellm_params["tools"] = tool_executor.get_tool_definitions()
            # Force tool choice to auto if tools are present
            if "tool_choice" not in litellm_params:
                litellm_params["tool_choice"] = "auto"
            logger.debug(f"[{request_id}] Injected {len(litellm_params['tools'])} tool definitions")

    # Handle streaming vs non-streaming
    if stream:
        return await handle_streaming_completion(
            messages=messages,
            litellm_params=litellm_params,
            request_id=request_id,
            error_handler=error_handler,
            user_id=user_id,
            tool_executor=tool_executor,
            max_iterations=max_iterations,
        )
    else:
        return await handle_non_streaming_completion(
            messages=messages,
            litellm_params=litellm_params,
            request_id=request_id,
            error_handler=error_handler,
            user_id=user_id,
        )


# ============================================================================
# Completion Handlers
# ============================================================================


async def handle_non_streaming_completion(
    messages: list,
    litellm_params: Dict[str, Any],
    request_id: str,
    error_handler: LiteLLMErrorHandler,
    user_id: Optional[str] = None,
) -> JSONResponse:
    """
    Handle non-streaming completion request with automatic tool execution.

    This function implements a robust tool execution loop with defensive handling:

    Tool Call Processing:
    1. Extracts tool_calls from LLM response
    2. Buffers tool calls with validation (ToolCallBuffer)
    3. Validates arguments are complete and parseable
    4. Executes complete tool calls via ToolExecutor
    5. Handles partial/incomplete tool calls gracefully
    6. Appends tool results to messages and calls LLM again
    7. Repeats until final text response (no more tool_calls)

    Edge Cases Handled:
    - Empty arguments (None, "", {})
    - Already-parsed dict arguments (no re-parsing)
    - Truncated/invalid JSON in arguments
    - Missing tool executor (returns response as-is)
    - Tool execution failures (returns error message to LLM)
    - Maximum iteration limit (prevents infinite loops)

    Args:
        messages: Chat messages list (modified in-place with tool results)
        litellm_params: Parameters for litellm.acompletion()
        request_id: Request tracking ID for logging
        error_handler: Error handler instance for exception conversion
        user_id: User ID for tool execution context (optional, default: "default")

    Returns:
        JSONResponse with completion result (final text response or tool_calls if not executed)

    Example:
        ```python
        response = await handle_non_streaming_completion(
            messages=[{"role": "user", "content": "Search for Python async"}],
            litellm_params={"model": "claude-sonnet-4.5"},
            request_id="req_123",
            error_handler=error_handler,
            user_id="user_123"
        )
        ```
    """
    try:
        start_time = time.time()

        # Get tool executor and config
        tool_executor = get_tool_executor()
        tool_exec_config = get_tool_exec_config()

        # Tool execution loop
        iteration = 0
        max_iterations = tool_exec_config.max_iterations if tool_exec_config else 10

        while iteration < max_iterations:
            iteration += 1
            logger.info(
                f"[{request_id}] Tool execution iteration {iteration}/{max_iterations}"
            )

            # Call LiteLLM SDK
            response = await litellm.acompletion(
                messages=messages,
                **litellm_params,
            )

            # Check if response has tool_calls
            has_tool_calls = False
            tool_calls = None

            chunk_id: str = getattr(response, "id", "")
            if chunk_id:
                logger.info(f"[{request_id}] Chunk ID: {chunk_id}")

            # Extract tool_calls from response (defensive extraction)
            if hasattr(response, "choices") and response.choices:
                choice = response.choices[0]
                if hasattr(choice, "message") and hasattr(choice.message, "tool_calls"):
                    tool_calls = choice.message.tool_calls
                    has_tool_calls = tool_calls is not None and len(tool_calls) > 0

            if not has_tool_calls:
                # No tool calls - return final response
                elapsed = time.time() - start_time
                logger.info(
                    f"[{request_id}] Completed in {elapsed:.2f}s (no tool calls)"
                )

                # Return OpenAI-compatible response
                response_dict = (
                    response.model_dump()
                    if hasattr(response, "model_dump")
                    else dict(response)
                )
                return JSONResponse(content=response_dict)

            # Check if tool executor is available
            if not tool_executor:
                logger.warning(
                    f"[{request_id}] Tool calls detected but tool executor not initialized"
                )
                # Return response as-is (client needs to handle tool calls)
                response_dict = (
                    response.model_dump()
                    if hasattr(response, "model_dump")
                    else dict(response) if response else None
                )
                return JSONResponse(content=response_dict)

            # Initialize tool call buffer for this iteration
            logger.info(f"[{request_id}] Processing {len(tool_calls)} tool call(s)")
            tool_buffer = ToolCallBuffer()

            # Buffer all tool calls with validation
            for tool_call in tool_calls:
                try:
                    # Extract tool call details (defensive attribute access)
                    tool_call_id = getattr(tool_call, "id", None)
                    tool_type = getattr(tool_call, "type", "function")

                    # Get function details
                    function = getattr(tool_call, "function", None)
                    if not function:
                        logger.warning(
                            f"[{request_id}] Tool call missing 'function' attribute, skipping"
                        )
                        continue

                    tool_name = getattr(function, "name", None)
                    tool_arguments = getattr(function, "arguments", None)

                    # Validate required fields
                    if not tool_call_id and not chunk_id:
                        logger.warning(
                            f"[{request_id}] Tool call missing 'id', skipping: {tool_call}"
                        )
                        continue

                    # if not tool_name:
                    #     logger.warning(
                    #         f"[{request_id}] Tool call {tool_call_id} missing 'name', skipping"
                    #     )
                    #     continue

                    # Add to buffer (handles argument validation)
                    tool_buffer.add_tool_call(
                        tool_call_id=tool_call_id,
                        tool_name=tool_name or "",
                        arguments=tool_arguments,
                        tool_type=tool_type,
                        chunk_id=chunk_id,
                    )

                except Exception as buffer_error:
                    logger.error(
                        f"[{request_id}] Error buffering tool call: {buffer_error}",
                        exc_info=True,
                    )
                    continue

            # In non-streaming mode, all tool calls arrive at once with finish_reason
            # Mark all buffered tool calls as finished (received with finish_reason)
            tool_buffer.mark_finished_by_finish_reason()

            # Check for incomplete tool calls
            incomplete_calls = tool_buffer.get_incomplete_tool_calls()
            if incomplete_calls:
                logger.warning(
                    f"[{request_id}] Found {len(incomplete_calls)} incomplete tool calls "
                    f"(truncated/invalid JSON). IDs: {list(incomplete_calls.keys())}"
                )

            # Get finished tool calls ready for execution
            finished_calls = tool_buffer.get_all_finished_tool_calls()

            if not finished_calls:
                logger.error(
                    f"[{request_id}] No finished tool calls to execute "
                    f"({len(tool_calls)} received, {len(incomplete_calls)} incomplete)"
                )
                # Return response as-is - cannot execute incomplete calls
                response_dict = (
                    response.model_dump()
                    if hasattr(response, "model_dump")
                    else dict(response)
                )
                return JSONResponse(content=response_dict)

            logger.info(
                f"[{request_id}] Executing {len(finished_calls)} finished tool call(s) "
                f"({len(incomplete_calls)} skipped as incomplete)"
            )

            # Append assistant message with tool_calls to messages
            # Use original tool_calls for message (preserves exact format)
            assistant_message = {
                "role": "assistant",
                "content": (
                    response.choices[0].message.content
                    if response.choices[0].message.content
                    else ""
                ),
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": tc.type,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in tool_calls
                ],
            }
            messages.append(assistant_message)

            # Execute each finished tool call
            for tool_call_id, tool_data in finished_calls.items():
                tool_name = tool_data["name"]

                logger.info(
                    f"[{request_id}] Executing tool: {tool_name} (id={tool_call_id})"
                )

                try:
                    # Parse arguments using buffer (robust parsing)
                    tool_args = tool_buffer.parse_arguments(tool_call_id)

                    logger.debug(
                        f"[{request_id}] Tool {tool_name}: Parsed {len(tool_args)} argument(s)"
                    )

                    # Execute tool via ToolExecutor
                    tool_result = await tool_executor.execute_tool_call(
                        tool_name=tool_name,
                        tool_args=tool_args,
                        user_id=user_id or "default",
                        tool_call_id=tool_call_id,
                    )
                    logger.info(
                        f"[{request_id}] Tool {tool_name}({", ".join(tool_args) if tool_args else 'no args'}): {tool_result}"
                    )

                    # Format tool result for LLM
                    tool_result_content = tool_executor.format_tool_result_for_llm(
                        tool_result
                    )

                    logger.info(
                        f"[{request_id}] Tool {tool_name} executed successfully "
                        f"(result length: {len(str(tool_result_content))} chars)"
                    )

                except ValueError as parse_error:
                    # Argument parsing failed - return detailed error to LLM
                    logger.error(
                        f"[{request_id}] Tool {tool_name} argument parsing failed: {parse_error}"
                    )
                    tool_result_content = (
                        f"Tool argument parsing error: {str(parse_error.__dict__)}\n\n"
                        f"The arguments provided could not be parsed. "
                        f"Please check the JSON format and try again."
                    )

                except Exception as tool_error:
                    # Tool execution failed - return error to LLM
                    logger.error(
                        f"[{request_id}] Tool {tool_name} execution failed: {tool_error}",
                        exc_info=True,
                    )
                    tool_result_content = (
                        f"Tool execution error: {type(tool_error).__name__}: {str(tool_error)}\n\n"
                        f"The tool encountered an error during execution."
                    )

                # Append tool result message (always append, even on error)
                tool_message = {
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": tool_result_content,
                }
                messages.append(tool_message)

            logger.info(
                f"[{request_id}] All tools executed, sending results back to LLM"
            )

        # Max iterations reached
        elapsed = time.time() - start_time
        logger.warning(
            f"[{request_id}] Max iterations ({max_iterations}) reached in {elapsed:.2f}s"
        )

        # Return last response even if it has tool_calls
        response_dict = (
            response.model_dump() if hasattr(response, "model_dump") else dict(response)
        )
        return JSONResponse(content=response_dict)

    except Exception as e:
        logger.error(f"[{request_id}] Error: {type(e).__name__}: {e}", exc_info=True)

        # Use error handler to convert to HTTP response
        return await error_handler.handle_completion_error(e, request_id=request_id)


async def handle_streaming_completion(
    messages: list,
    litellm_params: Dict[str, Any],
    request_id: str,
    error_handler: LiteLLMErrorHandler,
    user_id: Optional[str] = None,
    tool_executor: Optional[ToolExecutor] = None,
    max_iterations: int = 5,
) -> StreamingResponse:
    """
    Handle streaming completion request with tool call support.

    In streaming mode, tool calls arrive incrementally:
    1. Tool call ID and name arrive in early chunks
    2. Arguments are streamed across multiple chunks
    3. The LAST chunk has finish_reason set (not None)
    4. Tool execution happens AFTER finish_reason is received

    Args:
        messages: Chat messages
        litellm_params: Parameters for litellm.acompletion()
        request_id: Request tracking ID
        error_handler: Error handler instance
        user_id: User ID for tool execution context
        tool_executor: Tool executor instance (if tool execution enabled)
        max_iterations: Max tool call iterations

    Returns:
        StreamingResponse with SSE events
    """

    async def generate_stream() -> AsyncIterator[str]:
        """Generate SSE stream with tool call buffering."""
        try:
            start_time = time.time()
            iteration = 0
            current_messages = messages.copy()

            while iteration < max_iterations:
                iteration += 1

                # Initialize tool call buffer for this iteration
                tool_buffer = ToolCallBuffer()
                has_tool_calls = False
                saw_finish_reason = False

                # Call LiteLLM SDK with streaming
                litellm_params["stream"] = True
                response_iterator = await litellm.acompletion(
                    messages=current_messages,
                    **litellm_params,
                )

                logger.info(
                    f"[{request_id}] Starting stream (iteration {iteration})..."
                )
                if not isinstance(response_iterator, CustomStreamWrapper):
                    raise ValueError(
                        f"{response_iterator} should be an iterator but is: {type(response_iterator)}"
                    )

                # Track content for assistant message
                accumulated_content = ""

                # Stream chunks to client AND buffer tool calls
                async for chunk in response_iterator:
                    if not chunk:
                        continue
                    # Convert chunk to dict for analysis
                    if hasattr(chunk, "model_dump"):
                        chunk_dict = chunk.model_dump()
                    elif hasattr(chunk, "dict"):
                        chunk_dict = chunk.dict()
                    else:
                        chunk_dict = (
                            chunk if isinstance(chunk, dict) else {"data": str(chunk)}
                        )

                    if not isinstance(chunk, ModelResponseStream):
                        raise RuntimeError("invalid chunk type")
                        return
                    logger.debug("Got chunk %s", chunk)
                    id = chunk.id

                    # Check for tool calls in this chunk
                    choices = chunk.choices
                    if not choices:
                        continue
                    if len(choices) > 0:
                        choice = choices[0]

                        # Check for finish_reason
                        if choice.finish_reason is not None:
                            saw_finish_reason = True
                            logger.debug(
                                f"[{request_id}] Received finish_reason: {choice.finish_reason}"
                            )

                        # Check for tool calls in delta
                        if choice.delta and choice.delta.tool_calls:
                            delta_tool_calls = choice.delta.tool_calls

                            if delta_tool_calls:
                                has_tool_calls = True

                                for delta_tc in delta_tool_calls:
                                    tool_call_id = (
                                        delta_tc.id
                                        if hasattr(delta_tc, "id") and delta_tc.id
                                        else None
                                    )

                                    # Get tool name (may be None in subsequent chunks)
                                    tool_name = None
                                    if (
                                        hasattr(delta_tc, "function")
                                        and delta_tc.function
                                    ):
                                        tool_name = (
                                            delta_tc.function.name
                                            if hasattr(delta_tc.function, "name")
                                            else None
                                        )

                                    # Get arguments (may be partial/incremental)
                                    arguments = None
                                    if (
                                        hasattr(delta_tc, "function")
                                        and delta_tc.function
                                    ):
                                        arguments = (
                                            delta_tc.function.arguments
                                            if hasattr(delta_tc.function, "arguments")
                                            else None
                                        )
                                        # New tool call
                                        tool_buffer.add_tool_call(
                                            tool_call_id=tool_call_id,
                                            tool_name=tool_name or "",
                                            arguments=arguments or "",
                                            tool_type="function",
                                            chunk_id=id,  # Pass chunk ID for correlation
                                        )
                                        logger.debug(
                                            f"[{request_id}] Appended tool call: {tool_call_id}, "
                                            f"name={tool_name}, chunk_id={id}, args={arguments}"
                                        )

                        # Accumulate content
                        if hasattr(choice, "delta") and hasattr(
                            choice.delta, "content"
                        ):
                            if choice.delta.content:
                                accumulated_content += choice.delta.content

                    # Format as SSE and yield to client
                    try:
                        # Logic to hide tool calls from client if we are handling them internally
                        should_yield = True
                        
                        if tool_executor:
                            # Check if we need to modify the chunk to hide tool details
                            choices = chunk_dict.get("choices", [])
                            if choices:
                                choice = choices[0]
                                delta = choice.get("delta", {})
                                
                                # 1. Hide tool_calls in delta
                                if "tool_calls" in delta:
                                    # We are handling these internally, don't show to client
                                    del delta["tool_calls"]
                                    
                                # 2. Hide finish_reason if we are going to loop (have tool calls)
                                # If we saw tool calls, we expect to execute them and continue the stream
                                if has_tool_calls and choice.get("finish_reason"):
                                    choice["finish_reason"] = None
                                    
                                # 3. Check if there is anything left to yield
                                # If delta is empty (no content) and finish_reason is None, skip yielding
                                if not delta.get("content") and not choice.get("finish_reason"):
                                    should_yield = False
                                    
                        if should_yield:
                            sse_data = f"data: {json.dumps(chunk_dict)}\n\n"
                            yield sse_data
                    except (TypeError, ValueError) as e:
                        logger.error(
                            f"[{request_id}] Failed to serialize chunk to JSON: {e}",
                            exc_info=True,
                        )

                # Stream completed - check if we need to execute tools
                if has_tool_calls and saw_finish_reason:
                    # Mark all buffered tool calls as finished (received finish_reason)
                    tool_buffer.mark_finished_by_finish_reason()

                    logger.info(
                        f"[{request_id}] Stream finished with {len(tool_buffer)} tool call(s). "
                        f"finish_reason received: {saw_finish_reason}"
                    )

                    # Check if tool execution is enabled
                    tool_exec_cfg = get_tool_exec_config()
                    if not tool_exec_cfg:
                        raise RuntimeError("No tool exec config found")
                    if tool_executor and should_execute_tools(tool_exec_cfg):
                        # Get finished tool calls
                        finished_calls = tool_buffer.get_all_finished_tool_calls()
                        incomplete_calls = tool_buffer.get_incomplete_tool_calls()

                        if incomplete_calls:
                            logger.warning(
                                f"[{request_id}] {len(incomplete_calls)} incomplete tool calls "
                                f"(invalid JSON). IDs: {list(incomplete_calls.keys())}"
                            )

                        if finished_calls:
                            logger.info(
                                f"[{request_id}] Executing {len(finished_calls)} tool call(s):"
                            )
                            for finished_call in finished_calls:
                                logger.info(f"  - {repr(finished_call)})")

                            # Build assistant message with tool calls
                            # (reconstruct from buffer for message history)
                            assistant_message = {
                                "role": "assistant",
                                "content": (
                                    accumulated_content if accumulated_content else ""
                                ),
                                "tool_calls": [
                                    {
                                        "id": call_data["id"],
                                        "type": call_data["type"],
                                        "function": {
                                            "name": call_data["name"],
                                            "arguments": call_data["arguments"],
                                        },
                                    }
                                    for call_data in tool_buffer.buffer.values()
                                ],
                            }
                            current_messages.append(assistant_message)

                            # Execute each tool
                            for tool_call_id, tool_data in finished_calls.items():
                                tool_name = tool_data["name"]

                                try:
                                    # Send keep-alive to client to prevent timeout during tool execution
                                    yield ": processing tool execution\n\n"
                                    
                                    # Parse arguments
                                    tool_args = tool_buffer.parse_arguments(
                                        tool_call_id
                                    )

                                    # Execute tool
                                    tool_result = await tool_executor.execute_tool_call(
                                        tool_name=tool_name,
                                        tool_args=tool_args,
                                        user_id=user_id or "default",
                                        tool_call_id=tool_call_id,
                                    )

                                    # Format result
                                    tool_result_content = (
                                        tool_executor.format_tool_result_for_llm(
                                            tool_result
                                        )
                                    )

                                    logger.info(
                                        f"[{request_id}] Tool {tool_name} executed successfully"
                                    )

                                except Exception as tool_error:
                                    logger.error(
                                        f"[{request_id}] Tool {tool_name} execution failed: {tool_error}",
                                        exc_info=True,
                                    )

                                    # Provide structured error feedback to the LLM so it can self-correct
                                    fallback_result = {
                                        "tool_call_id": tool_call_id,
                                        "error": {
                                            "message": (
                                                f"Tool execution error: {type(tool_error).__name__}: {str(tool_error)}"
                                            ),
                                            "retry_hint": (
                                                "The tool encountered an error during execution. "
                                                "Please verify the arguments and try again."
                                            ),
                                        },
                                        "results": [],
                                    }
                                    tool_result_content = (
                                        tool_executor.format_tool_result_for_llm(fallback_result)
                                    )

                                # Append tool result message
                                tool_message = {
                                    "role": "tool",
                                    "tool_call_id": tool_call_id,
                                    "content": tool_result_content,
                                }
                                current_messages.append(tool_message)

                            # Continue to next iteration (send results back to LLM)
                            logger.info(
                                f"[{request_id}] Tools executed, continuing to iteration {iteration + 1}"
                            )
                            continue  # Next iteration with tool results
                        else:
                            # No executable tool calls
                            logger.warning(
                                f"[{request_id}] No executable tool calls "
                                f"({len(tool_buffer)} buffered, {len(incomplete_calls)} incomplete)"
                            )
                    else:
                        logger.info(
                            f"[{request_id}] Tool execution disabled or not configured, "
                            f"stream complete"
                        )

                # No tool calls or tool execution disabled - stream is complete
                break

            # Send completion signal
            elapsed = time.time() - start_time
            logger.info(f"[{request_id}] Stream completed in {elapsed:.2f}s")
            yield "data: [DONE]\n\n"

        except Exception as e:
            logger.error(f"[{request_id}] Stream error: {type(e).__name__}: {e}")

            # Send error as SSE event
            from proxy.streaming_utils import format_error_sse

            error_sse = format_error_sse(
                error_type=type(e).__name__,
                message=str(e),
                code=getattr(e, "status_code", None),
            )
            yield error_sse

    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


# ============================================================================
# Development/Testing Entry Point
# ============================================================================


if __name__ == "__main__":
    import uvicorn

    print("=" * 70)
    print("LiteLLM SDK Proxy - Development Server")
    print("=" * 70)
    print()
    print("Starting server on http://localhost:8764")
    print()
    print("Endpoints:")
    print("  - GET  /health                    - Health check")
    print("  - GET  /memory-routing/info       - Routing debug info")
    print("  - GET  /v1/models                 - List models")
    print("  - POST /v1/chat/completions       - Chat completions")
    print()
    print("Example request:")
    print("  curl http://localhost:8764/v1/chat/completions \\")
    print("    -H 'Content-Type: application/json' \\")
    print("    -H 'Authorization: Bearer sk-1234' \\")
    print(
        '    -d \'{"model": "claude-sonnet-4.5", "messages": [{"role": "user", "content": "Hello"}]}\''
    )
    print()
    print("=" * 70)

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8764,
        log_level="debug",
    )
