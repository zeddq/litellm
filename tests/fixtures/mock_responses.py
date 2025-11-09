"""
Mock responses for testing LiteLLM SDK integration.

Provides realistic mock responses for:
- LiteLLM completion responses (streaming and non-streaming)
- LiteLLM exceptions
- HTTP responses from providers
"""

from typing import Dict, Any, List, Optional


# =============================================================================
# Mock Completion Responses
# =============================================================================


def mock_completion_response(
    model: str = "claude-sonnet-4.5",
    content: str = "Hello! How can I help you today?",
    usage_tokens: Dict[str, int] = None,
) -> Dict[str, Any]:
    """
    Create a mock non-streaming completion response.

    Args:
        model: Model identifier
        content: Response content
        usage_tokens: Token usage (prompt, completion, total)

    Returns:
        Mock response in OpenAI format
    """
    if usage_tokens is None:
        usage_tokens = {"prompt_tokens": 10, "completion_tokens": 15, "total_tokens": 25}

    return {
        "id": "chatcmpl-test-123",
        "object": "chat.completion",
        "created": 1234567890,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": usage_tokens,
    }


def mock_streaming_chunk(
    content: str = "Hello",
    finish_reason: str = None,
    index: int = 0,
) -> Dict[str, Any]:
    """
    Create a mock streaming completion chunk.

    Args:
        content: Chunk content
        finish_reason: Finish reason (stop, length, etc.) or None
        index: Choice index

    Returns:
        Mock chunk in OpenAI streaming format
    """
    return {
        "id": "chatcmpl-test-123",
        "object": "chat.completion.chunk",
        "created": 1234567890,
        "model": "claude-sonnet-4.5",
        "choices": [
            {
                "index": index,
                "delta": {"content": content} if content else {},
                "finish_reason": finish_reason,
            }
        ],
    }


def mock_streaming_chunks_sequence() -> List[Dict[str, Any]]:
    """
    Create a realistic sequence of streaming chunks.

    Returns:
        List of chunks representing a complete streaming response
    """
    return [
        mock_streaming_chunk("Hello"),
        mock_streaming_chunk("! How"),
        mock_streaming_chunk(" can"),
        mock_streaming_chunk(" I help"),
        mock_streaming_chunk(" you?"),
        mock_streaming_chunk("", finish_reason="stop"),
    ]


# =============================================================================
# Mock Error Responses
# =============================================================================


def mock_error_response(
    status_code: int,
    error_type: str,
    message: str,
    code: str = None,
) -> Dict[str, Any]:
    """
    Create a mock error response.

    Args:
        status_code: HTTP status code
        error_type: Error type string
        message: Error message
        code: Optional error code

    Returns:
        Mock error response
    """
    error_content = {
        "message": message,
        "type": error_type,
    }

    if code:
        error_content["code"] = code

    return {
        "status_code": status_code,
        "error": error_content,
    }


def mock_rate_limit_error() -> Dict[str, Any]:
    """Mock 429 Rate Limit error."""
    return mock_error_response(
        status_code=429,
        error_type="rate_limit_error",
        message="Rate limit exceeded. Please retry after 60 seconds.",
        code="rate_limit_exceeded",
    )


def mock_auth_error() -> Dict[str, Any]:
    """Mock 401 Authentication error."""
    return mock_error_response(
        status_code=401,
        error_type="authentication_error",
        message="Invalid API key or authentication failed",
        code="invalid_api_key",
    )


def mock_context_length_error() -> Dict[str, Any]:
    """Mock 400 Context Length Exceeded error."""
    return mock_error_response(
        status_code=400,
        error_type="invalid_request_error",
        message="Context length exceeded maximum allowed tokens",
        code="context_length_exceeded",
    )


def mock_service_unavailable_error() -> Dict[str, Any]:
    """Mock 503 Service Unavailable error."""
    return mock_error_response(
        status_code=503,
        error_type="service_unavailable",
        message="Service temporarily unavailable. Please retry later.",
        code="service_unavailable",
    )


# =============================================================================
# Mock Models List Response
# =============================================================================


def mock_models_list(model_names: List[str] = None) -> Dict[str, Any]:
    """
    Create a mock models list response.

    Args:
        model_names: List of model names to include

    Returns:
        Mock models list in OpenAI format
    """
    if model_names is None:
        model_names = ["claude-sonnet-4.5", "gpt-4", "gpt-5-pro"]

    return {
        "object": "list",
        "data": [
            {
                "id": model_name,
                "object": "model",
                "created": 1234567890,
                "owned_by": "litellm",
                "permission": [],
                "root": model_name,
                "parent": None,
            }
            for model_name in model_names
        ],
    }


# =============================================================================
# Mock Memory Routing Info
# =============================================================================


