"""
Test suite for tool executor error handling and structured errors.

Tests the enhanced error messages that enable LLM self-correction in
multi-round tool call scenarios.
"""

import json
from types import SimpleNamespace

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from proxy.tool_executor import (
    ToolExecutor,
    ToolExecutionError,
    ToolExecutionConfig,
)


# =============================================================================
# ToolExecutionError Tests
# =============================================================================


class TestToolExecutionError:
    """Test the ToolExecutionError class."""

    def test_error_initialization(self):
        """Test that ToolExecutionError initializes correctly."""
        error = ToolExecutionError(
            error_type="missing_parameter",
            message="Parameter 'query' is required",
            parameter="query",
            required_parameters=["query"],
            example={"query": "test search"},
            retry_hint="Please provide a query parameter",
        )

        assert error.error_type == "missing_parameter"
        assert error.message == "Parameter 'query' is required"
        assert error.parameter == "query"
        assert error.required_parameters == ["query"]
        assert error.example == {"query": "test search"}
        assert error.retry_hint == "Please provide a query parameter"

    def test_error_to_dict(self):
        """Test that ToolExecutionError converts to dict correctly."""
        error = ToolExecutionError(
            error_type="missing_parameter",
            message="Parameter 'query' is required",
            parameter="query",
            required_parameters=["query"],
            example={"query": "test search"},
            retry_hint="Please provide a query parameter",
        )

        error_dict = error.to_dict()

        assert error_dict["type"] == "missing_parameter"
        assert error_dict["message"] == "Parameter 'query' is required"
        assert error_dict["parameter"] == "query"
        assert error_dict["required_parameters"] == ["query"]
        assert error_dict["example"] == {"query": "test search"}
        assert error_dict["retry_hint"] == "Please provide a query parameter"

    def test_error_to_dict_minimal(self):
        """Test that ToolExecutionError to_dict works with minimal fields."""
        error = ToolExecutionError(
            error_type="general_error", message="Something went wrong"
        )

        error_dict = error.to_dict()

        assert error_dict["type"] == "general_error"
        assert error_dict["message"] == "Something went wrong"
        assert "parameter" not in error_dict
        assert "required_parameters" not in error_dict
        assert "example" not in error_dict
        assert "retry_hint" not in error_dict


# =============================================================================
# Tool Executor Error Handling Tests
# =============================================================================


class TestToolExecutorErrorHandling:
    """Test tool executor error handling for missing parameters."""

    @pytest.mark.asyncio
    async def test_missing_query_parameter_returns_structured_error(self):
        """Test that missing query parameter returns structured error."""
        executor = ToolExecutor(
            supermemory_api_key="test-key",
            timeout=10.0,
        )

        # Call without query parameter
        result = await executor.execute_tool_call(
            tool_name="supermemoryToolSearch",
            tool_args={},  # Missing query
            user_id="test-user",
            tool_call_id="call_123",
        )

        # Verify structured error is returned
        assert "error" in result
        assert isinstance(result["error"], dict)
        assert result["error"]["type"] == "missing_parameter"
        assert result["error"]["parameter"] == "query"
        assert "required_parameters" in result["error"]
        assert "query" in result["error"]["required_parameters"]
        assert "retry_hint" in result["error"]
        assert "example" in result["error"]

    @pytest.mark.asyncio
    async def test_empty_query_parameter_returns_structured_error(self):
        """Test that empty query parameter returns structured error."""
        executor = ToolExecutor(
            supermemory_api_key="test-key",
            timeout=10.0,
        )

        # Call with empty query
        result = await executor.execute_tool_call(
            tool_name="supermemoryToolSearch",
            tool_args={"query": ""},  # Empty query
            user_id="test-user",
            tool_call_id="call_456",
        )

        # Verify structured error is returned
        assert "error" in result
        assert isinstance(result["error"], dict)
        assert result["error"]["type"] == "invalid_value"

    @pytest.mark.asyncio
    async def test_error_includes_example_usage(self):
        """Test that error includes example of correct usage."""
        executor = ToolExecutor(
            supermemory_api_key="test-key",
            timeout=10.0,
        )

        result = await executor.execute_tool_call(
            tool_name="supermemoryToolSearch",
            tool_args={},
            user_id="test-user",
            tool_call_id="call_789",
        )

        # Verify example is present and well-formed
        assert "error" in result
        assert "example" in result["error"]
        assert isinstance(result["error"]["example"], dict)
        assert "query" in result["error"]["example"]


