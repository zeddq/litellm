"""
Comprehensive tests for context retrieval functionality.

Tests cover:
- ContextRetriever class methods
- Query extraction strategies
- Context injection strategies
- Configuration validation
- Integration with SDK proxy handler
- Error handling and graceful degradation
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import httpx

from proxy.context_retriever import (
    ContextRetriever,
    retrieve_and_inject_context,
    ContextRetrievalError,
    SupermemoryAPIError,
)
from proxy.config_parser import LiteLLMConfig
from proxy.litellm_proxy_sdk import should_use_context_retrieval, apply_context_retrieval


# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def sample_messages():
    """Sample chat messages for testing."""
    return [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "What is the capital of France?"},
        {"role": "assistant", "content": "The capital of France is Paris."},
        {"role": "user", "content": "Tell me more about it."},
    ]


@pytest.fixture
def sample_supermemory_response():
    """Sample Supermemory API response."""
    return {
        "results": [
            {
                "content": "Paris is the capital and largest city of France.",
                "url": "https://example.com/paris",
                "score": 0.95,
            },
            {
                "content": "Paris has a population of over 2 million people.",
                "url": "https://example.com/paris-population",
                "score": 0.87,
            },
        ]
    }


@pytest.fixture
def mock_http_client():
    """Mock httpx.AsyncClient for testing."""
    client = AsyncMock(spec=httpx.AsyncClient)
    client.cookies = MagicMock()
    return client


@pytest.fixture
def context_retriever(mock_http_client):
    """ContextRetriever instance with mocked HTTP client."""
    return ContextRetriever(
        api_key="test-api-key",
        base_url="https://api.supermemory.ai",
        http_client=mock_http_client,
        default_container_tag="test",
        max_context_length=4000,
        timeout=10.0,
    )


@pytest.fixture
def mock_config():
    """Mock LiteLLMConfig with context retrieval enabled."""
    config = MagicMock(spec=LiteLLMConfig)
    config.config = {
        "context_retrieval": {
            "enabled": True,
            "api_key": "os.environ/SUPERMEMORY_API_KEY",
            "base_url": "https://api.supermemory.ai",
            "query_strategy": "last_user",
            "injection_strategy": "system",
            "container_tag": "test",
            "max_context_length": 4000,
            "max_results": 5,
            "timeout": 10.0,
            "enabled_for_models": ["claude-sonnet-4.5"],
        }
    }
    return config


# ============================================================================
# Unit Tests - Query Extraction
# ============================================================================


class TestQueryExtraction:
    """Test query extraction strategies."""

    def test_last_user_strategy(self, sample_messages):
        """Test extracting query from last user message."""
        query = ContextRetriever.extract_query_from_messages(
            sample_messages, strategy="last_user"
        )
        assert query == "Tell me more about it."

    def test_first_user_strategy(self, sample_messages):
        """Test extracting query from first user message."""
        query = ContextRetriever.extract_query_from_messages(
            sample_messages, strategy="first_user"
        )
        assert query == "What is the capital of France?"

    def test_all_user_strategy(self, sample_messages):
        """Test extracting query from all user messages."""
        query = ContextRetriever.extract_query_from_messages(
            sample_messages, strategy="all_user"
        )
        expected = "What is the capital of France? | Tell me more about it."
        assert query == expected

    def test_last_assistant_strategy(self, sample_messages):
        """Test extracting query from last assistant message."""
        query = ContextRetriever.extract_query_from_messages(
            sample_messages, strategy="last_assistant"
        )
        assert query == "The capital of France is Paris."

    def test_invalid_strategy(self, sample_messages):
        """Test handling invalid strategy - returns empty string."""
        query = ContextRetriever.extract_query_from_messages(
            sample_messages, strategy="invalid"
        )
        # Invalid strategies return empty string (graceful handling)
        assert query == ""

    def test_no_user_messages(self):
        """Test handling messages with no user messages."""
        messages = [{"role": "system", "content": "System message"}]
        query = ContextRetriever.extract_query_from_messages(messages, strategy="last_user")
        assert query == ""

    def test_empty_messages(self):
        """Test handling empty message list."""
        query = ContextRetriever.extract_query_from_messages([], strategy="last_user")
        assert query == ""


# ============================================================================
# Unit Tests - Context Injection
# ============================================================================


class TestContextInjection:
    """Test context injection strategies."""

    def test_system_injection(self, sample_messages):
        """Test injecting context as system message."""
        context = "Paris is the capital of France."
        injected = ContextRetriever.inject_context_into_messages(
            sample_messages, context, injection_strategy="system"
        )

        # Should have one more message (the system context)
        assert len(injected) == len(sample_messages) + 1

        # First message should be the context system message
        assert injected[0]["role"] == "system"
        assert "relevant context from the user's memory" in injected[0]["content"]
        assert context in injected[0]["content"]

        # Original messages should follow
        assert injected[1:] == sample_messages

    def test_user_prefix_injection(self, sample_messages):
        """Test prepending context to first user message."""
        context = "Paris is the capital of France."
        injected = ContextRetriever.inject_context_into_messages(
            sample_messages, context, injection_strategy="user_prefix"
        )

        # Should have same number of messages
        assert len(injected) == len(sample_messages)

        # Find first user message
        first_user_idx = next(
            i for i, msg in enumerate(injected) if msg["role"] == "user"
        )

        # Should start with context (before the separator)
        assert context in injected[first_user_idx]["content"]
        assert "---" in injected[first_user_idx]["content"]
        # Context should come before the separator
        content_parts = injected[first_user_idx]["content"].split("---")
        assert context in content_parts[0]

    def test_user_suffix_injection(self, sample_messages):
        """Test appending context to last user message."""
        context = "Paris is the capital of France."
        injected = ContextRetriever.inject_context_into_messages(
            sample_messages, context, injection_strategy="user_suffix"
        )

        # Should have same number of messages
        assert len(injected) == len(sample_messages)

        # Find last user message
        last_user_idx = max(
            i for i, msg in enumerate(injected) if msg["role"] == "user"
        )

        # Should end with context (after the separator)
        assert context in injected[last_user_idx]["content"]
        assert "---" in injected[last_user_idx]["content"]
        # Context should come after the separator
        content_parts = injected[last_user_idx]["content"].split("---")
        assert context in content_parts[-1]

    def test_invalid_injection_strategy(self, sample_messages):
        """Test handling invalid injection strategy - returns unchanged."""
        injected = ContextRetriever.inject_context_into_messages(
            sample_messages, "context", injection_strategy="invalid"
        )
        # Invalid strategies return unchanged messages (graceful handling)
        assert injected == sample_messages

    def test_no_user_messages_prefix(self):
        """Test user_prefix with no user messages."""
        messages = [{"role": "system", "content": "System"}]
        injected = ContextRetriever.inject_context_into_messages(
            messages, "context", injection_strategy="user_prefix"
        )
        # Should return unchanged
        assert injected == messages


# ============================================================================
# Unit Tests - Context Formatting
# ============================================================================


class TestContextFormatting:
    """Test context formatting from API results."""

    def test_format_context_with_results(self, context_retriever, sample_supermemory_response):
        """Test formatting context from API results."""
        # _format_context takes a list, not a dict with 'results' key
        results = sample_supermemory_response["results"]
        context = context_retriever._format_context(results)

        assert "Paris is the capital and largest city of France" in context
        assert "Paris has a population of over 2 million people" in context

    def test_format_context_empty_results(self, context_retriever):
        """Test formatting with no results."""
        context = context_retriever._format_context([])
        assert context == ""

    def test_format_context_max_length(self, context_retriever):
        """Test context truncation to max length."""
        # Create very long context
        long_results = [
            {"content": "A" * 5000, "url": "http://example.com", "score": 0.9}
        ]

        context = context_retriever._format_context(long_results)
        assert len(context) <= context_retriever.max_context_length


# ============================================================================
# Unit Tests - API Interaction
# ============================================================================


class TestAPIInteraction:
    """Test Supermemory API interaction."""

    @pytest.mark.asyncio
    async def test_retrieve_context_success(
        self, context_retriever, mock_http_client, sample_supermemory_response
    ):
        """Test successful context retrieval."""
        # Mock successful API response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json = MagicMock(return_value=sample_supermemory_response)
        mock_http_client.post = AsyncMock(return_value=mock_response)

        result = await context_retriever.retrieve_context(
            query="Paris", user_id="test-user"
        )

        assert result["success"] is True
        assert "Paris is the capital" in result["formatted_context"]
        assert result["query"] == "Paris"
        assert result["user_id"] == "test-user"
        assert len(result["results"]) == 2

    @pytest.mark.asyncio
    async def test_retrieve_context_api_error(self, context_retriever, mock_http_client):
        """Test API error handling."""
        # Mock API error
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_http_client.post = AsyncMock(return_value=mock_response)

        # SupermemoryAPIError is caught and wrapped in ContextRetrievalError
        with pytest.raises(ContextRetrievalError, match="Unexpected error"):
            await context_retriever.retrieve_context(
                query="Paris", user_id="test-user"
            )

    @pytest.mark.asyncio
    async def test_retrieve_context_timeout(self, context_retriever, mock_http_client):
        """Test timeout handling."""
        # Mock timeout
        mock_http_client.post = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))

        with pytest.raises(ContextRetrievalError, match="Request timeout"):
            await context_retriever.retrieve_context(
                query="Paris", user_id="test-user"
            )

    @pytest.mark.asyncio
    async def test_retrieve_context_empty_query(self, context_retriever, mock_http_client):
        """Test handling empty query."""
        # Mock API response for empty query
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json = MagicMock(return_value={"results": []})
        mock_http_client.post = AsyncMock(return_value=mock_response)
        
        result = await context_retriever.retrieve_context(
            query="", user_id="test-user"
        )
        assert result["formatted_context"] == ""
        assert result["success"] is True


# ============================================================================
# Integration Tests - retrieve_and_inject_context
# ============================================================================


class TestRetrieveAndInject:
    """Test the high-level retrieve_and_inject_context function."""

    @pytest.mark.asyncio
    async def test_full_workflow(
        self, context_retriever, mock_http_client, sample_messages, sample_supermemory_response
    ):
        """Test complete retrieve and inject workflow."""
        # Mock API response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json = MagicMock(return_value=sample_supermemory_response)
        mock_http_client.post = AsyncMock(return_value=mock_response)

        enhanced_messages, metadata = await retrieve_and_inject_context(
            retriever=context_retriever,
            messages=sample_messages,
            user_id="test-user",
            query_strategy="last_user",
            injection_strategy="system",
        )

        # Should have one more message (system context)
        assert len(enhanced_messages) == len(sample_messages) + 1
        assert enhanced_messages[0]["role"] == "system"
        assert "Paris" in enhanced_messages[0]["content"]

        # Metadata should be populated
        assert metadata["success"] is True
        assert metadata["query"] == "Tell me more about it."

    @pytest.mark.asyncio
    async def test_error_returns_original_messages(
        self, context_retriever, mock_http_client, sample_messages
    ):
        """Test that errors return original messages."""
        # Mock API error
        mock_http_client.post.side_effect = Exception("API Error")

        enhanced_messages, metadata = await retrieve_and_inject_context(
            retriever=context_retriever,
            messages=sample_messages,
            user_id="test-user",
        )

        # Should return original messages
        assert enhanced_messages == sample_messages
        assert metadata is None


# ============================================================================
# Integration Tests - Proxy Handler
# ============================================================================


class TestProxyHandlerIntegration:
    """Test integration with SDK proxy handler."""

    def test_should_use_context_retrieval_enabled(self, mock_config):
        """Test context retrieval is enabled for whitelisted models."""
        result = should_use_context_retrieval("claude-sonnet-4.5", mock_config)
        assert result is True

    def test_should_use_context_retrieval_disabled_model(self, mock_config):
        """Test context retrieval is disabled for non-whitelisted models."""
        result = should_use_context_retrieval("gpt-4", mock_config)
        assert result is False

    def test_should_use_context_retrieval_globally_disabled(self, mock_config):
        """Test context retrieval when globally disabled."""
        mock_config.config["context_retrieval"]["enabled"] = False
        result = should_use_context_retrieval("claude-sonnet-4.5", mock_config)
        assert result is False

    def test_should_use_context_retrieval_no_filters(self, mock_config):
        """Test context retrieval with no model filters."""
        mock_config.config["context_retrieval"]["enabled_for_models"] = None
        mock_config.config["context_retrieval"]["disabled_for_models"] = None

        result = should_use_context_retrieval("any-model", mock_config)
        assert result is True

    def test_should_use_context_retrieval_blacklist(self, mock_config):
        """Test context retrieval with blacklist."""
        mock_config.config["context_retrieval"]["enabled_for_models"] = None
        mock_config.config["context_retrieval"]["disabled_for_models"] = ["gpt-4"]

        assert should_use_context_retrieval("claude-sonnet-4.5", mock_config) is True
        assert should_use_context_retrieval("gpt-4", mock_config) is False

    @pytest.mark.asyncio
    async def test_apply_context_retrieval_success(
        self, mock_config, sample_messages, mock_http_client, sample_supermemory_response
    ):
        """Test apply_context_retrieval function."""
        # Mock environment variable
        with patch.dict(os.environ, {"SUPERMEMORY_API_KEY": "test-key"}):
            # Mock session manager
            with patch("proxy.litellm_proxy_sdk.LiteLLMSessionManager.get_client") as mock_get_client:
                mock_get_client.return_value = mock_http_client

                # Mock API response
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json = MagicMock(return_value=sample_supermemory_response)
                mock_http_client.post = AsyncMock(return_value=mock_response)

                enhanced_messages = await apply_context_retrieval(
                    messages=sample_messages,
                    model_name="claude-sonnet-4.5",
                    user_id="test-user",
                    config=mock_config,
                )

                # Should have enhanced messages (one more system message)
                assert len(enhanced_messages) == len(sample_messages) + 1
                assert enhanced_messages[0]["role"] == "system"

    @pytest.mark.asyncio
    async def test_apply_context_retrieval_disabled(self, mock_config, sample_messages):
        """Test apply_context_retrieval when disabled."""
        mock_config.config["context_retrieval"]["enabled"] = False

        enhanced_messages = await apply_context_retrieval(
            messages=sample_messages,
            model_name="claude-sonnet-4.5",
            user_id="test-user",
            config=mock_config,
        )

        # Should return original messages
        assert enhanced_messages == sample_messages

    @pytest.mark.asyncio
    async def test_apply_context_retrieval_no_api_key(self, mock_config, sample_messages):
        """Test apply_context_retrieval without API key."""
        with patch.dict(os.environ, {}, clear=True):
            enhanced_messages = await apply_context_retrieval(
                messages=sample_messages,
                model_name="claude-sonnet-4.5",
                user_id="test-user",
                config=mock_config,
            )

            # Should return original messages (graceful degradation)
            assert enhanced_messages == sample_messages


# ============================================================================
# Edge Cases and Error Handling
# ============================================================================


class TestEdgeCases:
    """Test edge cases and error scenarios."""

    def test_messages_with_only_system_role(self):
        """Test handling messages with only system role."""
        messages = [{"role": "system", "content": "You are helpful."}]
        query = ContextRetriever.extract_query_from_messages(messages, "last_user")
        assert query == ""

    def test_messages_with_mixed_content_types(self):
        """Test handling messages with different content types."""
        messages = [
            {"role": "user", "content": "Text message"},
            {"role": "user", "content": ["array", "content"]},  # Invalid format
        ]
        # Should handle gracefully
        try:
            query = ContextRetriever.extract_query_from_messages(messages, "all_user")
            # Should only include valid messages
            assert "Text message" in query
        except Exception:
            pytest.fail("Should handle mixed content types gracefully")

    @pytest.mark.asyncio
    async def test_context_retriever_without_http_client(self):
        """Test ContextRetriever without explicit HTTP client."""
        retriever = ContextRetriever(api_key="test-key")
        # Without explicit http_client, it should be None
        # The retrieve_context method will create a temporary one as needed
        assert retriever.http_client is None
        assert retriever.api_key == "test-key"

    def test_invalid_config_structure(self):
        """Test handling invalid config structure."""
        config = MagicMock()
        config.config = {}  # No context_retrieval key

        result = should_use_context_retrieval("any-model", config)
        assert result is False


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])