"""
Integration tests for ToolCallBuffer with actual proxy components.

Tests the complete tool execution flow including:
- End-to-end tool execution with valid/invalid arguments
- Multiple tool calls with mixed states
- Error recovery and graceful degradation
- Backward compatibility
"""

import json
import pytest
from unittest.mock import Mock, AsyncMock, patch
from typing import Dict, Any

# Import from actual implementation
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from proxy.litellm_proxy_sdk import ToolCallBuffer, handle_non_streaming_completion
from proxy.error_handlers import LiteLLMErrorHandler


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def mock_tool_executor():
    """Mock ToolExecutor for testing."""
    executor = Mock()
    executor.execute_tool_call = AsyncMock(return_value={
        "results": ["result1", "result2"],
        "error": None
    })
    executor.format_tool_result_for_llm = Mock(
        return_value="Tool executed successfully with 2 results"
    )
    return executor


@pytest.fixture
def mock_litellm_response_with_tool_calls():
    """Mock LiteLLM response with tool calls."""
    mock_response = Mock()
    mock_response.choices = [Mock()]
    mock_response.choices[0].message = Mock()
    mock_response.choices[0].message.content = ""

    # Create tool call objects
    tool_call_1 = Mock()
    tool_call_1.id = "call_abc123"
    tool_call_1.type = "function"
    tool_call_1.function = Mock()
    tool_call_1.function.name = "search"
    tool_call_1.function.arguments = '{"query": "python async", "limit": 10}'

    tool_call_2 = Mock()
    tool_call_2.id = "call_def456"
    tool_call_2.type = "function"
    tool_call_2.function = Mock()
    tool_call_2.function.name = "calculate"
    tool_call_2.function.arguments = {"x": 5, "y": 10, "operation": "add"}

    mock_response.choices[0].message.tool_calls = [tool_call_1, tool_call_2]
    mock_response.model_dump = Mock(return_value={
        "id": "chatcmpl-test",
        "choices": [{"message": {"tool_calls": []}}]
    })

    return mock_response


@pytest.fixture
def mock_litellm_response_truncated():
    """Mock LiteLLM response with truncated tool call JSON."""
    mock_response = Mock()
    mock_response.choices = [Mock()]
    mock_response.choices[0].message = Mock()
    mock_response.choices[0].message.content = ""

    # Tool call with truncated JSON
    tool_call = Mock()
    tool_call.id = "call_truncated"
    tool_call.type = "function"
    tool_call.function = Mock()
    tool_call.function.name = "search"
    tool_call.function.arguments = '{"query": "test", "limit": '  # Truncated

    mock_response.choices[0].message.tool_calls = [tool_call]
    mock_response.model_dump = Mock(return_value={
        "id": "chatcmpl-test",
        "choices": [{"message": {"tool_calls": []}}]
    })

    return mock_response


@pytest.fixture
def mock_litellm_response_mixed():
    """Mock LiteLLM response with mix of complete and incomplete tool calls."""
    mock_response = Mock()
    mock_response.choices = [Mock()]
    mock_response.choices[0].message = Mock()
    mock_response.choices[0].message.content = ""

    # Complete tool call 1
    tool_call_1 = Mock()
    tool_call_1.id = "call_complete_1"
    tool_call_1.type = "function"
    tool_call_1.function = Mock()
    tool_call_1.function.name = "search"
    tool_call_1.function.arguments = '{"query": "python"}'

    # Complete tool call 2
    tool_call_2 = Mock()
    tool_call_2.id = "call_complete_2"
    tool_call_2.type = "function"
    tool_call_2.function = Mock()
    tool_call_2.function.name = "calculate"
    tool_call_2.function.arguments = {"x": 5}

    # Incomplete tool call (truncated JSON)
    tool_call_3 = Mock()
    tool_call_3.id = "call_incomplete"
    tool_call_3.type = "function"
    tool_call_3.function = Mock()
    tool_call_3.function.name = "bad_tool"
    tool_call_3.function.arguments = '{"incomplete": '

    mock_response.choices[0].message.tool_calls = [tool_call_1, tool_call_2, tool_call_3]
    mock_response.model_dump = Mock(return_value={
        "id": "chatcmpl-test",
        "choices": [{"message": {"tool_calls": []}}]
    })

    return mock_response