def mock_routing_info(
    user_id: str = "default-dev",
    matched_pattern: Dict[str, str] = None,
    custom_header_present: bool = False,
    is_default: bool = True,
) -> Dict[str, Any]:
    """
    Create a mock memory routing info response.

    Args:
        user_id: Detected user ID
        matched_pattern: Pattern that matched (if any)
        custom_header_present: Whether custom header was present
        is_default: Whether default user ID was used

    Returns:
        Mock routing info response
    """
    return {
        "routing": {
            "user_id": user_id,
            "matched_pattern": matched_pattern,
            "custom_header_present": custom_header_present,
            "is_default": is_default,
        },
        "request_headers": {},
        "session_info": {
            "initialized": True,
            "client_id": 12345678,
            "cookie_count": 0,
            "cookie_names": [],
            "injected_into_litellm": True,
        },
    }


# =============================================================================
# Mock HTTP Responses
# =============================================================================


class MockHTTPResponse:
    """Mock httpx.Response for testing."""

    def __init__(
        self,
        status_code: int,
        json_data: Dict[str, Any] = None,
        text: Optional[str] = None,
        headers: Dict[str, str] = None,
    ):
        self.status_code = status_code
        self._json_data = json_data
        self._text = text
        self.headers = headers or {}

    def json(self) -> Dict[str, Any]:
        """Return JSON data."""
        return self._json_data or {}

    @property
    def text(self) -> str:
        """Return text content."""
        return self._text or ""

    def raise_for_status(self):
        """Raise exception for error status codes."""
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")


# =============================================================================
# Mock LiteLLM Response Objects
# =============================================================================


class MockLiteLLMResponse:
    """Mock litellm.ModelResponse for testing."""

    def __init__(self, response_dict: Dict[str, Any]):
        self._data = response_dict

    def model_dump(self) -> Dict[str, Any]:
        """Pydantic v2 compatibility."""
        return self._data

    def dict(self) -> Dict[str, Any]:
        """Pydantic v1 compatibility."""
        return self._data

    def __getattr__(self, name):
        """Dynamic attribute access."""
        return self._data.get(name)


class MockStreamingChunk:
    """Mock streaming chunk object."""

    def __init__(self, chunk_dict: Dict[str, Any]):
        self._data = chunk_dict
        self.choices = []

        # Parse choices
        if "choices" in chunk_dict:
            for choice_data in chunk_dict["choices"]:
                self.choices.append(MockChoice(choice_data))

        # Additional attributes required by CustomStreamWrapper
        self.id = chunk_dict.get("id", "chatcmpl-test-123")
        self.object = chunk_dict.get("object", "chat.completion.chunk")
        self.created = chunk_dict.get("created", 1234567890)
        self.model = chunk_dict.get("model", "claude-sonnet-4.5")
        self.system_fingerprint = chunk_dict.get("system_fingerprint")
        self.usage = chunk_dict.get("usage")

    def model_dump(self) -> Dict[str, Any]:
        """Pydantic v2 compatibility."""
        return self._data

    def dict(self) -> Dict[str, Any]:
        """Pydantic v1 compatibility."""
        return self._data


class MockChoice:
    """Mock choice object in streaming chunk."""

    def __init__(self, choice_data: Dict[str, Any]):
        self.index = choice_data.get("index", 0)
        self.delta = MockDelta(choice_data.get("delta", {}))
        self.finish_reason = choice_data.get("finish_reason")
        # Additional attributes for compatibility
        self.logprobs = choice_data.get("logprobs")


class MockDelta:
    """Mock delta object in streaming chunk."""

    def __init__(self, delta_data: Dict[str, Any]):
        self.content = delta_data.get("content")
        self.role = delta_data.get("role")
        # Additional attributes required by CustomStreamWrapper
        self.function_call = delta_data.get("function_call")
        self.tool_calls = delta_data.get("tool_calls")


# =============================================================================
# Helper Functions
# =============================================================================


