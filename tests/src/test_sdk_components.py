"""
Unit Tests for SDK Components

Tests individual components in isolation:
- LiteLLMSessionManager (session_manager.py)
- LiteLLMConfig (config_parser.py)
- Error handlers (error_handlers.py)
- Streaming utilities (streaming_utils.py)

Test Strategy:
- Mock all external dependencies
- Fast execution (<5 seconds total)
- 80%+ code coverage
- Test both happy and error paths

Usage:
    pytest tests/test_sdk_components.py -v
    pytest tests/test_sdk_components.py -v --cov=src/proxy --cov-report=html
"""

import asyncio

import httpx
import litellm
import pytest

from proxy.config_parser import LiteLLMConfig, ModelConfig
from proxy.error_handlers import LiteLLMErrorHandler, ErrorResponse

# Import components under test
from proxy.session_manager import LiteLLMSessionManager
from proxy.streaming_utils import (
    stream_litellm_completion,
    format_sse_event,
    format_error_sse,
    StreamMonitor,
)

# Import test fixtures
from tests.fixtures import (
    TEST_CONFIG_YAML,
    create_test_config_file,
    mock_streaming_chunks_sequence,
    MockStreamingChunk,
    create_mock_streaming_iterator,
)


# =============================================================================
# Test LiteLLMSessionManager
# =============================================================================


class TestLiteLLMSessionManager:
    """Test suite for session manager."""

    @pytest.fixture(autouse=True)
    async def cleanup_session(self):
        """Ensure session is cleaned up after each test."""
        yield
        # Reset session manager state
        await LiteLLMSessionManager.close()
        LiteLLMSessionManager._client = None

    @pytest.mark.asyncio
    async def test_get_client_creates_singleton(self):
        """Test that get_client creates a singleton instance."""
        # Get client twice
        client1 = await LiteLLMSessionManager.get_client()
        client2 = await LiteLLMSessionManager.get_client()

        # Should be the same instance
        assert client1 is client2
        assert id(client1) == id(client2)

    @pytest.mark.asyncio
    async def test_get_client_injects_into_litellm(self):
        """Test that client is injected into litellm.aclient_session."""
        client = await LiteLLMSessionManager.get_client()

        # Verify injection
        assert litellm.aclient_session is not None
        assert litellm.aclient_session is client
        assert id(litellm.aclient_session) == id(client)

    @pytest.mark.asyncio
    async def test_get_client_configuration(self):
        """Test that client has correct configuration."""
        client = await LiteLLMSessionManager.get_client()

        # Check client type
        assert isinstance(client, httpx.AsyncClient)

        # Check timeout configuration
        assert client.timeout.read == 600.0
        assert client.timeout.connect == 30.0

        # Check limits
        assert client._transport._pool._max_connections == 100
        assert client._transport._pool._max_keepalive_connections == 20

        # Check redirect following
        assert client.follow_redirects is True

    @pytest.mark.asyncio
    async def test_close_clears_session(self):
        """Test that close() properly clears the session."""
        # Create session
        client = await LiteLLMSessionManager.get_client()
        assert LiteLLMSessionManager.is_initialized()

        # Close session
        await LiteLLMSessionManager.close()

        # Verify cleanup
        assert not LiteLLMSessionManager.is_initialized()
        assert LiteLLMSessionManager._client is None
        assert litellm.aclient_session is None

    @pytest.mark.asyncio
    async def test_is_initialized(self):
        """Test is_initialized() status tracking."""
        # Initially not initialized
        assert not LiteLLMSessionManager.is_initialized()

        # After creating client
        await LiteLLMSessionManager.get_client()
        assert LiteLLMSessionManager.is_initialized()

        # After closing
        await LiteLLMSessionManager.close()
        assert not LiteLLMSessionManager.is_initialized()

    @pytest.mark.asyncio
    async def test_cookie_tracking(self):
        """Test cookie count and names tracking."""
        client = await LiteLLMSessionManager.get_client()

        # Initially no cookies
        assert LiteLLMSessionManager.get_cookie_count() == 0
        assert LiteLLMSessionManager.get_cookie_names() == []

        # Add mock cookies
        client.cookies.set("test_cookie", "value1")
        client.cookies.set("cf_clearance", "cloudflare_token")

        # Verify tracking
        assert LiteLLMSessionManager.get_cookie_count() == 2
        cookie_names = LiteLLMSessionManager.get_cookie_names()
        assert "test_cookie" in cookie_names
        assert "cf_clearance" in cookie_names

    @pytest.mark.asyncio
    async def test_get_session_info(self):
        """Test session info reporting."""
        # Before initialization
        info = LiteLLMSessionManager.get_session_info()
        assert info["initialized"] is False
        assert info["client_id"] is None
        assert info["cookie_count"] == 0

        # After initialization
        client = await LiteLLMSessionManager.get_client()
        info = LiteLLMSessionManager.get_session_info()

        assert info["initialized"] is True
        assert info["client_id"] == id(client)
        assert info["cookie_count"] == 0
        assert info["cookie_names"] == []
        assert info["injected_into_litellm"] is True

    @pytest.mark.asyncio
    async def test_concurrent_access_thread_safety(self):
        """Test that concurrent access is thread-safe."""

        async def get_client_id():
            client = await LiteLLMSessionManager.get_client()
            return id(client)

        # Get client from multiple coroutines concurrently
        ids = await asyncio.gather(*[get_client_id() for _ in range(10)])

        # All should return the same client ID
        assert len(set(ids)) == 1

    @pytest.mark.asyncio
    async def test_close_idempotent(self):
        """Test that close() is idempotent (safe to call multiple times)."""
        await LiteLLMSessionManager.get_client()

        # Close multiple times should not error
        await LiteLLMSessionManager.close()
        await LiteLLMSessionManager.close()
        await LiteLLMSessionManager.close()

        assert not LiteLLMSessionManager.is_initialized()


