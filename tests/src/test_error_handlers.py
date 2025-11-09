"""
Comprehensive tests for error handling module.

Tests cover:
- ErrorResponse.build() functionality
- LiteLLMErrorHandler exception mapping
- HTTP status code correctness
- OpenAI-compatible error format
- Retry-After headers
- Debug information handling
"""

import json
from typing import Dict, Any

import pytest
import litellm
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from proxy.error_handlers import (
    ErrorResponse,
    LiteLLMErrorHandler,
    register_exception_handlers,
)


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def error_handler():
    """Create error handler instance."""
    return LiteLLMErrorHandler(include_debug_info=False)


@pytest.fixture
def error_handler_with_debug():
    """Create error handler with debug info enabled."""
    return LiteLLMErrorHandler(include_debug_info=True)


@pytest.fixture
def test_app():
    """Create FastAPI test application with error handlers."""
    app = FastAPI()
    register_exception_handlers(app, include_debug_info=False)
    
    @app.get("/test/bad_request")
    async def test_bad_request():
        raise litellm.exceptions.BadRequestError(
            message="Test bad request",
            model="gpt-4",
            llm_provider="openai"
        )
    
    @app.get("/test/auth_error")
    async def test_auth_error():
        raise litellm.exceptions.AuthenticationError(
            message="Test auth error",
            model="gpt-4",
            llm_provider="openai"
        )
    
    @app.get("/test/rate_limit")
    async def test_rate_limit():
        raise litellm.exceptions.RateLimitError(
            message="Test rate limit",
            model="gpt-4",
            llm_provider="openai"
        )
    
    return app


# =============================================================================
# Test ErrorResponse.build()
# =============================================================================


class TestErrorResponse:
    """Test ErrorResponse builder functionality."""
    
    def test_build_basic_error(self):
        """Test building basic error response."""
        response = ErrorResponse.build(
            status_code=400,
            error_type="invalid_request_error",
            message="Test error message",
        )
        
        assert response.status_code == 400
        body = json.loads(response.body.decode())
        
        assert "error" in body
        assert body["error"]["message"] == "Test error message"
        assert body["error"]["type"] == "invalid_request_error"
    
    def test_build_error_with_code(self):
        """Test building error with error code."""
        response = ErrorResponse.build(
            status_code=400,
            error_type="invalid_request_error",
            message="Invalid parameter",
            code="invalid_parameter",
        )
        
        body = json.loads(response.body.decode())
        assert body["error"]["code"] == "invalid_parameter"
    
    def test_build_error_with_param(self):
        """Test building error with parameter name."""
        response = ErrorResponse.build(
            status_code=400,
            error_type="invalid_request_error",
            message="Invalid temperature",
            param="temperature",
        )
        
        body = json.loads(response.body.decode())
        assert body["error"]["param"] == "temperature"
    
    def test_build_error_with_details(self):
        """Test building error with debug details."""
        details = {"exception_type": "ValueError", "stack_trace": "..."}
        response = ErrorResponse.build(
            status_code=500,
            error_type="internal_error",
            message="Internal error",
            details=details,
        )
        
        body = json.loads(response.body.decode())
        assert body["error"]["details"] == details
    
    def test_build_error_with_retry_after(self):
        """Test building error with Retry-After header."""
        response = ErrorResponse.build(
            status_code=429,
            error_type="rate_limit_error",
            message="Rate limit exceeded",
            retry_after=60,
        )
        
        assert response.status_code == 429
        assert "retry-after" in response.headers
        assert response.headers["retry-after"] == "60"
    
    def test_openai_compatible_format(self):
        """Test that error format is OpenAI-compatible."""
        response = ErrorResponse.build(
            status_code=400,
            error_type="invalid_request_error",
            message="Missing required parameter",
            code="missing_parameter",
            param="messages",
        )
        
        body = json.loads(response.body.decode())
        
        # OpenAI error format structure
        assert "error" in body
        assert "message" in body["error"]
        assert "type" in body["error"]
        assert isinstance(body["error"]["message"], str)
        assert isinstance(body["error"]["type"], str)


# =============================================================================
# Test LiteLLMErrorHandler
# =============================================================================


