"""
Tool Executor for LiteLLM SDK Proxy

Handles automatic execution of tool calls from LLMs, particularly Supermemory tools.
This enables the proxy to transparently execute tools and return results to the model,
providing a seamless experience for clients that don't support tool execution.

Key Features:
- Automatic Supermemory search execution
- Configurable tool execution settings
- Error handling and timeout management
- Support for multiple tools
- Logging and monitoring

Architecture:
    When an LLM returns tool_calls in its response, this module executes those tools
    and formats the results to be sent back to the model for final response generation.

Example:
    ```python
    executor = ToolExecutor(config)

    # Execute a single tool call
    result = await executor.execute_tool_call(
        tool_name="supermemoryToolSearch",
        tool_args={"query": "Python memories"},
        user_id="user-123"
    )
    ```

References:
    - Anthropic Tool Use: https://docs.anthropic.com/claude/docs/tool-use
    - LangChain Agent Patterns
"""

import json
import logging
from typing import Any, Dict, List, Optional

from supermemory import Supermemory
from supermemory.types import SearchExecuteResponse

logger = logging.getLogger(__name__)


# =============================================================================
# Tool Executor
# =============================================================================


class ToolExecutor:
    """
    Executes tools called by LLMs.

    This class handles the execution of various tools, starting with Supermemory
    search. It provides a unified interface for tool execution with proper error
    handling and logging.

    Attributes:
        supermemory_client: Supermemory SDK client
        supermemory_api_key: API key for Supermemory
        timeout: Default timeout for tool execution
        max_results: Maximum number of search results
    """

    def __init__(
        self,
        supermemory_api_key: str,
        supermemory_base_url: str = "https://api.supermemory.ai",
        timeout: float = 30.0,
        max_results: int = 5,
    ):
        """
        Initialize the tool executor.

        Args:
            supermemory_api_key: API key for Supermemory
            supermemory_base_url: Base URL for Supermemory API
            timeout: Default timeout for tool execution (seconds)
            max_results: Maximum number of search results to return
        """
        self.supermemory_api_key = supermemory_api_key
        self.supermemory_base_url = supermemory_base_url
        self.timeout = timeout
        self.max_results = max_results

        # Initialize Supermemory client
        try:
            self.supermemory_client = Supermemory(
                api_key=supermemory_api_key,
                base_url=supermemory_base_url,
                timeout=timeout,
            )
            logger.info(f"✅ ToolExecutor initialized with Supermemory client")
        except Exception as e:
            logger.error(f"Failed to initialize Supermemory client: {e}")
            raise

    async def execute_tool_call(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        user_id: str,
        tool_call_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute a single tool call.

        Args:
            tool_name: Name of the tool to execute
            tool_args: Arguments for the tool
            user_id: User ID for context/memory isolation
            tool_call_id: ID of the tool call (for response matching)

        Returns:
            Dict containing tool execution result

        Raises:
            ValueError: If tool is not supported
            Exception: If tool execution fails
        """
        logger.info(f"Executing tool: {tool_name} for user: {user_id}")
        logger.debug(f"Tool args: {tool_args}")

        if tool_name == "supermemoryToolSearch":
            return await self._execute_supermemory_search(
                tool_args=tool_args,
                user_id=user_id,
                tool_call_id=tool_call_id,
            )
        else:
            raise ValueError(f"Unsupported tool: {tool_name}")

    async def _execute_supermemory_search(
        self,
        tool_args: Dict[str, Any],
        user_id: str,
        tool_call_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute Supermemory search tool.

        Args:
            tool_args: Tool arguments containing 'query'
            user_id: User ID for memory isolation
            tool_call_id: ID of the tool call

        Returns:
            Dict containing search results formatted for LLM
        """
        try:
            # Extract query from tool args
            if isinstance(tool_args, str):
                # If args is a JSON string, parse it
                tool_args = json.loads(tool_args)

            query = tool_args.get("query", "")
            if not query:
                return {
                    "tool_call_id": tool_call_id,
                    "error": "No query provided",
                    "results": []
                }

            logger.info(f"Searching Supermemory: query='{query}', user={user_id}")

            # Execute search using Supermemory SDK
            # Note: The SDK handles async internally, so we use the sync version
            response: SearchExecuteResponse = self.supermemory_client.search.execute(
                q=query,
                limit=self.max_results,
                include_summary=True,
                rerank=True,
            )

            # Format results for LLM consumption
            results = []
            if hasattr(response, 'results') and response.results:
                for idx, result in enumerate(response.results[:self.max_results]):
                    formatted_result = {
                        "index": idx + 1,
                        "content": getattr(result, 'content', ''),
                        "source": getattr(result, 'source', ''),
                        "relevance_score": getattr(result, 'score', 0),
                    }
                    # Add optional fields if available
                    if hasattr(result, 'title'):
                        formatted_result["title"] = result.title
                    if hasattr(result, 'url'):
                        formatted_result["url"] = result.url

                    results.append(formatted_result)

            logger.info(f"✅ Supermemory search completed: {len(results)} results")

            # Return formatted response
            return {
                "tool_call_id": tool_call_id,
                "query": query,
                "results_count": len(results),
                "results": results,
                "user_id": user_id,
            }

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse tool arguments: {e}")
            return {
                "tool_call_id": tool_call_id,
                "error": f"Invalid tool arguments format: {str(e)}",
                "results": []
            }
        except Exception as e:
            logger.error(f"Supermemory search failed: {e}", exc_info=True)
            return {
                "tool_call_id": tool_call_id,
                "error": f"Search failed: {str(e)}",
                "results": []
            }

    def format_tool_result_for_llm(self, tool_result: Dict[str, Any]) -> str:
        """
        Format tool execution result for LLM consumption.

        The LLM expects tool results as text that it can understand and use
        to formulate its final response to the user.

        Args:
            tool_result: Raw tool execution result

        Returns:
            Formatted string for LLM
        """
        if "error" in tool_result:
            return f"Tool execution error: {tool_result['error']}"

        if "results" in tool_result and tool_result["results"]:
            formatted_text = f"Found {tool_result['results_count']} results:\n\n"

            for result in tool_result["results"]:
                formatted_text += f"Result {result['index']}:\n"
                if "title" in result:
                    formatted_text += f"Title: {result['title']}\n"
                formatted_text += f"Content: {result['content']}\n"
                if "source" in result:
                    formatted_text += f"Source: {result['source']}\n"
                if "url" in result:
                    formatted_text += f"URL: {result['url']}\n"
                formatted_text += f"Relevance: {result['relevance_score']:.2f}\n\n"

            return formatted_text.strip()
        else:
            return "No results found."


# =============================================================================
# Tool Execution Configuration
# =============================================================================


class ToolExecutionConfig:
    """Configuration for tool execution."""

    def __init__(
        self,
        enabled: bool = True,
        max_iterations: int = 10,
        timeout_per_tool: float = 30.0,
        supermemory_api_key: Optional[str] = None,
        supermemory_base_url: str = "https://api.supermemory.ai",
    ):
        """
        Initialize tool execution configuration.

        Args:
            enabled: Whether tool execution is enabled
            max_iterations: Maximum number of tool execution loops
            timeout_per_tool: Timeout for each tool execution (seconds)
            supermemory_api_key: Supermemory API key
            supermemory_base_url: Supermemory API base URL
        """
        self.enabled = enabled
        self.max_iterations = max_iterations
        self.timeout_per_tool = timeout_per_tool
        self.supermemory_api_key = supermemory_api_key
        self.supermemory_base_url = supermemory_base_url

    @classmethod
    def from_config_dict(cls, config: Dict[str, Any]) -> "ToolExecutionConfig":
        """
        Create configuration from dictionary.

        Args:
            config: Configuration dictionary

        Returns:
            ToolExecutionConfig instance
        """
        return cls(
            enabled=config.get("enabled", True),
            max_iterations=config.get("max_iterations", 10),
            timeout_per_tool=config.get("timeout_per_tool", 30.0),
            supermemory_api_key=config.get("supermemory_api_key"),
            supermemory_base_url=config.get("supermemory_base_url", "https://api.supermemory.ai"),
        )


# =============================================================================
# Utility Functions
# =============================================================================


def should_execute_tools(config: ToolExecutionConfig) -> bool:
    """
    Check if tool execution should be enabled.

    Args:
        config: Tool execution configuration

    Returns:
        True if tools should be executed
    """
    if not config.enabled:
        logger.debug("Tool execution is disabled")
        return False

    if not config.supermemory_api_key:
        logger.warning("Tool execution enabled but no Supermemory API key configured")
        return False

    return True