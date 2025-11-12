"""
SSE Streaming Utilities for LiteLLM SDK Proxy.

This module provides utilities for Server-Sent Events (SSE) streaming with
LiteLLM completions. It handles the conversion of LiteLLM streaming responses
to the OpenAI-compatible SSE format.

Key Features:
- Async generator for streaming chunks
- OpenAI-compatible SSE format ("data: {json}\\n\\n")
- Error handling within streams
- Completion signals ("data: [DONE]\\n\\n")
- Infinite loop protection
- Comprehensive logging

Architecture:
    Streaming is a critical feature for LLMs with long response times. This
    module ensures that clients receive incremental updates, improving
    perceived responsiveness and enabling real-time UX updates.

References:
    - docs/architecture/LITELLM_SDK_INTEGRATION_PATTERNS.md (Section 5)
    - https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events
"""

import json
import logging
from typing import AsyncIterator, Any, Dict, Optional

import litellm

logger = logging.getLogger(__name__)


# =============================================================================
# SSE Streaming Generator
# =============================================================================


async def stream_litellm_completion(
    response_iterator: AsyncIterator,
    request_id: Optional[str] = None,
    detect_infinite_loops: bool = True,
) -> AsyncIterator[str]:
    """
    Convert LiteLLM streaming response to SSE format.

    This async generator takes a LiteLLM streaming response iterator and
    yields Server-Sent Events (SSE) formatted strings suitable for HTTP
    streaming responses.

    SSE Format:
        Each chunk is formatted as: "data: {json}\\n\\n"
        The stream ends with: "data: [DONE]\\n\\n"

    Args:
        response_iterator: Async iterator from litellm.acompletion(stream=True)
        request_id: Optional request ID for logging context
        detect_infinite_loops: Whether to detect and warn on repeated chunks

    Yields:
        str: SSE-formatted strings ("data: {json}\\n\\n")

    Example:
        ```python
        response = await litellm.acompletion(..., stream=True)

        async for sse_chunk in stream_litellm_completion(response, "req-123"):
            # Send chunk to client
            yield sse_chunk
        ```

    Error Handling:
        Errors during streaming are caught and sent as SSE events, allowing
        the client to handle them gracefully without breaking the connection.
    """
    log_extra = {"request_id": request_id} if request_id else {}

    chunk_count = 0
    last_chunk_json = None
    repeated_chunk_count = 0
    max_chunks = 1000  # Safety limit to prevent infinite loops

    try:
        logger.debug(f"Starting stream processing", extra=log_extra)

        async for chunk in response_iterator:
            chunk_count += 1

            # Safety check: prevent infinite loops
            if chunk_count > max_chunks:
                logger.error(
                    f"Stream exceeded maximum chunk limit ({max_chunks}). Breaking to prevent infinite loop.",
                    extra=log_extra,
                )
                break

            # Convert chunk to dictionary for comparison
            if hasattr(chunk, "model_dump"):
                chunk_dict = chunk.model_dump()
            elif hasattr(chunk, "dict"):
                chunk_dict = chunk.dict()
            else:
                chunk_dict = chunk if isinstance(chunk, dict) else {"data": str(chunk)}

            # Detect infinite loops (same chunk repeated)
            if detect_infinite_loops:
                chunk_json = json.dumps(chunk_dict, sort_keys=True)
                if chunk_json == last_chunk_json:
                    repeated_chunk_count += 1
                    if repeated_chunk_count >= 10:
                        logger.error(
                            f"Identical chunk repeated {repeated_chunk_count} times. Breaking to prevent infinite loop.",
                            extra=log_extra,
                        )
                        break
                    elif repeated_chunk_count >= 5:
                        logger.warning(
                            f"Identical chunk repeated {repeated_chunk_count} times: {str(chunk_dict)[:100]}...",
                            extra=log_extra,
                        )
                else:
                    repeated_chunk_count = 0
                last_chunk_json = chunk_json

            # Format as SSE
            try:
                sse_data = f"data: {json.dumps(chunk_dict)}\n\n"
            except (TypeError, ValueError) as e:
                logger.error(
                    f"Failed to serialize chunk to JSON: {e}",
                    extra=log_extra,
                    exc_info=True,
                )
                # Send error as SSE event
                error_dict = {
                    "error": {
                        "message": "Failed to serialize response chunk",
                        "type": "serialization_error",
                    }
                }
                sse_data = f"data: {json.dumps(error_dict)}\n\n"

            yield sse_data

            # Check for completion
            if hasattr(chunk, "choices") and len(chunk.choices) > 0:
                finish_reason = chunk.choices[0].finish_reason
                if finish_reason:
                    logger.debug(
                        f"Stream finished: {finish_reason} ({chunk_count} chunks)",
                        extra=log_extra,
                    )
                    break

        # Send completion signal (OpenAI convention)
        logger.info(
            f"Stream completed successfully ({chunk_count} chunks)",
            extra=log_extra,
        )
        yield "data: [DONE]\n\n"

    except litellm.RateLimitError as e:
        logger.error(
            f"Rate limit during streaming (after {chunk_count} chunks): {e.message}",
            extra=log_extra,
        )
        error_dict = {
            "error": {
                "message": e.message,
                "type": "rate_limit_error",
                "code": "rate_limit_exceeded",
            }
        }
        yield f"data: {json.dumps(error_dict)}\n\n"

    except litellm.Timeout as e:
        logger.error(
            f"Timeout during streaming (after {chunk_count} chunks): {e.message}",
            extra=log_extra,
        )
        error_dict = {
            "error": {
                "message": e.message,
                "type": "timeout_error",
                "code": "stream_timeout",
            }
        }
        yield f"data: {json.dumps(error_dict)}\n\n"

    except litellm.ServiceUnavailableError as e:
        logger.error(
            f"Service unavailable during streaming (after {chunk_count} chunks): {e.message}",
            extra=log_extra,
        )
        error_dict = {
            "error": {
                "message": e.message,
                "type": "service_unavailable",
                "code": "service_unavailable",
            }
        }
        yield f"data: {json.dumps(error_dict)}\n\n"

    except Exception as e:
        logger.exception(
            f"Unexpected error during streaming (after {chunk_count} chunks): {e}",
            extra=log_extra,
        )
        error_dict = {
            "error": {
                "message": "Internal error during streaming",
                "type": "internal_error",
                "code": "streaming_error",
            }
        }
        yield f"data: {json.dumps(error_dict)}\n\n"