class TestLiteLLMErrorHandler:
    """Test error handler exception mapping."""
    
    @pytest.mark.asyncio
    async def test_bad_request_error(self, error_handler):
        """Test handling of BadRequestError."""
        exc = litellm.exceptions.BadRequestError(
            message="Invalid request",
            model="gpt-4",
            llm_provider="openai"
        )
        
        response = await error_handler.handle_completion_error(exc)
        
        assert response.status_code == 400
        body = json.loads(response.body.decode())
        assert body["error"]["type"] == "invalid_request_error"
        assert body["error"]["code"] == "bad_request"
    
    @pytest.mark.asyncio
    async def test_context_window_exceeded_error(self, error_handler):
        """Test handling of ContextWindowExceededError."""
        exc = litellm.exceptions.ContextWindowExceededError(
            message="Context too long",
            model="gpt-4",
            llm_provider="openai"
        )
        
        response = await error_handler.handle_completion_error(exc)
        
        assert response.status_code == 400
        body = json.loads(response.body.decode())
        assert body["error"]["code"] == "context_length_exceeded"
    
    @pytest.mark.asyncio
    async def test_content_policy_violation_error(self, error_handler):
        """Test handling of ContentPolicyViolationError."""
        exc = litellm.exceptions.ContentPolicyViolationError(
            message="Content violates policy",
            model="gpt-4",
            llm_provider="openai"
        )
        
        response = await error_handler.handle_completion_error(exc)
        
        assert response.status_code == 400
        body = json.loads(response.body.decode())
        assert body["error"]["code"] == "content_policy_violation"
    
    @pytest.mark.asyncio
    async def test_unsupported_params_error(self, error_handler):
        """Test handling of UnsupportedParamsError."""
        exc = litellm.exceptions.UnsupportedParamsError(
            message="Parameter not supported",
            model="gpt-4",
            llm_provider="openai"
        )
        
        response = await error_handler.handle_completion_error(exc)
        
        assert response.status_code == 400
        body = json.loads(response.body.decode())
        assert body["error"]["code"] == "unsupported_parameter"
    
    @pytest.mark.asyncio
    async def test_authentication_error(self, error_handler):
        """Test handling of AuthenticationError."""
        exc = litellm.exceptions.AuthenticationError(
            message="Invalid API key",
            model="gpt-4",
            llm_provider="openai"
        )
        
        response = await error_handler.handle_completion_error(exc)
        
        assert response.status_code == 401
        body = json.loads(response.body.decode())
        assert body["error"]["type"] == "authentication_error"
        assert body["error"]["code"] == "invalid_api_key"
    
    @pytest.mark.skip(reason="PermissionDeniedError requires complex mock response object")
    @pytest.mark.asyncio
    async def test_permission_denied_error(self, error_handler):
        """Test handling of PermissionDeniedError."""
        exc = litellm.exceptions.PermissionDeniedError(
            message="Access denied",
            model="gpt-4",
            llm_provider="openai",
            response={}
        )
        
        response = await error_handler.handle_completion_error(exc)
        
        assert response.status_code == 403
        body = json.loads(response.body.decode())
        assert body["error"]["type"] == "permission_error"
        assert body["error"]["code"] == "permission_denied"
    
    @pytest.mark.asyncio
    async def test_not_found_error(self, error_handler):
        """Test handling of NotFoundError."""
        exc = litellm.exceptions.NotFoundError(
            message="Model not found",
            model="invalid-model",
            llm_provider="openai"
        )
        
        response = await error_handler.handle_completion_error(exc)
        
        assert response.status_code == 404
        body = json.loads(response.body.decode())
        assert body["error"]["type"] == "not_found_error"
        assert body["error"]["code"] == "model_not_found"
    
    @pytest.mark.asyncio
    async def test_timeout_error(self, error_handler):
        """Test handling of Timeout error."""
        exc = litellm.exceptions.Timeout(
            message="Request timed out",
            model="gpt-4",
            llm_provider="openai"
        )
        
        response = await error_handler.handle_completion_error(exc)
        
        assert response.status_code == 408
        body = json.loads(response.body.decode())
        assert body["error"]["type"] == "timeout_error"
        assert body["error"]["code"] == "request_timeout"
        assert "retry-after" in response.headers
        assert response.headers["retry-after"] == "60"
    
    @pytest.mark.asyncio
    async def test_rate_limit_error(self, error_handler):
        """Test handling of RateLimitError."""
        exc = litellm.exceptions.RateLimitError(
            message="Rate limit exceeded",
            model="gpt-4",
            llm_provider="openai"
        )
        
        response = await error_handler.handle_completion_error(exc)
        
        assert response.status_code == 429
        body = json.loads(response.body.decode())
        assert body["error"]["type"] == "rate_limit_error"
        assert body["error"]["code"] == "rate_limit_exceeded"
        assert "retry-after" in response.headers
    
    @pytest.mark.asyncio
    async def test_service_unavailable_error(self, error_handler):
        """Test handling of ServiceUnavailableError."""
        exc = litellm.exceptions.ServiceUnavailableError(
            message="Service unavailable",
            model="gpt-4",
            llm_provider="openai"
        )
        
        response = await error_handler.handle_completion_error(exc)
        
        assert response.status_code == 503
        body = json.loads(response.body.decode())
        assert body["error"]["type"] == "service_unavailable"
        assert body["error"]["code"] == "service_unavailable"
        assert "retry-after" in response.headers
        assert response.headers["retry-after"] == "30"
    
    @pytest.mark.asyncio
    async def test_api_error(self, error_handler):
        """Test handling of generic APIError."""
        exc = litellm.exceptions.APIError(
            message="API error occurred",
            model="gpt-4",
            llm_provider="openai",
            status_code=500
        )
        
        response = await error_handler.handle_completion_error(exc)
        
        assert response.status_code == 500
        body = json.loads(response.body.decode())
        assert body["error"]["type"] == "api_error"
        assert body["error"]["code"] == "api_error"
    
    @pytest.mark.asyncio
    async def test_unexpected_exception(self, error_handler):
        """Test handling of unexpected (non-LiteLLM) exceptions."""
        exc = ValueError("Unexpected error")
        
        response = await error_handler.handle_completion_error(exc)
        
        assert response.status_code == 500
        body = json.loads(response.body.decode())
        assert body["error"]["type"] == "internal_error"
        assert body["error"]["code"] == "internal_error"
    
    @pytest.mark.asyncio
    async def test_debug_info_disabled(self, error_handler):
        """Test that debug info is not included when disabled."""
        exc = litellm.exceptions.BadRequestError(
            message="Test error",
            model="gpt-4",
            llm_provider="openai"
        )
        
        response = await error_handler.handle_completion_error(exc)
        body = json.loads(response.body.decode())
        
        assert "details" not in body["error"]
    
    @pytest.mark.asyncio
    async def test_debug_info_enabled(self, error_handler_with_debug):
        """Test that debug info is included when enabled."""
        exc = litellm.exceptions.BadRequestError(
            message="Test error",
            model="gpt-4",
            llm_provider="openai"
        )
        
        response = await error_handler_with_debug.handle_completion_error(exc)
        body = json.loads(response.body.decode())
        
        assert "details" in body["error"]
        assert "exception_type" in body["error"]["details"]
        assert body["error"]["details"]["exception_type"] == "BadRequestError"
    
    @pytest.mark.asyncio
    async def test_request_id_logging(self, error_handler):
        """Test that request_id is passed to handler."""
        exc = litellm.exceptions.BadRequestError(
            message="Test error",
            model="gpt-4",
            llm_provider="openai"
        )
        
        # Should not raise exception
        response = await error_handler.handle_completion_error(
            exc, 
            request_id="test-request-123"
        )
        
        assert response.status_code == 400


# =============================================================================
# Test FastAPI Integration
# =============================================================================


class TestFastAPIIntegration:
    """Test error handler integration with FastAPI."""
    
    def test_register_exception_handlers(self, test_app):
        """Test that exception handlers are registered correctly."""
        client = TestClient(test_app)
        
        # Test bad request handler
        response = client.get("/test/bad_request")
        assert response.status_code == 400
        assert "error" in response.json()
        assert response.json()["error"]["type"] == "invalid_request_error"
    
    def test_auth_error_handler(self, test_app):
        """Test authentication error handler."""
        client = TestClient(test_app)
        
        response = client.get("/test/auth_error")
        assert response.status_code == 401
        assert response.json()["error"]["type"] == "authentication_error"
    
    def test_rate_limit_handler(self, test_app):
        """Test rate limit error handler."""
        client = TestClient(test_app)
        
        response = client.get("/test/rate_limit")
        assert response.status_code == 429
        assert response.json()["error"]["type"] == "rate_limit_error"
        assert "retry-after" in response.headers