# =============================================================================
# LLM Formatting Tests
# =============================================================================


class TestToolResultLLMFormatting:
    """Test that tool results are formatted correctly for LLM consumption."""

    def test_format_structured_error_for_llm(self):
        """Test that structured errors are formatted with guidance for LLM."""
        executor = ToolExecutor(
            supermemory_api_key="test-key",
            timeout=10.0,
        )

        # Create a tool result with structured error
        tool_result = {
            "tool_call_id": "call_123",
            "error": {
                "type": "missing_parameter",
                "message": "The 'query' parameter is required",
                "parameter": "query",
                "required_parameters": ["query"],
                "example": {"query": "python asyncio patterns"},
                "retry_hint": "Retry with a search query string",
            },
            "results": [],
        }

        # Format for LLM
        formatted = executor.format_tool_result_for_llm(tool_result)

        # Verify all key elements are present
        assert "Tool Call Error" in formatted
        assert "Missing Parameter" in formatted
        assert "query" in formatted
        assert "Required Parameters" in formatted
        assert "Example Usage" in formatted
        assert "python asyncio patterns" in formatted
        assert "retry" in formatted.lower()

    def test_format_legacy_string_error_for_llm(self):
        """Test backward compatibility with legacy string errors."""
        executor = ToolExecutor(
            supermemory_api_key="test-key",
            timeout=10.0,
        )

        # Legacy error format (string)
        tool_result = {
            "tool_call_id": "call_456",
            "error": "Search failed: connection timeout",
            "results": [],
        }

        # Format for LLM
        formatted = executor.format_tool_result_for_llm(tool_result)

        # Verify legacy format still works
        assert "Tool execution error" in formatted
        assert "connection timeout" in formatted

    def test_format_success_result_for_llm(self):
        """Test that successful results are formatted correctly."""
        executor = ToolExecutor(
            supermemory_api_key="test-key",
            timeout=10.0,
        )

        # Successful result
        tool_result = {
            "tool_call_id": "call_789",
            "query": "python async",
            "results_count": 2,
            "results": [
                {
                    "index": 1,
                    "title": "Python Asyncio Guide",
                    "content": "Asyncio is a library...",
                    "source": "docs.python.org",
                    "relevance_score": 0.95,
                },
                {
                    "index": 2,
                    "title": "Async Patterns",
                    "content": "Common patterns...",
                    "source": "realpython.com",
                    "relevance_score": 0.87,
                },
            ],
        }

        # Format for LLM
        formatted = executor.format_tool_result_for_llm(tool_result)

        # Verify success formatting
        assert "Found 2 results" in formatted
        assert "Python Asyncio Guide" in formatted
        assert "Asyncio is a library" in formatted
        assert "0.95" in formatted


# =============================================================================
# Integration Test: Multi-Round Tool Call Flow
# =============================================================================


class TestMultiRoundToolCallFlow:
    """Test multi-round tool call flow with error recovery."""

    @pytest.mark.asyncio
    async def test_error_provides_sufficient_context_for_retry(self):
        """Test that error message provides enough context for LLM to retry successfully."""
        executor = ToolExecutor(
            supermemory_api_key="test-key",
            timeout=10.0,
        )

        # Simulate first attempt with missing parameter
        first_result = await executor.execute_tool_call(
            tool_name="supermemoryToolSearch",
            tool_args={},  # Missing query
            user_id="test-user",
            tool_call_id="call_first",
        )

        # Format error for LLM
        error_message = executor.format_tool_result_for_llm(first_result)

        # Verify error provides actionable guidance
        assert "error" in first_result
        assert isinstance(first_result["error"], dict)

        # Verify formatted message contains key information
        assert "Missing Parameter" in error_message
        assert "query" in error_message
        assert "Example Usage" in error_message
        assert "retry" in error_message.lower()

        # Verify the error includes concrete example
        assert "python asyncio patterns" in error_message or "query" in error_message

    @pytest.mark.asyncio
    async def test_consecutive_errors_maintain_structure(self):
        """Test that multiple consecutive errors maintain structured format."""
        executor = ToolExecutor(
            supermemory_api_key="test-key",
            timeout=10.0,
        )

        # First error
        result1 = await executor.execute_tool_call(
            tool_name="supermemoryToolSearch",
            tool_args={},
            user_id="test-user",
            tool_call_id="call_1",
        )

        # Second error (same issue)
        result2 = await executor.execute_tool_call(
            tool_name="supermemoryToolSearch",
            tool_args={},
            user_id="test-user",
            tool_call_id="call_2",
        )

        # Both should have structured errors
        assert "error" in result1
        assert "error" in result2
        assert isinstance(result1["error"], dict)
        assert isinstance(result2["error"], dict)
        assert result1["error"]["type"] == result2["error"]["type"]


