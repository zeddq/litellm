"""
Test data and configuration fixtures for SDK migration tests.

Provides test configurations, sample data, and utility functions.
"""

from typing import Dict, Any


# =============================================================================
# Test Configuration Files
# =============================================================================

TEST_CONFIG_YAML = """
general_settings:
  master_key: sk-test-1234
  forward_openai_org_id: true
  forward_client_headers_to_llm_api: true

user_id_mappings:
  custom_header: "x-memory-user-id"
  header_patterns:
    - header: "user-agent"
      pattern: "^OpenAIClientImpl/Java"
      user_id: "pycharm-ai"
    - header: "user-agent"
      pattern: "^Claude Code"
      user_id: "claude-code"
    - header: "user-agent"
      pattern: "^anthropic-sdk-python"
      user_id: "anthropic-python"
  default_user_id: "default-dev"

model_list:
  - model_name: claude-sonnet-4.5
    litellm_params:
      api_base: https://api.supermemory.ai/v3/api.anthropic.com
      model: anthropic/claude-sonnet-4-5-20250929
      api_key: os.environ/ANTHROPIC_API_KEY
      custom_llm_provider: anthropic
      extra_headers:
        x-supermemory-api-key: os.environ/SUPERMEMORY_API_KEY

  - model_name: gpt-4
    litellm_params:
      model: openai/gpt-4
      api_key: os.environ/OPENAI_API_KEY

  - model_name: gpt-5-pro
    litellm_params:
      model: openai/gpt-5-pro
      api_key: os.environ/OPENAI_API_KEY

litellm_settings:
  set_verbose: true
  json_logs: true
  drop_params: true
  use_client_cache: true
"""

TEST_CONFIG_MINIMAL = """
general_settings:
  master_key: sk-test-minimal

model_list:
  - model_name: test-model
    litellm_params:
      model: openai/gpt-4
      api_key: sk-fake-key
"""

TEST_INVALID_API_KEY="321"

# =============================================================================
# Sample Request Bodies
# =============================================================================


def get_chat_completion_request(
    model: str = "claude-sonnet-4.5",
    messages: list = None,
    stream: bool = False,
    **kwargs,
) -> Dict[str, Any]:
    """
    Create a chat completion request body.

    Args:
        model: Model name
        messages: List of message dicts
        stream: Whether to stream
        **kwargs: Additional parameters

    Returns:
        Request body dictionary
    """
    if messages is None:
        messages = [{"role": "user", "content": "Hello!"}]

    request_body = {
        "model": model,
        "messages": messages,
        "stream": stream,
    }

    request_body.update(kwargs)
    return request_body


# =============================================================================
# Sample Headers
# =============================================================================


