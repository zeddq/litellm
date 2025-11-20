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
from typing import Any, Dict, List, Optional, Tuple

import litellm
from supermemory import Supermemory
from supermemory.types import SearchExecuteResponse

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


# =============================================================================
# Parameter Validation Helpers
# =============================================================================


def validate_parameter_type(
    param_name: str,
    value: Any,
    expected_type: type,
    example_value: Any = None,
) -> Optional["ToolExecutionError"]:
    """
    Validate that a parameter has the expected type.

    Args:
        param_name: Name of the parameter to validate
        value: The actual value to check
        expected_type: Expected Python type
        example_value: Example of a valid value

    Returns:
        ToolExecutionError if validation fails, None if valid
    """
    if not isinstance(value, expected_type):
        return ToolExecutionError(
            error_type="invalid_type",
            message=f"Parameter '{param_name}' must be {expected_type.__name__}, got {type(value).__name__}",
            parameter=param_name,
            required_parameters=[param_name],
            example={param_name: example_value or f"<{expected_type.__name__} value>"},
            retry_hint=f"Retry the tool call with '{param_name}' as a {expected_type.__name__} value."
        )
    return None


def validate_parameter_not_empty(
    param_name: str,
    value: str,
    example_value: str = None,
) -> Optional["ToolExecutionError"]:
    """
    Validate that a string parameter is not empty.

    Args:
        param_name: Name of the parameter to validate
        value: The string value to check
        example_value: Example of a valid value

    Returns:
        ToolExecutionError if validation fails, None if valid
    """
    if not value or not value.strip():
        return ToolExecutionError(
            error_type="invalid_value",
            message=f"Parameter '{param_name}' cannot be empty",
            parameter=param_name,
            required_parameters=[param_name],
            example={param_name: example_value or "valid non-empty value"},
            retry_hint=f"Retry the tool call with a non-empty '{param_name}' value."
        )
    return None


# =============================================================================
# Tool Execution Error
# =============================================================================