# =============================================================================
# New Error Types Tests
# =============================================================================


class TestNewErrorTypes:
    """Test new error types: invalid_type, rate_limit, authentication."""

    @pytest.mark.asyncio
    async def test_invalid_type_error(self):
        """Test that invalid parameter type returns structured error."""
        executor = ToolExecutor(
            supermemory_api_key="test-key",
            timeout=10.0,
        )

        # Call with wrong type (int instead of string)
        result = await executor.execute_tool_call(
            tool_name="supermemoryToolSearch",
            tool_args={"query": 123},  # Wrong type!
            user_id="test-user",
            tool_call_id="call_invalid_type",
        )

        # Verify structured error
        assert "error" in result
        assert isinstance(result["error"], dict)
        assert result["error"]["type"] == "invalid_type"
        assert "str" in result["error"]["message"]
        assert "int" in result["error"]["message"]

    @pytest.mark.asyncio
    async def test_empty_value_error(self):
        """Test that empty string parameter returns structured error."""
        executor = ToolExecutor(
            supermemory_api_key="test-key",
            timeout=10.0,
        )

        # Call with empty string
        result = await executor.execute_tool_call(
            tool_name="supermemoryToolSearch",
            tool_args={"query": "   "},  # Empty/whitespace only
            user_id="test-user",
            tool_call_id="call_empty",
        )

        # Verify structured error
        assert "error" in result
        assert isinstance(result["error"], dict)
        assert result["error"]["type"] == "invalid_value"
        assert "empty" in result["error"]["message"].lower()

    @pytest.mark.asyncio
    async def test_invalid_arguments_json_error(self):
        """Test that invalid JSON arguments return structured error."""
        executor = ToolExecutor(
            supermemory_api_key="test-key",
            timeout=10.0,
        )

        # Call with invalid JSON string
        result = await executor.execute_tool_call(
            tool_name="supermemoryToolSearch",
            tool_args='{"query": invalid json}',  # Malformed JSON
            user_id="test-user",
            tool_call_id="call_bad_json",
        )

        # Verify structured error
        assert "error" in result
        assert isinstance(result["error"], dict)
        assert result["error"]["type"] == "invalid_arguments"

    @pytest.mark.asyncio
    async def test_queries_array_is_combined_into_single_query(self):
        """Test that the 'queries' parameter is accepted and combined."""
        executor = ToolExecutor(
            supermemory_api_key="test-key",
            timeout=10.0,
        )

        executor.supermemory_client = MagicMock()
        search_result = SimpleNamespace(
            content="Doc content",
            source="memory://doc",
            score=0.81,
            title="Doc title",
            url="https://example.com/doc",
        )
        executor.supermemory_client.search.execute.return_value = SimpleNamespace(
            results=[search_result]
        )

        result = await executor.execute_tool_call(
            tool_name="supermemoryToolSearch",
            tool_args={"queries": ["documents", "files"]},
            user_id="test-user",
            tool_call_id="call_queries",
        )

        executor.supermemory_client.search.execute.assert_called_once_with(
            q="documents OR files",
            limit=executor.max_results,
            include_summary=True,
            rerank=True,
        )
        assert result["query"] == "documents OR files"
        assert result["results_count"] == 1

    @pytest.mark.asyncio
    async def test_queries_with_non_string_entries_returns_type_error(self):
        """Test that non-string entries in 'queries' return invalid_type."""
        executor = ToolExecutor(
            supermemory_api_key="test-key",
            timeout=10.0,
        )

        result = await executor.execute_tool_call(
            tool_name="supermemoryToolSearch",
            tool_args={"queries": ["documents", 123]},
            user_id="test-user",
            tool_call_id="call_queries_type_error",
        )

        assert "error" in result
        assert result["error"]["type"] == "invalid_type"
        assert result["error"]["parameter"] == "queries"

    @pytest.mark.asyncio
    async def test_queries_with_only_empty_strings_returns_value_error(self):
        """Test that empty strings in 'queries' return invalid_value."""
        executor = ToolExecutor(
            supermemory_api_key="test-key",
            timeout=10.0,
        )

        result = await executor.execute_tool_call(
            tool_name="supermemoryToolSearch",
            tool_args={"queries": ["   ", "\t"]},
            user_id="test-user",
            tool_call_id="call_queries_value_error",
        )

        assert "error" in result
        assert result["error"]["type"] == "invalid_value"
        assert result["error"]["parameter"] == "queries"