# =============================================================================
# Unit Tests for ToolCallBuffer Integration
# =============================================================================


class TestToolCallBufferIntegration:
    """Integration tests for ToolCallBuffer with actual proxy components."""

    def test_buffer_with_mock_llm_response(self, mock_litellm_response_with_tool_calls):
        """Test buffer handles mock LLM response correctly."""
        buffer = ToolCallBuffer()

        # Extract and buffer tool calls from mock response
        tool_calls = mock_litellm_response_with_tool_calls.choices[0].message.tool_calls

        for tc in tool_calls:
            buffer.add_tool_call(
                tool_call_id=tc.id,
                tool_name=tc.function.name,
                arguments=tc.function.arguments,
                tool_type=tc.type
            )

        # Verify all tool calls buffered
        assert len(buffer) == 2
        assert "call_abc123" in buffer
        assert "call_def456" in buffer

        # Verify both are complete
        assert buffer.is_complete("call_abc123")
        assert buffer.is_complete("call_def456")

        # Verify parsing works
        args_1 = buffer.parse_arguments("call_abc123")
        assert args_1 == {"query": "python async", "limit": 10}

        args_2 = buffer.parse_arguments("call_def456")
        assert args_2 == {"x": 5, "y": 10, "operation": "add"}

    def test_buffer_with_truncated_response(self, mock_litellm_response_truncated):
        """Test buffer detects truncated JSON in LLM response."""
        buffer = ToolCallBuffer()

        # Extract and buffer tool call
        tool_call = mock_litellm_response_truncated.choices[0].message.tool_calls[0]
        buffer.add_tool_call(
            tool_call_id=tool_call.id,
            tool_name=tool_call.function.name,
            arguments=tool_call.function.arguments,
            tool_type=tool_call.type
        )

        # Verify buffered
        assert len(buffer) == 1
        assert "call_truncated" in buffer

        # Verify detected as incomplete
        assert not buffer.is_complete("call_truncated")

        # Verify in incomplete list
        incomplete = buffer.get_incomplete_tool_calls()
        assert "call_truncated" in incomplete

        # Verify not in complete list
        complete = buffer.get_all_complete_tool_calls()
        assert "call_truncated" not in complete

    def test_buffer_with_mixed_states(self, mock_litellm_response_mixed):
        """Test buffer handles mix of complete and incomplete tool calls."""
        buffer = ToolCallBuffer()

        # Buffer all tool calls
        tool_calls = mock_litellm_response_mixed.choices[0].message.tool_calls
        for tc in tool_calls:
            buffer.add_tool_call(
                tool_call_id=tc.id,
                tool_name=tc.function.name,
                arguments=tc.function.arguments,
                tool_type=tc.type
            )

        # Verify all buffered
        assert len(buffer) == 3

        # Verify complete calls
        complete = buffer.get_all_complete_tool_calls()
        assert len(complete) == 2
        assert "call_complete_1" in complete
        assert "call_complete_2" in complete

        # Verify incomplete calls
        incomplete = buffer.get_incomplete_tool_calls()
        assert len(incomplete) == 1
        assert "call_incomplete" in incomplete

        # Verify parsing works for complete calls
        args_1 = buffer.parse_arguments("call_complete_1")
        assert args_1 == {"query": "python"}

        args_2 = buffer.parse_arguments("call_complete_2")
        assert args_2 == {"x": 5}

        # Verify parsing fails for incomplete call
        with pytest.raises(ValueError) as exc_info:
            buffer.parse_arguments("call_incomplete")
        assert "call_incomplete" in str(exc_info.value)
        assert "bad_tool" in str(exc_info.value)


# =============================================================================
# Integration Tests with handle_non_streaming_completion
# =============================================================================


