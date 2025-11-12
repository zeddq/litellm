"""
Test streaming tool call buffering with finish_reason tracking.

This test validates the critical streaming behavior:
1. Tool call arguments arrive incrementally across multiple chunks
2. Each chunk adds more text to the arguments buffer
3. The LAST chunk has finish_reason set (not None)
4. Tool calls are marked "finished" only when finish_reason is received
5. Tool execution happens AFTER finish_reason indicates completion
"""
import json
import pytest
from typing import Any, Dict, Optional
import logging

# Inline ToolCallBuffer implementation for testing
# (copied from litellm_proxy_sdk.py to avoid import issues)

logger = logging.getLogger(__name__)


class ToolCallBuffer:
    """
    Buffer for managing tool call state during streaming/non-streaming responses.
    
    In STREAMING mode:
    - Tool call arguments arrive incrementally across multiple chunks
    - Each chunk adds more text to the arguments string
    - The LAST chunk has finish_reason set (not None)
    - Tool calls are marked "finished" only when finish_reason is present
    - Tool execution happens AFTER finish_reason indicates completion
    """
    
    def __init__(self):
        """Initialize empty tool call buffer."""
        self.buffer: Dict[str, Dict[str, Any]] = {}
        self.finished_tool_ids: set[str] = set()
        
    def add_tool_call(
        self,
        tool_call_id: str,
        tool_name: str,
        arguments: Any,
        tool_type: str = "function"
    ) -> None:
        """Add or update a tool call in the buffer."""
        if tool_call_id in self.buffer:
            existing = self.buffer[tool_call_id]
            updated_name = tool_name if tool_name else existing["name"]
            updated_arguments = arguments if arguments is not None else existing["arguments"]
            
            self.buffer[tool_call_id] = {
                "id": tool_call_id,
                "name": updated_name,
                "arguments": updated_arguments,
                "type": tool_type,
                "complete": self._is_arguments_complete(updated_arguments)
            }
        else:
            self.buffer[tool_call_id] = {
                "id": tool_call_id,
                "name": tool_name,
                "arguments": arguments,
                "type": tool_type,
                "complete": self._is_arguments_complete(arguments)
            }
    
    def append_arguments(self, tool_call_id: str, additional_arguments: str) -> None:
        """Append additional arguments to an existing tool call (STREAMING mode)."""
        if tool_call_id not in self.buffer:
            raise KeyError(f"Cannot append to unknown tool_call_id: {tool_call_id}")
        
        tool_data = self.buffer[tool_call_id]
        current_args = tool_data["arguments"]
        
        if current_args is None or current_args == "":
            current_args = ""
        elif isinstance(current_args, dict):
            current_args = json.dumps(current_args)
        elif not isinstance(current_args, str):
            current_args = str(current_args)
        
        if additional_arguments:
            updated_args = current_args + additional_arguments
        else:
            updated_args = current_args
        
        tool_data["arguments"] = updated_args
        tool_data["complete"] = self._is_arguments_complete(updated_args)
    
    def mark_finished_by_finish_reason(self, tool_call_id: Optional[str] = None) -> None:
        """Mark tool call(s) as finished because finish_reason was received."""
        if tool_call_id is not None:
            if tool_call_id in self.buffer:
                self.finished_tool_ids.add(tool_call_id)
        else:
            for tid in self.buffer.keys():
                self.finished_tool_ids.add(tid)
    
    def is_finished(self, tool_call_id: str) -> bool:
        """Check if a tool call is finished and ready for execution."""
        if tool_call_id not in self.buffer:
            return False
        
        if not self.buffer[tool_call_id]["complete"]:
            return False
        
        # Must be explicitly marked finished (finish_reason received)
        return tool_call_id in self.finished_tool_ids
    
    def is_complete(self, tool_call_id: str) -> bool:
        """Check if a tool call's arguments are complete (valid JSON)."""
        if tool_call_id not in self.buffer:
            return False
        return self.buffer[tool_call_id]["complete"]
    
    def _is_arguments_complete(self, arguments: Any) -> bool:
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
    
    def parse_arguments(self, tool_call_id: str) -> Dict[str, Any]:
        """Parse and return arguments for a tool call."""
        if tool_call_id not in self.buffer:
            raise KeyError(f"Tool call ID {tool_call_id} not found in buffer")
        
        tool_data = self.buffer[tool_call_id]
        arguments = tool_data["arguments"]
        
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
                raise ValueError(f"Failed to parse arguments JSON: {e}")
        
        raise ValueError(f"Unexpected argument type {type(arguments)}")
    
    def get_all_finished_tool_calls(self) -> Dict[str, Dict[str, Any]]:
        """Get all finished tool calls ready for execution."""
        return {
            call_id: call_data
            for call_id, call_data in self.buffer.items()
            if self.is_finished(call_id)
        }
    
    def get_all_complete_tool_calls(self) -> Dict[str, Dict[str, Any]]:
        """Get all tool calls with complete arguments (valid JSON)."""
        return {
            call_id: call_data
            for call_id, call_data in self.buffer.items()
            if call_data["complete"]
        }
    
    def get_incomplete_tool_calls(self) -> Dict[str, Dict[str, Any]]:
        """Get all incomplete tool calls (for debugging/logging)."""
        return {
            call_id: call_data
            for call_id, call_data in self.buffer.items()
            if not call_data["complete"]
        }
    
    def get_unfinished_tool_calls(self) -> Dict[str, Dict[str, Any]]:
        """Get all unfinished tool calls (haven't seen finish_reason yet)."""
        return {
            call_id: call_data
            for call_id, call_data in self.buffer.items()
            if not self.is_finished(call_id)
        }
    
    def __len__(self) -> int:
        """Return number of tool calls in buffer."""
        return len(self.buffer)