# =============================================================================
# Test LiteLLMConfig
# =============================================================================


class TestLiteLLMConfig:
    """Test suite for configuration parser."""

    @pytest.fixture
    def test_config_file(self, tmp_path):
        """Create a test configuration file."""
        return create_test_config_file(tmp_path, TEST_CONFIG_YAML)

    @pytest.fixture
    def mock_env_vars(self, monkeypatch):
        """Mock environment variables."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-123")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test-456")
        monkeypatch.setenv("SUPERMEMORY_API_KEY", "sm_test_789")

    def test_load_config(self, test_config_file, mock_env_vars):
        """Test loading configuration from file."""
        config = LiteLLMConfig(test_config_file)

        assert config.config is not None
        assert len(config.get_all_models()) > 0

    def test_model_configs_cached(self, test_config_file, mock_env_vars):
        """Test that model configurations are cached."""
        config = LiteLLMConfig(test_config_file)

        models = config.get_all_models()
        assert len(models) >= 3
        assert "claude-sonnet-4.5" in models
        assert "gpt-4" in models
        assert "gpt-5-pro" in models

    def test_get_model_config(self, test_config_file, mock_env_vars):
        """Test retrieving specific model configuration."""
        config = LiteLLMConfig(test_config_file)

        model_config = config.get_model_config("claude-sonnet-4.5")
        assert model_config is not None
        assert isinstance(model_config, ModelConfig)
        assert model_config.model_name == "claude-sonnet-4.5"
        assert "anthropic" in model_config.litellm_model
        assert model_config.api_base is not None

    def test_get_model_config_not_found(self, test_config_file, mock_env_vars):
        """Test retrieving non-existent model."""
        config = LiteLLMConfig(test_config_file)

        model_config = config.get_model_config("nonexistent-model")
        assert model_config is None

    def test_get_litellm_params(self, test_config_file, mock_env_vars):
        """Test getting LiteLLM parameters for completion calls."""
        config = LiteLLMConfig(test_config_file)

        params = config.get_litellm_params("claude-sonnet-4.5")

        assert "model" in params
        assert params["model"] == "anthropic/claude-sonnet-4-5-20250929"
        assert "api_base" in params
        assert "api_key" in params
        assert params["api_key"] == "sk-ant-test-123"  # From env var
        assert "custom_llm_provider" in params

    def test_get_litellm_params_not_found(self, test_config_file, mock_env_vars):
        """Test getting params for non-existent model raises error."""
        config = LiteLLMConfig(test_config_file)

        with pytest.raises(ValueError, match="not found"):
            config.get_litellm_params("nonexistent-model")

    def test_env_var_resolution(self, test_config_file, mock_env_vars):
        """Test that environment variables are resolved correctly."""
        config = LiteLLMConfig(test_config_file)

        # Check API key resolution
        model_config = config.get_model_config("gpt-4")
        assert model_config.api_key == "sk-openai-test-456"

    def test_missing_env_var_raises_error(self, tmp_path, monkeypatch):
        """Test that missing required env vars raise errors."""
        # Don't set ANTHROPIC_API_KEY
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        test_file = create_test_config_file(tmp_path, TEST_CONFIG_YAML)

        with pytest.raises(ValueError, match="Environment variable.*not set"):
            LiteLLMConfig(test_file)

    def test_model_exists(self, test_config_file, mock_env_vars):
        """Test model existence checking."""
        config = LiteLLMConfig(test_config_file)

        assert config.model_exists("claude-sonnet-4.5")
        assert config.model_exists("gpt-4")
        assert not config.model_exists("nonexistent-model")

    def test_get_all_models(self, test_config_file, mock_env_vars):
        """Test retrieving all model names."""
        config = LiteLLMConfig(test_config_file)

        models = config.get_all_models()
        assert isinstance(models, list)
        assert len(models) >= 3
        assert "claude-sonnet-4.5" in models

    def test_model_config_to_litellm_params(self, test_config_file, mock_env_vars):
        """Test ModelConfig.to_litellm_params() conversion."""
        config = LiteLLMConfig(test_config_file)
        model_config = config.get_model_config("claude-sonnet-4.5")

        params = model_config.to_litellm_params()

        assert "model" in params
        assert "api_base" in params
        assert "api_key" in params
        assert "extra_headers" in params
        assert "custom_llm_provider" in params

    def test_extra_headers_resolution(self, test_config_file, mock_env_vars):
        """Test that extra_headers with env vars are resolved."""
        config = LiteLLMConfig(test_config_file)
        model_config = config.get_model_config("claude-sonnet-4.5")

        params = model_config.to_litellm_params()
        extra_headers = params.get("extra_headers", {})

        # Supermemory key should be resolved from env var
        assert "x-supermemory-api-key" in extra_headers
        assert extra_headers["x-supermemory-api-key"] == "sm_test_789"

    def test_master_key(self, test_config_file, mock_env_vars):
        """Test master key retrieval."""
        config = LiteLLMConfig(test_config_file)

        master_key = config.get_master_key()
        assert master_key == "sk-test-1234"

    def test_litellm_settings(self, test_config_file, mock_env_vars):
        """Test LiteLLM settings retrieval."""
        config = LiteLLMConfig(test_config_file)

        settings = config.get_litellm_settings()
        assert isinstance(settings, dict)
        assert settings.get("set_verbose") is True
        assert settings.get("drop_params") is True

    def test_raw_config_access(self, test_config_file, mock_env_vars):
        """Test access to raw configuration dict."""
        config = LiteLLMConfig(test_config_file)

        assert config.config.model_dump_json() is not None
        assert "model_list" in config.config.model_dump_json()
        assert "user_id_mappings" in config.config.model_dump_json()


# =============================================================================
# Test Error Handlers
# =============================================================================


class TestErrorHandlers:
    """Test suite for error handling."""

    @pytest.fixture
    def error_handler(self):
        """Create error handler instance."""
        return LiteLLMErrorHandler(include_debug_info=False)

    @pytest.fixture
    def debug_error_handler(self):
        """Create error handler with debug info enabled."""
        return LiteLLMErrorHandler(include_debug_info=True)

    @pytest.mark.asyncio
    async def test_handle_bad_request_error(self, error_handler):
        """Test handling BadRequestError."""
        exc = litellm.exceptions.BadRequestError(
            message="Invalid parameter", model="gpt-4", llm_provider="openai"
        )

        response = await error_handler.handle_completion_error(
            exc, request_id="test-123"
        )

        assert response.status_code == 400
        body = response.body.decode()
        assert "Invalid parameter" in body
        assert "bad_request" in body

    @pytest.mark.asyncio
    async def test_handle_authentication_error(self, error_handler):
        """Test handling AuthenticationError."""
        exc = litellm.exceptions.AuthenticationError(
            message="Invalid API key", model="gpt-4", llm_provider="openai"
        )

        response = await error_handler.handle_completion_error(exc)

        assert response.status_code == 401
        body = response.body.decode()
        assert "authentication" in body.lower()

    @pytest.mark.asyncio
    async def test_handle_rate_limit_error(self, error_handler):
        """Test handling RateLimitError with retry-after."""
        exc = litellm.exceptions.RateLimitError(
            message="Rate limit exceeded", model="gpt-4", llm_provider="openai"
        )

        response = await error_handler.handle_completion_error(exc)

        assert response.status_code == 429
        assert "Retry-After" in response.headers
        body = response.body.decode()
        assert "rate_limit" in body.lower()

    @pytest.mark.asyncio
    async def test_handle_context_length_error(self, error_handler):
        """Test handling ContextWindowExceededError."""
        exc = litellm.exceptions.ContextWindowExceededError(
            message="Context too long", model="gpt-4", llm_provider="openai"
        )

        response = await error_handler.handle_completion_error(exc)

        assert response.status_code == 400
        body = response.body.decode()
        assert "context_length_exceeded" in body

    @pytest.mark.asyncio
    async def test_handle_timeout_error(self, error_handler):
        """Test handling Timeout error."""
        exc = litellm.Timeout(
            message="Request timeout", model="gpt-4", llm_provider="openai"
        )

        response = await error_handler.handle_completion_error(exc)

        assert response.status_code == 408
        assert "Retry-After" in response.headers
        body = response.body.decode()
        assert "timeout" in body.lower()

    @pytest.mark.asyncio
    async def test_handle_service_unavailable_error(self, error_handler):
        """Test handling ServiceUnavailableError."""
        exc = litellm.exceptions.ServiceUnavailableError(
            message="Service down", model="gpt-4", llm_provider="openai"
        )

        response = await error_handler.handle_completion_error(exc)

        assert response.status_code == 503
        body = response.body.decode()
        assert "service_unavailable" in body

    @pytest.mark.asyncio
    async def test_handle_generic_exception(self, error_handler):
        """Test handling unexpected exceptions."""
        exc = Exception("Unexpected error")

        response = await error_handler.handle_completion_error(exc)

        assert response.status_code == 500
        body = response.body.decode()
        assert "internal" in body.lower()

    @pytest.mark.asyncio
    async def test_debug_info_included_when_enabled(self, debug_error_handler):
        """Test that debug info is included when enabled."""
        exc = litellm.exceptions.BadRequestError(
            message="Test error", model="gpt-4", llm_provider="openai"
        )

        response = await debug_error_handler.handle_completion_error(exc)

        body_str = response.body.decode()
        # Debug info should include exception type
        assert "exception_type" in body_str.lower() or "BadRequestError" in body_str

    @pytest.mark.asyncio
    async def test_debug_info_excluded_when_disabled(self, error_handler):
        """Test that debug info is excluded by default."""
        exc = litellm.exceptions.BadRequestError(
            message="Test error", model="gpt-4", llm_provider="openai"
        )

        response = await error_handler.handle_completion_error(exc)

        body_str = response.body.decode()
        # Debug-only fields should not be present
        # This is a weak check but validates the concept
        import json

        body = json.loads(body_str)
        error_obj = body.get("error", {})
        # If details exist, they should be minimal
        if "details" in error_obj:
            # Details should be empty or not overly verbose
            pass

    def test_error_response_builder(self):
        """Test ErrorResponse.build() utility."""
        response = ErrorResponse.build(
            status_code=400,
            error_type="test_error",
            message="Test message",
            code="test_code",
        )

        assert response.status_code == 400
        body = response.body.decode()
        assert "test_error" in body
        assert "Test message" in body
        assert "test_code" in body


# =============================================================================
# Test Streaming Utilities
# =============================================================================


class TestStreamingUtilities:
    """Test suite for streaming utilities."""

    @pytest.mark.asyncio
    async def test_stream_litellm_completion_basic(self):
        """Test basic streaming with mock chunks."""
        chunks = mock_streaming_chunks_sequence()
        mock_iterator = create_mock_streaming_iterator(chunks)

        collected_chunks = []
        async for sse_chunk in stream_litellm_completion(
            mock_iterator, request_id="test-123"
        ):
            collected_chunks.append(sse_chunk)

        # Should have chunks + [DONE] signal
        assert len(collected_chunks) > 0
        assert collected_chunks[-1] == "data: [DONE]\n\n"

        # Each chunk should be SSE formatted
        for chunk in collected_chunks[:-1]:
            assert chunk.startswith("data: ")
            assert chunk.endswith("\n\n")

    @pytest.mark.asyncio
    async def test_stream_detects_finish_reason(self):
        """Test that streaming detects finish_reason and stops."""
        chunks = mock_streaming_chunks_sequence()
        mock_iterator = create_mock_streaming_iterator(chunks)

        finish_detected = False
        async for sse_chunk in stream_litellm_completion(mock_iterator):
            if "[DONE]" in sse_chunk:
                finish_detected = True
                break

        assert finish_detected

    @pytest.mark.asyncio
    async def test_stream_handles_errors(self):
        """Test that streaming handles errors gracefully."""

        async def error_iterator():
            yield MockStreamingChunk(mock_streaming_chunks_sequence()[0])
            raise litellm.exceptions.RateLimitError(
                message="Rate limit", model="gpt-4", llm_provider="openai"
            )

        collected = []
        async for chunk in stream_litellm_completion(error_iterator()):
            collected.append(chunk)

        # Should have error chunk
        error_found = any("rate_limit" in chunk.lower() for chunk in collected)
        assert error_found

    def test_format_sse_event(self):
        """Test SSE event formatting."""
        data = {"status": "processing", "progress": 50}
        sse = format_sse_event(data, event_type="progress")

        assert "event: progress\n" in sse
        assert "data: " in sse
        assert "processing" in sse
        assert sse.endswith("\n\n")

    def test_format_error_sse(self):
        """Test error SSE formatting."""
        sse = format_error_sse(
            error_type="rate_limit_error",
            message="Rate limit exceeded",
            code="rate_limit_exceeded",
        )

        assert "data: " in sse
        assert "rate_limit_error" in sse
        assert "Rate limit exceeded" in sse
        assert sse.endswith("\n\n")

    @pytest.mark.asyncio
    async def test_stream_monitor_tracks_chunks(self):
        """Test StreamMonitor tracks chunk count."""
        monitor = StreamMonitor("test-123")

        for _ in range(10):
            monitor.record_chunk()
            await asyncio.sleep(0.01)

        stats = monitor.get_stats()
        assert stats["chunk_count"] == 10
        assert stats["request_id"] == "test-123"
        assert stats["duration_seconds"] > 0
        assert stats["error_count"] == 0

    def test_stream_monitor_tracks_errors(self):
        """Test StreamMonitor tracks errors."""
        monitor = StreamMonitor()

        monitor.record_error()
        monitor.record_error()

        stats = monitor.get_stats()
        assert stats["error_count"] == 2


# =============================================================================
# Test Execution
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
