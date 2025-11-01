"""
Mock responses for testing LiteLLM SDK integration.

Provides realistic mock responses for:
- LiteLLM completion responses (streaming and non-streaming)
- LiteLLM exceptions
- HTTP responses from providers
"""

from typing import Dict, Any, List


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
        text: str = None,
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


class MockDelta:
    """Mock delta object in streaming chunk."""

    def __init__(self, delta_data: Dict[str, Any]):
        self.content = delta_data.get("content")
        self.role = delta_data.get("role")


# =============================================================================
# Helper Functions
# =============================================================================


def create_mock_streaming_iterator(chunks: List[Dict[str, Any]]):
    """
    Create an async iterator for mock streaming chunks.

    Args:
        chunks: List of chunk dictionaries

    Returns:
        Async iterator yielding MockStreamingChunk objects
    """

    async def mock_iterator():
        for chunk in chunks:
            yield MockStreamingChunk(chunk)

    return mock_iterator()


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