# =============================================================================
# Helper functions
# =============================================================================


def format_sse_event(data: Dict[str, Any], event_type: Optional[str] = None) -> str:
    """
    Format a dictionary as an SSE event.

    Args:
        data: Data to send as JSON
        event_type: Optional event type (e.g., "message", "error")

    Returns:
        SSE-formatted string

    Example:
        ```python
        event = format_sse_event({"status": "processing"}, "status")
        # Returns: "event: status\\ndata: {\\"status\\": \\"processing\\"}\\n\\n"
        ```
    """
    lines = []

    if event_type:
        lines.append(f"event: {event_type}")

    try:
        json_data = json.dumps(data)
        lines.append(f"data: {json_data}")
    except (TypeError, ValueError) as e:
        logger.error(f"Failed to serialize SSE event: {e}", exc_info=True)
        # Send error event instead
        error_data = json.dumps(
            {
                "error": {
                    "message": "Failed to serialize event data",
                    "type": "serialization_error",
                }
            }
        )
        lines.append(f"data: {error_data}")

    lines.append("")  # Empty line terminates event
    return "\n".join(lines) + "\n"


def format_error_sse(error_type: str, message: str, code: Optional[str] = None) -> str:
    """
    Format an error as an SSE event.

    Args:
        error_type: Error type (e.g., "rate_limit_error")
        message: Human-readable error message
        code: Optional error code

    Returns:
        SSE-formatted error string

    Example:
        ```python
        error_sse = format_error_sse(
            "rate_limit_error",
            "Rate limit exceeded",
            "rate_limit_exceeded"
        )
        ```
    """
    error_dict = {
        "error": {
            "type": error_type,
            "message": message,
        }
    }

    if code:
        error_dict["error"]["code"] = code

    return f"data: {json.dumps(error_dict)}\n\n"


def format_done_signal() -> str:
    """
    Format the stream completion signal.

    Returns:
        SSE-formatted completion signal

    Example:
        ```python
        done = format_done_signal()
        # Returns: "data: [DONE]\\n\\n"
        ```
    """
    return "data: [DONE]\n\n"


# =============================================================================
# Stream monitoring and debugging
# =============================================================================