def create_mock_streaming_iterator(chunks: List[Dict[str, Any]]):
    """
    Create a CustomStreamWrapper-compatible mock for streaming chunks.

    This function creates a real CustomStreamWrapper instance with properly formatted
    litellm streaming objects, ensuring compatibility with CustomStreamWrapper's
    internal processing logic.

    Args:
        chunks: List of chunk dictionaries in OpenAI streaming format

    Returns:
        CustomStreamWrapper instance wrapping an async iterator yielding proper chunk objects
    """
    from litellm.litellm_core_utils.streaming_handler import CustomStreamWrapper
    from litellm.utils import StreamingChoices, Delta, ModelResponse
    from unittest.mock import Mock

    async def mock_iterator():
        """Inner async generator that yields properly formatted chunks."""
        for chunk_data in chunks:
            # Create proper litellm streaming response object
            # Build choices list with proper Delta objects
            choices_list = []
            if "choices" in chunk_data:
                for choice_data in chunk_data["choices"]:
                    delta_data = choice_data.get("delta", {})
                    delta = Delta(
                        content=delta_data.get("content"),
                        role=delta_data.get("role"),
                        function_call=delta_data.get("function_call"),
                        tool_calls=delta_data.get("tool_calls"),
                    )
                    choice = StreamingChoices(
                        finish_reason=choice_data.get("finish_reason"),
                        index=choice_data.get("index", 0),
                        delta=delta,
                        logprobs=choice_data.get("logprobs"),
                    )
                    choices_list.append(choice)

            # Create a mock response object that has all required attributes
            # Use spec_set=[] to prevent auto-creation of Mock attributes
            mock_chunk = Mock(spec_set=[
                "choices", "id", "object", "created", "model",
                "system_fingerprint", "usage", "provider_specific_fields",
                "citations", "model_dump", "dict", "_hidden_params"
            ])
            mock_chunk.choices = choices_list
            mock_chunk.id = chunk_data.get("id", "chatcmpl-test-123")
            mock_chunk.object = chunk_data.get("object", "chat.completion.chunk")
            mock_chunk.created = chunk_data.get("created", 1234567890)
            mock_chunk.model = chunk_data.get("model", "test-model")
            mock_chunk.system_fingerprint = chunk_data.get("system_fingerprint")
            mock_chunk.usage = chunk_data.get("usage")
            # Provider-specific fields (must be None or dict, not Mock)
            mock_chunk.provider_specific_fields = None
            mock_chunk.citations = None
            mock_chunk._hidden_params = {}

            # Add model_dump() method for serialization
            def model_dump():
                result = {
                    "id": mock_chunk.id,
                    "object": mock_chunk.object,
                    "created": mock_chunk.created,
                    "model": mock_chunk.model,
                    "choices": [
                        {
                            "index": c.index,
                            "delta": {
                                "content": c.delta.content,
                                "role": c.delta.role,
                                "function_call": c.delta.function_call,
                                "tool_calls": c.delta.tool_calls,
                            },
                            "finish_reason": c.finish_reason,
                            "logprobs": c.logprobs,
                        }
                        for c in mock_chunk.choices
                    ],
                }
                if mock_chunk.system_fingerprint:
                    result["system_fingerprint"] = mock_chunk.system_fingerprint
                if mock_chunk.usage:
                    result["usage"] = mock_chunk.usage
                return result

            mock_chunk.model_dump = model_dump
            mock_chunk.dict = model_dump  # Pydantic v1 compatibility

            yield mock_chunk

    # Create a minimal mock logging object with proper async methods
    mock_logging_obj = Mock()
    mock_logging_obj.model_call_details = {
        "litellm_params": {},
        "model": "test-model",
    }

    # Make async_failure_handler a proper async function
    async def async_failure_handler(*_args, **_kwargs):
        """Mock async failure handler."""
        pass

    mock_logging_obj.async_failure_handler = async_failure_handler
    mock_logging_obj.async_success_handler = async_failure_handler  # Reuse for success

    # Use the real CustomStreamWrapper class to ensure isinstance checks pass
    return CustomStreamWrapper(
        completion_stream=mock_iterator(),
        model="test-model",
        custom_llm_provider="openai",
        logging_obj=mock_logging_obj,
    )


# =============================================================================
# Test Data Collections
# =============================================================================

TEST_MODELS = {
    "claude-sonnet-4.5": {
        "litellm_model": "anthropic/claude-sonnet-4-5-20250929",
        "api_base": "https://api.supermemory.ai/v3/api.anthropic.com",
        "provider": "anthropic",
    },
    "gpt-4": {
        "litellm_model": "openai/gpt-4",
        "api_base": None,
        "provider": "openai",
    },
    "gpt-5-pro": {
        "litellm_model": "openai/gpt-5-pro",
        "api_base": None,
        "provider": "openai",
    },
}

TEST_MESSAGES = [
    [{"role": "user", "content": "Hello!"}],
    [
        {"role": "user", "content": "What is the weather?"},
        {"role": "assistant", "content": "I cannot check weather."},
        {"role": "user", "content": "Okay, thanks anyway."},
    ],
    [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Tell me a joke."},
    ],
]

TEST_USER_AGENTS = {
    "pycharm": "OpenAIClientImpl/Java 1.0",
    "claude_code": "Claude Code CLI/1.0",
    "anthropic_sdk": "anthropic-sdk-python/0.5.0",
    "curl": "curl/7.68.0",
}