class TestHandleNonStreamingWithBuffer:
    """Integration tests for handle_non_streaming_completion with ToolCallBuffer."""

    @pytest.mark.asyncio
    async def test_completion_with_no_tool_calls(self):
        """Test completion without tool calls returns immediately."""
        # Mock LiteLLM response without tool calls
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message = Mock()
        mock_response.choices[0].message.content = "Hello! How can I help?"
        mock_response.choices[0].message.tool_calls = None
        mock_response.model_dump = Mock(return_value={
            "id": "chatcmpl-test",
            "choices": [{"message": {"content": "Hello! How can I help?"}}]
        })

        # Mock error handler
        error_handler = Mock(spec=LiteLLMErrorHandler)

        # Mock litellm.acompletion
        with patch('proxy.litellm_proxy_sdk.litellm.acompletion', new_callable=AsyncMock) as mock_acompletion:
            mock_acompletion.return_value = mock_response

            # Mock get_tool_executor to return None
            with patch('proxy.litellm_proxy_sdk.get_tool_executor', return_value=None):
                with patch('proxy.litellm_proxy_sdk.get_tool_exec_config', return_value=None):
                    # Call handler
                    response = await handle_non_streaming_completion(
                        messages=[{"role": "user", "content": "Hello"}],
                        litellm_params={"model": "test-model"},
                        request_id="test_req_1",
                        error_handler=error_handler,
                        user_id="test_user"
                    )

        # Verify response returned immediately
        assert response.status_code == 200
        assert mock_acompletion.call_count == 1  # Only one call

    @pytest.mark.asyncio
    async def test_completion_with_tool_calls_no_executor(self, mock_litellm_response_with_tool_calls):
        """Test completion with tool calls but no executor returns response as-is."""
        # Mock error handler
        error_handler = Mock(spec=LiteLLMErrorHandler)

        # Mock litellm.acompletion
        with patch('proxy.litellm_proxy_sdk.litellm.acompletion', new_callable=AsyncMock) as mock_acompletion:
            mock_acompletion.return_value = mock_litellm_response_with_tool_calls

            # Mock get_tool_executor to return None
            with patch('proxy.litellm_proxy_sdk.get_tool_executor', return_value=None):
                with patch('proxy.litellm_proxy_sdk.get_tool_exec_config', return_value=None):
                    # Call handler
                    response = await handle_non_streaming_completion(
                        messages=[{"role": "user", "content": "Search for python"}],
                        litellm_params={"model": "test-model"},
                        request_id="test_req_2",
                        error_handler=error_handler,
                        user_id="test_user"
                    )

        # Verify response returned with tool_calls (not executed)
        assert response.status_code == 200
        assert mock_acompletion.call_count == 1  # Only one call (no execution loop)


# =============================================================================
# Error Recovery Tests
# =============================================================================


class TestErrorRecovery:
    """Test error recovery and graceful degradation."""

    def test_parse_error_raises_with_context(self):
        """Test parse errors include tool name and call ID in message."""
        buffer = ToolCallBuffer()
        buffer.add_tool_call(
            tool_call_id="call_error_test",
            tool_name="search_tool",
            arguments='{"invalid": json syntax}'
        )

        with pytest.raises(ValueError) as exc_info:
            buffer.parse_arguments("call_error_test")

        error_msg = str(exc_info.value)
        assert "call_error_test" in error_msg
        assert "search_tool" in error_msg
        assert "Failed to parse arguments JSON" in error_msg

    def test_missing_tool_call_id_raises(self):
        """Test parsing non-existent tool call ID raises KeyError."""
        buffer = ToolCallBuffer()

        with pytest.raises(KeyError) as exc_info:
            buffer.parse_arguments("nonexistent_call")

        assert "nonexistent_call" in str(exc_info.value)

    def test_buffer_clears_successfully(self):
        """Test buffer can be cleared and reused."""
        buffer = ToolCallBuffer()

        # Add some tool calls
        buffer.add_tool_call("call_1", "tool_1", '{"arg": "value1"}')
        buffer.add_tool_call("call_2", "tool_2", '{"arg": "value2"}')
        assert len(buffer) == 2

        # Clear buffer
        buffer.clear()
        assert len(buffer) == 0
        assert buffer.get_all_complete_tool_calls() == {}

        # Reuse buffer
        buffer.add_tool_call("call_3", "tool_3", '{"arg": "value3"}')
        assert len(buffer) == 1
        assert buffer.is_complete("call_3")