def get_request_headers(
    api_key: str = "sk-test-1234",
    user_agent: str = "test-client/1.0",
    custom_user_id: str = None,
    **extra_headers,
) -> Dict[str, str]:
    """
    Create request headers.

    Args:
        api_key: API key for Authorization header
        user_agent: User-Agent header
        custom_user_id: Optional custom user ID header
        **extra_headers: Additional headers

    Returns:
        Headers dictionary
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": user_agent,
    }

    if custom_user_id:
        headers["x-memory-user-id"] = custom_user_id

    headers.update(extra_headers)
    return headers


# =============================================================================
# Test Scenarios
# =============================================================================

TEST_SCENARIOS = {
    "simple_completion": {
        "request": get_chat_completion_request(
            model="claude-sonnet-4.5",
            messages=[{"role": "user", "content": "Hello!"}],
        ),
        "headers": get_request_headers(user_agent="test-client/1.0"),
        "expected_user_id": "default-dev",
    },
    "pycharm_client": {
        "request": get_chat_completion_request(
            model="claude-sonnet-4.5",
            messages=[{"role": "user", "content": "Write a function"}],
        ),
        "headers": get_request_headers(user_agent="OpenAIClientImpl/Java 1.0"),
        "expected_user_id": "pycharm-ai",
    },
    "claude_code_client": {
        "request": get_chat_completion_request(
            model="gpt-4",
            messages=[{"role": "user", "content": "Help me debug"}],
        ),
        "headers": get_request_headers(user_agent="Claude Code CLI/1.0"),
        "expected_user_id": "claude-code",
    },
    "custom_user_id": {
        "request": get_chat_completion_request(
            model="gpt-5-pro",
            messages=[{"role": "user", "content": "Custom user test"}],
        ),
        "headers": get_request_headers(
            user_agent="test-client/1.0", custom_user_id="project-alpha"
        ),
        "expected_user_id": "project-alpha",
    },
    "streaming_completion": {
        "request": get_chat_completion_request(
            model="claude-sonnet-4.5",
            messages=[{"role": "user", "content": "Stream test"}],
            stream=True,
        ),
        "headers": get_request_headers(user_agent="test-client/1.0"),
        "expected_user_id": "default-dev",
    },
    "max_tokens": {
        "request": get_chat_completion_request(
            model="claude-sonnet-4.5",
            messages=[{"role": "user", "content": "Short response please"}],
            max_tokens=50,
        ),
        "headers": get_request_headers(),
        "expected_user_id": "default-dev",
    },
    "temperature": {
        "request": get_chat_completion_request(
            model="gpt-4",
            messages=[{"role": "user", "content": "Creative story"}],
            temperature=0.9,
        ),
        "headers": get_request_headers(),
        "expected_user_id": "default-dev",
    },
}

# =============================================================================
# Error Test Cases
# =============================================================================

ERROR_TEST_CASES = {
    "missing_model": {
        "request": {"messages": [{"role": "user", "content": "Hello"}]},
        "expected_status": 400,
        "expected_error": "Missing required parameter: model",
    },
    "missing_messages": {
        "request": {"model": "claude-sonnet-4.5"},
        "expected_status": 400,
        "expected_error": "Missing required parameter: messages",
    },
    "invalid_model": {
        "request": get_chat_completion_request(model="nonexistent-model"),
        "expected_status": 404,
        "expected_error": "not found",
    },
    "invalid_api_key": {
        "request": get_chat_completion_request(),
        "headers": get_request_headers(api_key="sk-invalid"),
        "expected_status": 401,
        "expected_error": "Invalid API key",
    },
    "missing_auth_header": {
        "request": get_chat_completion_request(),
        "headers": {"Content-Type": "application/json"},
        "expected_status": 401,
        "expected_error": "Missing or invalid Authorization header",
    },
    "malformed_json": {
        "request_body": "{invalid json",
        "expected_status": 400,
        "expected_error": "Invalid JSON",
    },
}

# =============================================================================
# Performance Test Data
# =============================================================================

PERFORMANCE_TESTS = {
    "small_request": {
        "messages": [{"role": "user", "content": "Hi"}],
        "expected_max_latency_ms": 100,  # Local processing only
    },
    "medium_request": {
        "messages": [
            {"role": "user", "content": "Tell me a story about " + "x" * 100}
        ],
        "expected_max_latency_ms": 200,
    },
    "large_context": {
        "messages": [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Context " + "x" * 1000},
            {"role": "assistant", "content": "Response " + "y" * 500},
            {"role": "user", "content": "More " + "z" * 500},
        ],
        "expected_max_latency_ms": 500,
    },
}

# =============================================================================
# Concurrent Test Scenarios
# =============================================================================

CONCURRENT_TEST_CONFIG = {
    "light_load": {
        "num_requests": 10,
        "concurrent": 5,
        "expected_success_rate": 1.0,
    },
    "medium_load": {
        "num_requests": 50,
        "concurrent": 20,
        "expected_success_rate": 0.95,
    },
    "heavy_load": {
        "num_requests": 100,
        "concurrent": 50,
        "expected_success_rate": 0.90,
    },
}

# =============================================================================
# Environment Variables for Testing
# =============================================================================

TEST_ENV_VARS = {
    "ANTHROPIC_API_KEY": "sk-ant-test-key-12345",
    "OPENAI_API_KEY": "sk-test-openai-key-67890",
    "SUPERMEMORY_API_KEY": "sm_test_key_abcdef",
    "LITELLM_CONFIG_PATH": "tests/fixtures/test_config.yaml",
}

# =============================================================================
# Mock Cookie Data (Cloudflare)
# =============================================================================

CLOUDFLARE_TEST_COOKIES = {
    "cf_clearance": "test_clearance_token_12345",
    "__cfruid": "test_cf_ruid_67890",
    "__cf_bm": "test_cf_bm_token",
}

# =============================================================================
# Helper Functions
# =============================================================================


def create_test_config_file(tmp_path, config_content: str = TEST_CONFIG_YAML) -> str:
    """
    Create a temporary config file for testing.

    Args:
        tmp_path: pytest tmp_path fixture
        config_content: YAML content string

    Returns:
        Path to created config file
    """
    config_file = tmp_path / "test_config.yaml"
    config_file.write_text(config_content)
    return str(config_file)


def get_expected_litellm_params(model_name: str) -> Dict[str, Any]:
    """
    Get expected LiteLLM parameters for a model.

    Args:
        model_name: Model name

    Returns:
        Expected parameters dictionary
    """
    params_map = {
        "claude-sonnet-4.5": {
            "model": "anthropic/claude-sonnet-4-5-20250929",
            "api_base": "https://api.supermemory.ai/v3/api.anthropic.com",
            "custom_llm_provider": "anthropic",
        },
        "gpt-4": {
            "model": "openai/gpt-4",
        },
        "gpt-5-pro": {
            "model": "openai/gpt-5-pro",
        },
    }

    return params_map.get(model_name, {})


def assert_response_format(response_data: Dict[str, Any], streaming: bool = False):
    """
    Assert response has correct OpenAI format.

    Args:
        response_data: Response data to validate
        streaming: Whether it's a streaming response

    Raises:
        AssertionError: If format is incorrect
    """
    if streaming:
        assert "id" in response_data
        assert "object" in response_data
        assert response_data["object"] == "chat.completion.chunk"
        assert "choices" in response_data
    else:
        assert "id" in response_data
        assert "object" in response_data
        assert response_data["object"] == "chat.completion"
        assert "choices" in response_data
        assert "usage" in response_data


def assert_error_format(error_data: Dict[str, Any]):
    """
    Assert error response has correct format.

    Args:
        error_data: Error response to validate

    Raises:
        AssertionError: If format is incorrect
    """
    
    assert "error" in error_data
    error = error_data["error"]
    assert "message" in error
    assert "type" in error
    # code is optional but common