class ToolExecutionError:
    """
    Structured tool execution error with guidance for LLM self-correction.

    This class provides detailed error information that helps LLMs understand
    what went wrong and how to fix it, enabling multi-round tool call recovery.

    Attributes:
        error_type: Classification of error (e.g., 'missing_parameter', 'invalid_type')
        message: Human-readable error message
        parameter: Name of the problematic parameter (if applicable)
        required_parameters: List of all required parameters
        example: Example of correct parameter usage
        retry_hint: Explicit guidance for retrying the tool call
    """

    def __init__(
        self,
        error_type: str,
        message: str,
        parameter: Optional[str] = None,
        required_parameters: Optional[List[str]] = None,
        example: Optional[Dict[str, Any]] = None,
        retry_hint: Optional[str] = None,
    ):
        """
        Initialize a structured tool execution error.

        Args:
            error_type: Error classification (e.g., 'missing_parameter')
            message: Descriptive error message
            parameter: Name of problematic parameter
            required_parameters: List of required parameter names
            example: Example showing correct usage
            retry_hint: Guidance for fixing and retrying
        """
        self.error_type = error_type
        self.message = message
        self.parameter = parameter
        self.required_parameters = required_parameters or []
        self.example = example
        self.retry_hint = retry_hint

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert error to dictionary format.

        Returns:
            Dictionary representation with all error details
        """
        result = {
            "type": self.error_type,
            "message": self.message,
        }
        if self.parameter:
            result["parameter"] = self.parameter
        if self.required_parameters:
            result["required_parameters"] = self.required_parameters
        if self.example:
            result["example"] = self.example
        if self.retry_hint:
            result["retry_hint"] = self.retry_hint
        return result


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

    def _extract_query_argument(
        self,
        tool_args: Dict[str, Any],
    ) -> Tuple[Optional[str], str, Optional["ToolExecutionError"]]:
        """
        Normalize supported query parameters.

        Returns:
            Tuple of (query string or None, parameter name used, error if any)
        """
        if "query" in tool_args:
            return tool_args.get("query"), "query", None

        if "queries" in tool_args:
            queries_value = tool_args["queries"]
            if isinstance(queries_value, str):
                return queries_value, "queries", None

            if isinstance(queries_value, list):
                normalized_queries: List[str] = []

                for value in queries_value:
                    if not isinstance(value, str):
                        return None, "queries", ToolExecutionError(
                            error_type="invalid_type",
                            message="Each entry in 'queries' must be a string.",
                            parameter="queries",
                            required_parameters=["queries"],
                            example={"queries": ["project roadmap", "product brief"]},
                            retry_hint="Retry with 'queries' as a list of non-empty strings.",
                        )

                    stripped = value.strip()
                    if stripped:
                        normalized_queries.append(stripped)

                if not normalized_queries:
                    return None, "queries", ToolExecutionError(
                        error_type="invalid_value",
                        message="The 'queries' list must include at least one non-empty string.",
                        parameter="queries",
                        required_parameters=["queries"],
                        example={"queries": ["recent invoices", "expense reports"]},
                        retry_hint="Provide at least one descriptive search phrase.",
                    )

                combined_query = " OR ".join(normalized_queries)
                return combined_query, "queries", None

            return None, "queries", ToolExecutionError(
                error_type="invalid_type",
                message="Parameter 'queries' must be a string or list of strings.",
                parameter="queries",
                required_parameters=["queries"],
                example={"queries": ["roadmap", "release notes"]},
                retry_hint="Send 'queries' as ['first term', 'second term'] or provide a single string.",
            )

        return None, "query", None

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
        litellm.callbacks
        try:
            # Extract query from tool args
            if isinstance(tool_args, str):
                # If args is a JSON string, parse it
                tool_args = json.loads(tool_args)

            query, query_param, extraction_error = self._extract_query_argument(tool_args)
            if extraction_error:
                logger.warning(
                    f"Tool execution error: {extraction_error.error_type}",
                    extra={
                        "tool_name": "supermemoryToolSearch",
                        "error_type": extraction_error.error_type,
                        "parameter": query_param,
                        "user_id": user_id,
                        "tool_call_id": tool_call_id,
                    }
                )

                return {
                    "tool_call_id": tool_call_id,
                    "error": extraction_error.to_dict(),
                    "results": []
                }

            # Validate query parameter exists
            if query is None:
                error = ToolExecutionError(
                    error_type="missing_parameter",
                    message="Either 'query' (string) or 'queries' (array of strings) is required for document search",
                    parameter="query",
                    required_parameters=["query"],
                    example={
                        "query": "python asyncio patterns",
                        "queries": ["python docs", "asyncio patterns"],
                    },
                    retry_hint="Retry the tool call with a single 'query' string or provide 'queries' as a list of related phrases."
                )
                
                # Log telemetry for missing parameter error
                logger.warning(
                    f"Tool execution error: missing_parameter",
                    extra={
                        "tool_name": "supermemoryToolSearch",
                        "error_type": "missing_parameter",
                        "parameter": "query",
                        "user_id": user_id,
                        "tool_call_id": tool_call_id,
                    }
                )
                
                return {
                    "tool_call_id": tool_call_id,
                    "error": error.to_dict(),
                    "results": []
                }

            # Validate query is a string
            type_error = validate_parameter_type(
                param_name=query_param,
                value=query,
                expected_type=str,
                example_value="python asyncio patterns"
            )
            if type_error:
                # Log telemetry for type error
                logger.warning(
                    f"Tool execution error: invalid_type",
                    extra={
                        "tool_name": "supermemoryToolSearch",
                        "error_type": "invalid_type",
                        "parameter": query_param,
                        "expected_type": "str",
                        "actual_type": type(query).__name__,
                        "user_id": user_id,
                        "tool_call_id": tool_call_id,
                    }
                )
                
                return {
                    "tool_call_id": tool_call_id,
                    "error": type_error.to_dict(),
                    "results": []
                }

            # Validate query is not empty
            empty_error = validate_parameter_not_empty(
                param_name=query_param,
                value=query,
                example_value="python asyncio patterns"
            )
            if empty_error:
                # Log telemetry for empty value error
                logger.warning(
                    f"Tool execution error: invalid_value",
                    extra={
                        "tool_name": "supermemoryToolSearch",
                        "error_type": "invalid_value",
                        "parameter": query_param,
                        "user_id": user_id,
                        "tool_call_id": tool_call_id,
                    }
                )
                
                return {
                    "tool_call_id": tool_call_id,
                    "error": empty_error.to_dict(),
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
            
            error = ToolExecutionError(
                error_type="invalid_arguments",
                message=f"Invalid tool arguments format: {str(e)}",
                parameter="arguments",
                required_parameters=["query"],
                example={"query": "python asyncio patterns"},
                retry_hint="Ensure the tool arguments are valid JSON format."
            )
            
            # Log telemetry
            logger.error(
                "Tool execution error: invalid_arguments",
                extra={
                    "tool_name": "supermemoryToolSearch",
                    "error_type": "invalid_arguments",
                    "user_id": user_id,
                    "tool_call_id": tool_call_id,
                    "exception": str(e),
                }
            )
            
            return {
                "tool_call_id": tool_call_id,
                "error": error.to_dict(),
                "results": []
            }
        except Exception as e:
            error_str = str(e).lower()
            
            # Detect authentication errors
            if any(keyword in error_str for keyword in ["authentication", "unauthorized", "api key", "401", "403"]):
                error = ToolExecutionError(
                    error_type="authentication_error",
                    message="Authentication failed. Please check the API key configuration.",
                    parameter="api_key",
                    required_parameters=["api_key"],
                    example=None,  # Don't show API key examples
                    retry_hint="Verify that the Supermemory API key is correctly configured in the environment."
                )
                
                # Log telemetry
                logger.error(
                    "Tool execution error: authentication_error",
                    extra={
                        "tool_name": "supermemoryToolSearch",
                        "error_type": "authentication_error",
                        "user_id": user_id,
                        "tool_call_id": tool_call_id,
                        "exception": str(e),
                    }
                )
                
                return {
                    "tool_call_id": tool_call_id,
                    "error": error.to_dict(),
                    "results": []
                }
            
            # Detect rate limit errors
            elif any(keyword in error_str for keyword in ["rate limit", "too many requests", "429"]):
                error = ToolExecutionError(
                    error_type="rate_limit_exceeded",
                    message="Rate limit exceeded. Please try again in a few moments.",
                    parameter=None,
                    required_parameters=["query"],
                    example={"query": "python asyncio patterns"},
                    retry_hint="Wait a few moments before retrying this search. Consider caching frequently accessed documents."
                )
                
                # Log telemetry
                logger.warning(
                    "Tool execution error: rate_limit_exceeded",
                    extra={
                        "tool_name": "supermemoryToolSearch",
                        "error_type": "rate_limit_exceeded",
                        "user_id": user_id,
                        "tool_call_id": tool_call_id,
                        "exception": str(e),
                    }
                )
                
                return {
                    "tool_call_id": tool_call_id,
                    "error": error.to_dict(),
                    "results": []
                }
            
            # Generic error fallback
            else:
                logger.error(f"Supermemory search failed: {e}", exc_info=True)
                
                error = ToolExecutionError(
                    error_type="execution_error",
                    message=f"Search execution failed: {str(e)}",
                    parameter=None,
                    required_parameters=["query"],
                    example={"query": "python asyncio patterns"},
                    retry_hint="This may be a temporary issue. Try the search again or check the query format."
                )
                
                # Log telemetry
                logger.error(
                    "Tool execution error: execution_error",
                    extra={
                        "tool_name": "supermemoryToolSearch",
                        "error_type": "execution_error",
                        "user_id": user_id,
                        "tool_call_id": tool_call_id,
                        "exception": str(e),
                        "exception_type": type(e).__name__,
                    }
                )
                
                return {
                    "tool_call_id": tool_call_id,
                    "error": error.to_dict(),
                    "results": []
                }

    def format_tool_result_for_llm(self, tool_result: Dict[str, Any]) -> str:
        """
        Format tool execution result for LLM consumption.

        The LLM expects tool results as text that it can understand and use
        to formulate its final response to the user. For errors, provides
        structured guidance to enable self-correction.

        Args:
            tool_result: Raw tool execution result

        Returns:
            Formatted string for LLM
        """
        if "error" in tool_result:
            error = tool_result["error"]
            
            # Handle structured errors with guidance
            if isinstance(error, dict):
                msg = f"❌ Tool Call Error: {error.get('message', 'Unknown error')}\n\n"
                
                if error.get('parameter'):
                    msg += f"Missing Parameter: '{error['parameter']}'\n"
                
                if error.get('required_parameters'):
                    msg += f"Required Parameters: {', '.join(error['required_parameters'])}\n"
                
                if error.get('example'):
                    msg += f"\nExample Usage:\n{json.dumps(error['example'], indent=2)}\n"
                
                if error.get('retry_hint'):
                    msg += f"\n💡 {error['retry_hint']}\n"
                
                return msg
            else:
                # Legacy string error (backward compatibility)
                return f"Tool execution error: {error}"

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