# =============================================================================
# Backward Compatibility Tests
# =============================================================================


class TestBackwardCompatibility:
    """Test backward compatibility with existing systems."""

    def test_message_format_preservation(self, mock_litellm_response_with_tool_calls):
        """Test that tool_calls in messages use original format."""
        buffer = ToolCallBuffer()

        # Buffer tool calls
        tool_calls = mock_litellm_response_with_tool_calls.choices[0].message.tool_calls
        for tc in tool_calls:
            buffer.add_tool_call(
                tool_call_id=tc.id,
                tool_name=tc.function.name,
                arguments=tc.function.arguments,
                tool_type=tc.type
            )

        # Verify original arguments format is preserved in buffer
        tool_data_1 = buffer.get_tool_call("call_abc123")
        assert tool_data_1["arguments"] == '{"query": "python async", "limit": 10}'  # Original string

        tool_data_2 = buffer.get_tool_call("call_def456")
        assert tool_data_2["arguments"] == {"x": 5, "y": 10, "operation": "add"}  # Original dict

    def test_empty_arguments_behavior(self):
        """Test empty arguments are handled consistently."""
        buffer = ToolCallBuffer()

        # Test with None
        buffer.add_tool_call("call_none", "tool", arguments=None)
        assert buffer.parse_arguments("call_none") == {}

        # Test with empty string
        buffer.add_tool_call("call_empty", "tool", arguments="")
        assert buffer.parse_arguments("call_empty") == {}

        # Test with whitespace
        buffer.add_tool_call("call_ws", "tool", arguments="   \n\t  ")
        assert buffer.parse_arguments("call_ws") == {}


# =============================================================================
# Performance and Stress Tests
# =============================================================================


class TestPerformance:
    """Performance and stress tests for ToolCallBuffer."""

    def test_many_tool_calls(self):
        """Test buffer handles 100+ tool calls efficiently."""
        buffer = ToolCallBuffer()

        # Add 100 tool calls
        for i in range(100):
            buffer.add_tool_call(
                tool_call_id=f"call_{i}",
                tool_name=f"tool_{i}",
                arguments=f'{{"param": "value_{i}"}}'
            )

        # Verify all buffered
        assert len(buffer) == 100

        # Verify all complete
        complete = buffer.get_all_complete_tool_calls()
        assert len(complete) == 100

        # Verify parsing works for all
        for i in range(100):
            args = buffer.parse_arguments(f"call_{i}")
            assert args == {"param": f"value_{i}"}

    def test_large_arguments(self):
        """Test buffer with very large JSON arguments."""
        buffer = ToolCallBuffer()

        # Create 1MB JSON string
        large_data = "x" * 1_000_000
        large_json = json.dumps({"data": large_data})

        buffer.add_tool_call("call_large", "tool", arguments=large_json)

        # Verify complete
        assert buffer.is_complete("call_large")

        # Verify parsing works
        parsed = buffer.parse_arguments("call_large")
        assert len(parsed["data"]) == 1_000_000

    def test_deeply_nested_json(self):
        """Test buffer with deeply nested JSON structures."""
        buffer = ToolCallBuffer()

        # Create 50-level nested structure
        nested = {"level": 0}
        current = nested
        for i in range(50):
            current["child"] = {"level": i + 1}
            current = current["child"]

        buffer.add_tool_call("call_nested", "tool", arguments=json.dumps(nested))

        # Verify complete and parsing works
        assert buffer.is_complete("call_nested")
        parsed = buffer.parse_arguments("call_nested")
        assert parsed["level"] == 0

        # Navigate to deepest level
        current = parsed
        for i in range(50):
            current = current["child"]
            assert current["level"] == i + 1


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
