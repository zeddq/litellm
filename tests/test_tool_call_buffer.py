"""
Unit tests for ToolCallBuffer class.

Tests defensive handling of tool call arguments:
- Empty/None arguments
- Already-parsed dict arguments
- Valid JSON string arguments
- Truncated/invalid JSON
- Argument validation and completeness checks

Note: This test file includes a copy of ToolCallBuffer to avoid
complex import dependencies during testing.
"""
import json
import pytest


# ============================================================================
# ToolCallBuffer Copy for Testing
# ============================================================================


class ToolCallBuffer:
    """
    Buffer for managing tool call state during streaming/non-streaming responses.

    Test copy to avoid import issues.
    """

    def __init__(self):
        """Initialize empty tool call buffer."""
        self.buffer = {}

    def add_tool_call(
        self,
        tool_call_id: str,
        tool_name: str,
        arguments,
        tool_type: str = "function"
    ) -> None:
        """Add or update a tool call in the buffer."""
        self.buffer[tool_call_id] = {
            "id": tool_call_id,
            "name": tool_name,
            "arguments": arguments,
            "type": tool_type,
            "complete": self._is_arguments_complete(arguments)
        }

    def _is_arguments_complete(self, arguments) -> bool:
        """Check if arguments appear complete and parseable."""
        if arguments is None or arguments == "":
            return True

        if isinstance(arguments, dict):
            return True

        if isinstance(arguments, str):
            arguments_stripped = arguments.strip()
            if not arguments_stripped:
                return True

            try:
                json.loads(arguments_stripped)
                return True
            except json.JSONDecodeError:
                return False

        return True

    def is_complete(self, tool_call_id: str) -> bool:
        """Check if a tool call is complete and ready for execution."""
        if tool_call_id not in self.buffer:
            return False
        return self.buffer[tool_call_id]["complete"]

    def get_tool_call(self, tool_call_id: str):
        """Retrieve tool call data by ID."""
        return self.buffer.get(tool_call_id)

    def parse_arguments(self, tool_call_id: str):
        """Parse and return arguments for a tool call."""
        if tool_call_id not in self.buffer:
            raise KeyError(f"Tool call ID {tool_call_id} not found in buffer")

        tool_data = self.buffer[tool_call_id]
        arguments = tool_data["arguments"]
        tool_name = tool_data["name"]

        if arguments is None or arguments == "":
            return {}

        if isinstance(arguments, dict):
            return arguments

        if isinstance(arguments, str):
            arguments_stripped = arguments.strip()

            if not arguments_stripped:
                return {}

            try:
                parsed = json.loads(arguments_stripped)
                return parsed if isinstance(parsed, dict) else {}

            except json.JSONDecodeError as e:
                error_msg = (
                    f"Tool {tool_name} ({tool_call_id}): Failed to parse arguments JSON: {e}\n"
                    f"Arguments (first 200 chars): {arguments_stripped[:200]}"
                )
                raise ValueError(error_msg) from e

        error_msg = (
            f"Tool {tool_name} ({tool_call_id}): "
            f"Unexpected argument type {type(arguments)}: {arguments}"
        )
        raise ValueError(error_msg)

    def get_all_complete_tool_calls(self):
        """Get all complete tool calls ready for execution."""
        return {
            call_id: call_data
            for call_id, call_data in self.buffer.items()
            if call_data["complete"]
        }

    def get_incomplete_tool_calls(self):
        """Get all incomplete tool calls (for debugging/logging)."""
        return {
            call_id: call_data
            for call_id, call_data in self.buffer.items()
            if not call_data["complete"]
        }

    def clear(self) -> None:
        """Clear all buffered tool calls."""
        self.buffer.clear()

    def __len__(self) -> int:
        """Return number of tool calls in buffer."""
        return len(self.buffer)

    def __contains__(self, tool_call_id: str) -> bool:
        """Check if tool_call_id exists in buffer."""
        return tool_call_id in self.buffer


# ============================================================================
# Test Suite
# ============================================================================