class TestToolCallBufferStreaming:
    """Test ToolCallBuffer streaming behavior with finish_reason tracking."""
    
    def test_streaming_incremental_arguments(self):
        """Test that arguments can be appended incrementally (streaming mode)."""
        buffer = ToolCallBuffer()
        
        # Chunk 1: Initial tool call with partial JSON
        buffer.add_tool_call(
            tool_call_id="call_123",
            tool_name="search",
            arguments='{"query":',
            tool_type="function"
        )
        
        # Should be incomplete (invalid JSON)
        assert not buffer.is_complete("call_123")
        assert not buffer.is_finished("call_123")
        
        # Chunk 2: More arguments
        buffer.append_arguments("call_123", ' "python')
        assert not buffer.is_complete("call_123")
        assert not buffer.is_finished("call_123")
        
        # Chunk 3: Complete the JSON
        buffer.append_arguments("call_123", ' async"}')
        
        # Now arguments are complete (valid JSON)
        assert buffer.is_complete("call_123")
        
        # BUT not finished yet (no finish_reason)
        assert not buffer.is_finished("call_123")
        
        # Chunk 4: finish_reason signals completion
        buffer.mark_finished_by_finish_reason("call_123")
        
        # NOW it's finished and ready for execution
        assert buffer.is_finished("call_123")
        
        # Parse arguments
        args = buffer.parse_arguments("call_123")
        assert args == {"query": "python async"}
    
    def test_non_streaming_immediate_finish(self):
        """Test that non-streaming tool calls are immediately finished."""
        buffer = ToolCallBuffer()
        
        # Non-streaming: complete tool call arrives all at once
        buffer.add_tool_call(
            tool_call_id="call_456",
            tool_name="weather",
            arguments='{"location": "SF"}',
            tool_type="function"
        )
        
        # Arguments are complete
        assert buffer.is_complete("call_456")
        
        # Mark as finished (simulating finish_reason in response)
        buffer.mark_finished_by_finish_reason("call_456")
        
        # Now finished and executable
        assert buffer.is_finished("call_456")
        
        args = buffer.parse_arguments("call_456")
        assert args == {"location": "SF"}
    
    def test_finish_reason_marks_all_tools(self):
        """Test that finish_reason can mark all buffered tools as finished."""
        buffer = ToolCallBuffer()
        
        # Add multiple tool calls (simulating streaming)
        buffer.add_tool_call("call_1", "tool1", '{"a": 1}', "function")
        buffer.add_tool_call("call_2", "tool2", '{"b": 2}', "function")
        buffer.add_tool_call("call_3", "tool3", '{"c": 3}', "function")
        
        # All complete but not finished
        assert buffer.is_complete("call_1")
        assert buffer.is_complete("call_2")
        assert buffer.is_complete("call_3")
        assert not buffer.is_finished("call_1")
        assert not buffer.is_finished("call_2")
        assert not buffer.is_finished("call_3")
        
        # Mark all as finished (finish_reason applies to all)
        buffer.mark_finished_by_finish_reason()
        
        # All should now be finished
        assert buffer.is_finished("call_1")
        assert buffer.is_finished("call_2")
        assert buffer.is_finished("call_3")
        
        # Get all finished tool calls
        finished = buffer.get_all_finished_tool_calls()
        assert len(finished) == 3
        assert "call_1" in finished
        assert "call_2" in finished
        assert "call_3" in finished
    
    def test_incomplete_arguments_not_finished(self):
        """Test that incomplete arguments prevent finish even with finish_reason."""
        buffer = ToolCallBuffer()
        
        # Add tool call with incomplete JSON
        buffer.add_tool_call(
            tool_call_id="call_bad",
            tool_name="broken",
            arguments='{"incomplete": ',  # Invalid JSON
            tool_type="function"
        )
        
        # Mark as finished by finish_reason
        buffer.mark_finished_by_finish_reason("call_bad")
        
        # Arguments are incomplete (invalid JSON)
        assert not buffer.is_complete("call_bad")
        
        # Should NOT be finished (incomplete arguments)
        assert not buffer.is_finished("call_bad")
        
        # Should not appear in finished calls
        finished = buffer.get_all_finished_tool_calls()
        assert "call_bad" not in finished
    
    def test_empty_arguments_are_valid(self):
        """Test that empty/None arguments are considered complete and finishable."""
        buffer = ToolCallBuffer()
        
        # Tool with no arguments (empty string)
        buffer.add_tool_call("call_empty", "no_args_tool", "", "function")
        buffer.mark_finished_by_finish_reason("call_empty")
        
        assert buffer.is_complete("call_empty")
        assert buffer.is_finished("call_empty")
        assert buffer.parse_arguments("call_empty") == {}
        
        # Tool with None arguments
        buffer.add_tool_call("call_none", "no_args_tool2", None, "function")
        buffer.mark_finished_by_finish_reason("call_none")
        
        assert buffer.is_complete("call_none")
        assert buffer.is_finished("call_none")
        assert buffer.parse_arguments("call_none") == {}
    
    def test_get_all_finished_vs_complete(self):
        """Test distinction between finished and complete tool calls."""
        buffer = ToolCallBuffer()
        
        # Add tool calls with various states
        buffer.add_tool_call("complete_not_finished", "tool1", '{"x": 1}', "function")
        buffer.add_tool_call("incomplete_not_finished", "tool2", '{"y":', "function")
        buffer.add_tool_call("complete_and_finished", "tool3", '{"z": 3}', "function")
        
        # Mark only one as finished
        buffer.mark_finished_by_finish_reason("complete_and_finished")
        
        # Check complete calls (includes unfinished with valid JSON)
        complete_calls = buffer.get_all_complete_tool_calls()
        assert len(complete_calls) == 2  # complete_not_finished + complete_and_finished
        assert "complete_not_finished" in complete_calls
        assert "complete_and_finished" in complete_calls
        
        # Check finished calls (only those with finish_reason AND complete args)
        finished_calls = buffer.get_all_finished_tool_calls()
        assert len(finished_calls) == 1  # Only complete_and_finished
        assert "complete_and_finished" in finished_calls
        
        # Check incomplete calls
        incomplete_calls = buffer.get_incomplete_tool_calls()
        assert len(incomplete_calls) == 1
        assert "incomplete_not_finished" in incomplete_calls
        
        # Check unfinished calls
        unfinished_calls = buffer.get_unfinished_tool_calls()
        assert len(unfinished_calls) == 2  # complete_not_finished + incomplete_not_finished
        assert "complete_not_finished" in unfinished_calls
        assert "incomplete_not_finished" in unfinished_calls
    
    def test_streaming_realistic_scenario(self):
        """Test realistic streaming scenario with multiple chunks and finish_reason."""
        buffer = ToolCallBuffer()
        
        # Simulate streaming chunks for a search tool call
        
        # Chunk 1: Tool call starts, ID and name
        buffer.add_tool_call(
            tool_call_id="toolu_01ABC",
            tool_name="supermemoryToolSearch",
            arguments="",  # Empty initially
            tool_type="function"
        )
        assert not buffer.is_finished("toolu_01ABC")
        
        # Chunk 2: Arguments start
        buffer.append_arguments("toolu_01ABC", '{"')
        assert not buffer.is_complete("toolu_01ABC")
        assert not buffer.is_finished("toolu_01ABC")
        
        # Chunk 3: More arguments
        buffer.append_arguments("toolu_01ABC", 'query')
        assert not buffer.is_complete("toolu_01ABC")
        
        # Chunk 4: More arguments
        buffer.append_arguments("toolu_01ABC", '": "')
        assert not buffer.is_complete("toolu_01ABC")
        
        # Chunk 5: More arguments
        buffer.append_arguments("toolu_01ABC", 'How does')
        assert not buffer.is_complete("toolu_01ABC")
        
        # Chunk 6: More arguments
        buffer.append_arguments("toolu_01ABC", ' async work')
        assert not buffer.is_complete("toolu_01ABC")
        
        # Chunk 7: Complete arguments
        buffer.append_arguments("toolu_01ABC", '"}')
        assert buffer.is_complete("toolu_01ABC")
        assert not buffer.is_finished("toolu_01ABC")  # Still not finished!
        
        # Chunk 8: Empty chunk with finish_reason (typical pattern)
        buffer.mark_finished_by_finish_reason("toolu_01ABC")
        
        # NOW it's finished!
        assert buffer.is_finished("toolu_01ABC")
        
        # Parse and verify
        args = buffer.parse_arguments("toolu_01ABC")
        assert args == {"query": "How does async work"}
        
        # Should appear in finished calls
        finished = buffer.get_all_finished_tool_calls()
        assert len(finished) == 1
        assert "toolu_01ABC" in finished
    
    def test_multiple_tools_streaming(self):
        """Test multiple tool calls streaming in parallel."""
        buffer = ToolCallBuffer()
        
        # Two tool calls being streamed
        buffer.add_tool_call("call_A", "tool_A", '{"x":', "function")
        buffer.add_tool_call("call_B", "tool_B", '{"y":', "function")
        
        # Append to first tool
        buffer.append_arguments("call_A", ' 1}')
        assert buffer.is_complete("call_A")
        assert not buffer.is_complete("call_B")
        
        # Append to second tool
        buffer.append_arguments("call_B", ' 2}')
        assert buffer.is_complete("call_B")
        
        # Both complete but not finished
        assert not buffer.is_finished("call_A")
        assert not buffer.is_finished("call_B")
        
        # Mark both as finished (finish_reason received)
        buffer.mark_finished_by_finish_reason()
        
        # Both should be finished
        assert buffer.is_finished("call_A")
        assert buffer.is_finished("call_B")
        
        finished = buffer.get_all_finished_tool_calls()
        assert len(finished) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