class StreamMonitor:
    """
    Monitor streaming performance and detect issues.

    This class tracks streaming metrics for debugging and monitoring,
    including chunk count, timing, and error detection.

    Attributes:
        request_id: Request identifier
        chunk_count: Number of chunks processed
        error_count: Number of errors encountered
        start_time: Stream start timestamp
        last_chunk_time: Last chunk timestamp
    """

    def __init__(self, request_id: Optional[str] = None):
        """Initialize stream monitor."""
        self.request_id = request_id
        self.chunk_count = 0
        self.error_count = 0
        self.start_time: Optional[float] = None
        self.last_chunk_time: Optional[float] = None
        self.repeated_chunks = 0

    def record_chunk(self):
        """Record a chunk received."""
        import time

        self.chunk_count += 1
        current_time = time.time()

        if self.start_time is None:
            self.start_time = current_time

        if self.last_chunk_time is not None:
            time_since_last = current_time - self.last_chunk_time
            if time_since_last > 5.0:  # 5 second gap
                logger.warning(
                    f"Large gap between chunks: {time_since_last:.2f}s",
                    extra={"request_id": self.request_id} if self.request_id else {},
                )

        self.last_chunk_time = current_time

    def record_error(self):
        """Record an error encountered."""
        self.error_count += 1

    def get_stats(self) -> Dict[str, Any]:
        """
        Get streaming statistics.

        Returns:
            Dictionary with streaming stats
        """
        import time

        duration = time.time() - self.start_time if self.start_time else 0

        return {
            "request_id": self.request_id,
            "chunk_count": self.chunk_count,
            "error_count": self.error_count,
            "duration_seconds": round(duration, 2),
            "chunks_per_second": (
                round(self.chunk_count / duration, 2) if duration > 0 else 0
            ),
        }


# =============================================================================
# Testing and validation
# =============================================================================

if __name__ == "__main__":
    """
    Test streaming utilities.

    Usage:
        python -m src.proxy.streaming_utils
    """
    import asyncio

    async def mock_streaming_response():
        """Mock LiteLLM streaming response for testing."""

        class MockChoice:
            def __init__(self, content, finish_reason=None):
                self.delta = MockDelta(content)
                self.finish_reason = finish_reason

        class MockDelta:
            def __init__(self, content):
                self.content = content

        class MockChunk:
            def __init__(self, content, finish_reason=None):
                self.choices = [MockChoice(content, finish_reason)]

            def model_dump(self):
                return {
                    "choices": [
                        {
                            "delta": {"content": self.choices[0].delta.content},
                            "finish_reason": self.choices[0].finish_reason,
                        }
                    ]
                }

        # Yield some chunks
        for i in range(5):
            await asyncio.sleep(0.1)
            yield MockChunk(f"chunk {i}")

        # Final chunk with finish reason
        yield MockChunk("", finish_reason="stop")

    async def test_streaming_utils():
        """Test streaming utility functions."""
        print("\n" + "=" * 70)
        print("Testing Streaming Utilities")
        print("=" * 70 + "\n")

        # Test 1: Basic streaming
        print("Test 1: Basic Streaming")
        mock_response = mock_streaming_response()
        chunk_count = 0

        async for sse_chunk in stream_litellm_completion(
            mock_response, request_id="test-123"
        ):
            chunk_count += 1
            print(f"  Chunk {chunk_count}: {sse_chunk[:50]}...")

        print(f"  Total chunks: {chunk_count}")

        # Test 2: Error formatting
        print("\nTest 2: Error Formatting")
        error_sse = format_error_sse(
            "rate_limit_error", "Rate limit exceeded", "rate_limit_exceeded"
        )
        print(f"  Error SSE: {error_sse[:100]}...")

        # Test 3: Done signal
        print("\nTest 3: Done Signal")
        done = format_done_signal()
        print(f"  Done signal: {done}")

        # Test 4: Stream monitor
        print("\nTest 4: Stream Monitor")
        monitor = StreamMonitor("test-456")
        for i in range(10):
            monitor.record_chunk()
            await asyncio.sleep(0.05)

        stats = monitor.get_stats()
        print(f"  Stats: {stats}")

        print("\n" + "=" * 70)
        print("✅ All tests completed!")
        print("=" * 70 + "\n")

    asyncio.run(test_streaming_utils())