class TestToolCallBuffer:
    """Test suite for ToolCallBuffer class."""

    def test_empty_buffer(self):
        """Test newly created buffer is empty."""
        buffer = ToolCallBuffer()
        assert len(buffer) == 0
        assert buffer.get_all_complete_tool_calls() == {}
        assert buffer.get_incomplete_tool_calls() == {}

    def test_add_tool_call_with_valid_json(self):
        """Test adding tool call with valid JSON string arguments."""
        buffer = ToolCallBuffer()

        buffer.add_tool_call(
            tool_call_id="call_123",
            tool_name="search",
            arguments='{"query": "python async", "limit": 10}',
            tool_type="function"
        )

        assert len(buffer) == 1
        assert "call_123" in buffer
        assert buffer.is_complete("call_123")

        tool_data = buffer.get_tool_call("call_123")
        assert tool_data["name"] == "search"
        assert tool_data["type"] == "function"
        assert tool_data["complete"] is True

    def test_add_tool_call_with_dict_arguments(self):
        """Test adding tool call with already-parsed dict arguments."""
        buffer = ToolCallBuffer()

        buffer.add_tool_call(
            tool_call_id="call_456",
            tool_name="calculate",
            arguments={"x": 5, "y": 10, "operation": "add"},
            tool_type="function"
        )

        assert len(buffer) == 1
        assert buffer.is_complete("call_456")

        parsed_args = buffer.parse_arguments("call_456")
        assert parsed_args == {"x": 5, "y": 10, "operation": "add"}

    def test_add_tool_call_with_none_arguments(self):
        """Test adding tool call with None arguments (no args needed)."""
        buffer = ToolCallBuffer()

        buffer.add_tool_call(
            tool_call_id="call_789",
            tool_name="get_time",
            arguments=None,
            tool_type="function"
        )

        assert len(buffer) == 1
        assert buffer.is_complete("call_789")

        parsed_args = buffer.parse_arguments("call_789")
        assert parsed_args == {}

    def test_add_tool_call_with_empty_string(self):
        """Test adding tool call with empty string arguments."""
        buffer = ToolCallBuffer()

        buffer.add_tool_call(
            tool_call_id="call_empty",
            tool_name="get_status",
            arguments="",
            tool_type="function"
        )

        assert buffer.is_complete("call_empty")
        parsed_args = buffer.parse_arguments("call_empty")
        assert parsed_args == {}

    def test_add_tool_call_with_whitespace_only(self):
        """Test adding tool call with whitespace-only arguments."""
        buffer = ToolCallBuffer()

        buffer.add_tool_call(
            tool_call_id="call_ws",
            tool_name="ping",
            arguments="   \n\t  ",
            tool_type="function"
        )

        assert buffer.is_complete("call_ws")
        parsed_args = buffer.parse_arguments("call_ws")
        assert parsed_args == {}

    def test_add_tool_call_with_truncated_json(self):
        """Test adding tool call with incomplete/truncated JSON."""
        buffer = ToolCallBuffer()

        # Truncated JSON (missing closing brace)
        buffer.add_tool_call(
            tool_call_id="call_truncated",
            tool_name="search",
            arguments='{"query": "python async", "limit": 10',
            tool_type="function"
        )

        assert len(buffer) == 1
        assert not buffer.is_complete("call_truncated")

        incomplete = buffer.get_incomplete_tool_calls()
        assert "call_truncated" in incomplete

    def test_parse_arguments_invalid_json_raises_error(self):
        """Test parsing invalid JSON raises ValueError with context."""
        buffer = ToolCallBuffer()

        buffer.add_tool_call(
            tool_call_id="call_bad",
            tool_name="search",
            arguments='{"invalid": json}',  # Invalid JSON
            tool_type="function"
        )

        with pytest.raises(ValueError) as exc_info:
            buffer.parse_arguments("call_bad")

        assert "call_bad" in str(exc_info.value)
        assert "search" in str(exc_info.value)

    def test_parse_arguments_nonexistent_id_raises_error(self):
        """Test parsing non-existent tool call ID raises KeyError."""
        buffer = ToolCallBuffer()

        with pytest.raises(KeyError) as exc_info:
            buffer.parse_arguments("nonexistent_id")

        assert "nonexistent_id" in str(exc_info.value)

    def test_get_all_complete_tool_calls(self):
        """Test getting all complete tool calls."""
        buffer = ToolCallBuffer()

        # Add mix of complete and incomplete calls
        buffer.add_tool_call("call_1", "search", '{"query": "test"}')
        buffer.add_tool_call("call_2", "calc", {"x": 5})
        buffer.add_tool_call("call_3", "bad", '{"incomplete": ')

        complete = buffer.get_all_complete_tool_calls()

        assert len(complete) == 2
        assert "call_1" in complete
        assert "call_2" in complete
        assert "call_3" not in complete

    def test_get_incomplete_tool_calls(self):
        """Test getting all incomplete tool calls."""
        buffer = ToolCallBuffer()

        buffer.add_tool_call("call_1", "search", '{"query": "test"}')
        buffer.add_tool_call("call_2", "bad1", '{"incomplete": ')
        buffer.add_tool_call("call_3", "bad2", 'not json at all')

        incomplete = buffer.get_incomplete_tool_calls()

        assert len(incomplete) == 2
        assert "call_2" in incomplete
        assert "call_3" in incomplete
        assert "call_1" not in incomplete

    def test_clear_buffer(self):
        """Test clearing all tool calls from buffer."""
        buffer = ToolCallBuffer()

        buffer.add_tool_call("call_1", "search", '{"query": "test"}')
        buffer.add_tool_call("call_2", "calc", {"x": 5})

        assert len(buffer) == 2

        buffer.clear()

        assert len(buffer) == 0
        assert buffer.get_all_complete_tool_calls() == {}

    def test_multiple_tool_calls_keyed_by_id(self):
        """Test buffer correctly manages multiple tool calls keyed by ID."""
        buffer = ToolCallBuffer()

        # Add multiple tool calls
        tool_calls = [
            ("call_abc", "search", '{"query": "test1"}'),
            ("call_def", "calculate", '{"x": 5, "y": 10}'),
            ("call_ghi", "get_weather", '{"city": "NYC"}'),
        ]

        for call_id, name, args in tool_calls:
            buffer.add_tool_call(call_id, name, args)

        assert len(buffer) == 3

        # Verify each can be retrieved independently
        for call_id, expected_name, _ in tool_calls:
            assert call_id in buffer
            tool_data = buffer.get_tool_call(call_id)
            assert tool_data["name"] == expected_name
            assert buffer.is_complete(call_id)

    def test_parse_arguments_preserves_types(self):
        """Test argument parsing preserves data types correctly."""
        buffer = ToolCallBuffer()

        buffer.add_tool_call(
            "call_types",
            "complex_tool",
            '{"string": "hello", "number": 42, "float": 3.14, "bool": true, "null": null, "array": [1, 2, 3]}'
        )

        parsed = buffer.parse_arguments("call_types")

        assert isinstance(parsed["string"], str)
        assert parsed["string"] == "hello"
        assert isinstance(parsed["number"], int)
        assert parsed["number"] == 42
        assert isinstance(parsed["float"], float)
        assert abs(parsed["float"] - 3.14) < 0.001
        assert isinstance(parsed["bool"], bool)
        assert parsed["bool"] is True
        assert parsed["null"] is None
        assert isinstance(parsed["array"], list)
        assert parsed["array"] == [1, 2, 3]

    def test_update_existing_tool_call(self):
        """Test updating an existing tool call (overwrite)."""
        buffer = ToolCallBuffer()

        # Add initial incomplete call
        buffer.add_tool_call("call_update", "search", '{"incomplete":')
        assert not buffer.is_complete("call_update")

        # Update with complete arguments
        buffer.add_tool_call("call_update", "search", '{"query": "complete"}')
        assert buffer.is_complete("call_update")

        parsed = buffer.parse_arguments("call_update")
        assert parsed == {"query": "complete"}

    def test_parse_arguments_with_nested_objects(self):
        """Test parsing complex nested JSON structures."""
        buffer = ToolCallBuffer()

        complex_json = json.dumps({
            "search": {
                "query": "python",
                "filters": {
                    "date_range": {"start": "2024-01-01", "end": "2024-12-31"},
                    "tags": ["async", "performance"]
                }
            },
            "options": {
                "limit": 10,
                "include_metadata": True
            }
        })

        buffer.add_tool_call("call_nested", "advanced_search", complex_json)

        parsed = buffer.parse_arguments("call_nested")

        assert parsed["search"]["query"] == "python"
        assert parsed["search"]["filters"]["date_range"]["start"] == "2024-01-01"
        assert "async" in parsed["search"]["filters"]["tags"]
        assert parsed["options"]["limit"] == 10
        assert parsed["options"]["include_metadata"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