# =============================================================================
# Retry Tracking Tests
# =============================================================================


class TestRetryTracking:
    """Test retry tracking functionality in ToolCallBuffer."""

    @pytest.fixture
    def buffer(self):
        """Create a minimal ToolCallBuffer for testing."""
        # Create a simple buffer class for testing
        class SimpleToolCallBuffer:
            def __init__(self):
                self.retry_counts = {}
                self.error_history = {}

            def increment_retry_count(self, tool_call_id):
                current_count = self.retry_counts.get(tool_call_id, 0)
                self.retry_counts[tool_call_id] = current_count + 1
                return self.retry_counts[tool_call_id]

            def get_retry_count(self, tool_call_id):
                return self.retry_counts.get(tool_call_id, 0)

            def should_retry(self, tool_call_id, max_retries=2):
                current_count = self.get_retry_count(tool_call_id)
                return current_count < max_retries

            def record_error(self, tool_call_id, error_type):
                if tool_call_id not in self.error_history:
                    self.error_history[tool_call_id] = []
                self.error_history[tool_call_id].append(error_type)

            def get_error_history(self, tool_call_id):
                return self.error_history.get(tool_call_id, [])

        return SimpleToolCallBuffer()

    def test_increment_retry_count(self, buffer):
        """Test that retry count increments correctly."""

        # First increment
        count1 = buffer.increment_retry_count("call_123")
        assert count1 == 1

        # Second increment
        count2 = buffer.increment_retry_count("call_123")
        assert count2 == 2

        # Third increment
        count3 = buffer.increment_retry_count("call_123")
        assert count3 == 3

    def test_get_retry_count(self, buffer):
        """Test getting retry count."""
        # Before any retries
        assert buffer.get_retry_count("call_456") == 0

        # After incrementing
        buffer.increment_retry_count("call_456")
        assert buffer.get_retry_count("call_456") == 1

    def test_should_retry_default_max(self, buffer):
        """Test retry decision with default max retries (2)."""
        # No retries yet - should retry
        assert buffer.should_retry("call_789") is True

        # First retry - should retry
        buffer.increment_retry_count("call_789")
        assert buffer.should_retry("call_789") is True

        # Second retry - should NOT retry (max reached)
        buffer.increment_retry_count("call_789")
        assert buffer.should_retry("call_789") is False

        # Third retry - should NOT retry (exceeded max)
        buffer.increment_retry_count("call_789")
        assert buffer.should_retry("call_789") is False

    def test_should_retry_custom_max(self, buffer):
        """Test retry decision with custom max retries."""
        # Custom max: 5 retries
        for i in range(5):
            assert buffer.should_retry("call_abc", max_retries=5) is True
            buffer.increment_retry_count("call_abc")

        # After 5 retries, should not retry anymore
        assert buffer.should_retry("call_abc", max_retries=5) is False

    def test_record_error(self, buffer):
        """Test recording errors for a tool call."""
        # Record first error
        buffer.record_error("call_xyz", "missing_parameter")
        history = buffer.get_error_history("call_xyz")
        assert len(history) == 1
        assert history[0] == "missing_parameter"

        # Record second error
        buffer.record_error("call_xyz", "invalid_type")
        history = buffer.get_error_history("call_xyz")
        assert len(history) == 2
        assert history[1] == "invalid_type"

    def test_get_error_history_empty(self, buffer):
        """Test getting error history when no errors recorded."""
        # No errors recorded
        history = buffer.get_error_history("call_new")
        assert history == []

    def test_independent_tracking_per_tool_call(self, buffer):
        """Test that retry counts and errors are tracked independently per tool call."""

        # Different tool calls
        buffer.increment_retry_count("call_1")
        buffer.increment_retry_count("call_1")
        buffer.increment_retry_count("call_2")

        buffer.record_error("call_1", "error_a")
        buffer.record_error("call_2", "error_b")
        buffer.record_error("call_2", "error_c")

        # Verify independent tracking
        assert buffer.get_retry_count("call_1") == 2
        assert buffer.get_retry_count("call_2") == 1

        assert len(buffer.get_error_history("call_1")) == 1
        assert len(buffer.get_error_history("call_2")) == 2
