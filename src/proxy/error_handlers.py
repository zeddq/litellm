"""
Comprehensive Error Handling for LiteLLM SDK Proxy.

This module provides structured error handling for all LiteLLM exceptions,
mapping them to appropriate HTTP status codes and OpenAI-compatible error
responses. It ensures consistent error formats and proper logging.

Key Features:
- Complete LiteLLM exception hierarchy coverage
- OpenAI-compatible error response format
- HTTP status code mapping
- Structured logging with context
- Retry-After headers for rate limits
- Debug information (conditional)

Architecture:
    This error handler provides a centralized approach to exception handling,
    ensuring that all errors are properly logged, formatted, and returned to
    clients in a consistent manner.

References:
    - docs/architecture/LITELLM_SDK_INTEGRATION_PATTERNS.md (Section 4)
    - https://docs.litellm.ai/docs/exception_mapping
"""

import logging
from typing import Any, Dict, Optional

import litellm
from fastapi import Request
from fastapi.responses import JSONResponse


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


# =============================================================================
# Error Response Builder
# =============================================================================


class ErrorResponse:
    """
    Builder for standardized error responses.

    This class provides a consistent format for all error responses, following
    the OpenAI API error format for compatibility with existing clients.

    Error Format (OpenAI-compatible):
        ```json
        {
            "error": {
                "message": "Human-readable error message",
                "type": "error_type_string",
                "code": "error_code",
                "param": "parameter_name" (optional),
                "details": {...} (optional, debug only)
            }
        }
        ```
    """

    @staticmethod
    def build(
        status_code: int,
        error_type: str,
        message: str,
        code: Optional[str] = None,
        param: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        retry_after: Optional[int] = None,
    ) -> JSONResponse:
        """
        Build a standardized error response.

        Args:
            status_code: HTTP status code
            error_type: Error type string (e.g., "invalid_request_error")
            message: Human-readable error message
            code: Optional error code (e.g., "context_length_exceeded")
            param: Optional parameter name that caused the error
            details: Optional additional details (only included in debug mode)
            retry_after: Optional retry-after value in seconds (for rate limits)

        Returns:
            JSONResponse with error payload and appropriate headers

        Example:
            ```python
            return ErrorResponse.build(
                status_code=400,
                error_type="invalid_request_error",
                message="Invalid parameter value",
                code="invalid_parameter",
                param="temperature"
            )
            ```
        """
        error_content: Dict[str, Any] = {
            "message": message,
            "type": error_type,
        }

        if code:
            error_content["code"] = code

        if param:
            error_content["param"] = param

        if details:
            error_content["details"] = details

        content = {"error": error_content}

        headers = {}
        if retry_after is not None:
            headers["Retry-After"] = str(retry_after)

        return JSONResponse(
            status_code=status_code,
            content=content,
            headers=headers if headers else None,
        )


# =============================================================================
# Exception Handler
# =============================================================================


class LiteLLMErrorHandler:
    """
    Comprehensive error handler for LiteLLM exceptions.

    This class maps all LiteLLM exception types to appropriate HTTP responses
    with proper status codes, error messages, and retry hints.

    Exception Hierarchy:
        All LiteLLM exceptions inherit from their OpenAI equivalents, making
        them compatible with OpenAI error handling patterns.

    Status Code Mapping:
        - 400: BadRequestError, ContextWindowExceededError, ContentPolicyViolationError
        - 401: AuthenticationError
        - 403: PermissionDeniedError
        - 404: NotFoundError
        - 408: Timeout
        - 429: RateLimitError
        - 500: APIError (generic)
        - 503: ServiceUnavailableError
    """

    def __init__(self, include_debug_info: bool = False):
        """
        Initialize error handler.

        Args:
            include_debug_info: Whether to include debug details in responses
                (should be False in production)
        """
        self.include_debug_info = include_debug_info

    async def handle_completion_error(
        self, exc: Exception, request_id: Optional[str] = None
    ) -> JSONResponse:
        """
        Handle errors from litellm.acompletion() calls.

        This method processes any exception that occurs during LiteLLM
        completion calls and returns an appropriate HTTP response.

        Args:
            exc: The exception to handle
            request_id: Optional request ID for logging context

        Returns:
            JSONResponse with error details and appropriate status code

        Example:
            ```python
            try:
                response = await litellm.acompletion(...)
            except Exception as e:
                return await error_handler.handle_completion_error(e, request_id="abc123")
            ```
        """
        # Log context (all logs include request_id if available)
        log_extra = {"request_id": request_id} if request_id else {}

        # =============================================================================
        # 400 - Bad Request Errors
        # =============================================================================

        if isinstance(exc, litellm.exceptions.ContextWindowExceededError):
            logger.warning(
                f"Context window exceeded: {exc.message}",
                extra=log_extra,
                exc_info=self.include_debug_info,
            )
            return ErrorResponse.build(
                status_code=400,
                error_type="invalid_request_error",
                message=exc.message,
                code="context_length_exceeded",
                details=(
                    {"exception_type": type(exc).__name__}
                    if self.include_debug_info
                    else None
                ),
            )

        elif isinstance(exc, litellm.exceptions.ContentPolicyViolationError):
            logger.warning(
                f"Content policy violation: {exc.message}",
                extra=log_extra,
                exc_info=self.include_debug_info,
            )
            return ErrorResponse.build(
                status_code=400,
                error_type="invalid_request_error",
                message=exc.message,
                code="content_policy_violation",
                details=(
                    {"exception_type": type(exc).__name__}
                    if self.include_debug_info
                    else None
                ),
            )

        elif isinstance(exc, litellm.exceptions.UnsupportedParamsError):
            logger.warning(
                f"Unsupported parameters: {exc.message}",
                extra=log_extra,
                exc_info=self.include_debug_info,
            )
            return ErrorResponse.build(
                status_code=400,
                error_type="invalid_request_error",
                message=exc.message,
                code="unsupported_parameter",
                details=(
                    {"exception_type": type(exc).__name__}
                    if self.include_debug_info
                    else None
                ),
            )

        elif isinstance(exc, litellm.exceptions.BadRequestError):
            logger.warning(
                f"Bad request: {exc.message}",
                extra=log_extra,
                exc_info=self.include_debug_info,
            )
            return ErrorResponse.build(
                status_code=400,
                error_type="invalid_request_error",
                message=exc.message,
                code="bad_request",
                details=(
                    {"exception_type": type(exc).__name__}
                    if self.include_debug_info
                    else None
                ),
            )

        # =============================================================================
        # 401 - Authentication Error
        # =============================================================================

        elif isinstance(exc, litellm.exceptions.AuthenticationError):
            logger.error(
                f"Authentication failed: {exc.message}",
                extra=log_extra,
                exc_info=self.include_debug_info,
            )
            return ErrorResponse.build(
                status_code=401,
                error_type="authentication_error",
                message="Invalid API key or authentication failed",
                code="invalid_api_key",
                details=(
                    {"exception_type": type(exc).__name__}
                    if self.include_debug_info
                    else None
                ),
            )

        # =============================================================================
        # 403 - Permission Denied
        # =============================================================================

        elif isinstance(exc, litellm.exceptions.PermissionDeniedError):
            logger.error(
                f"Permission denied: {exc.message}",
                extra=log_extra,
                exc_info=self.include_debug_info,
            )
            return ErrorResponse.build(
                status_code=403,
                error_type="permission_error",
                message=exc.message,
                code="permission_denied",
                details=(
                    {"exception_type": type(exc).__name__}
                    if self.include_debug_info
                    else None
                ),
            )

        # =============================================================================
        # 404 - Not Found
        # =============================================================================

        elif isinstance(exc, litellm.exceptions.NotFoundError):
            logger.error(
                f"Resource not found: {exc.message}",
                extra=log_extra,
                exc_info=self.include_debug_info,
            )
            return ErrorResponse.build(
                status_code=404,
                error_type="not_found_error",
                message=exc.message,
                code="model_not_found",
                details=(
                    {"exception_type": type(exc).__name__}
                    if self.include_debug_info
                    else None
                ),
            )

        # =============================================================================
        # 408 - Timeout
        # =============================================================================

        elif isinstance(exc, litellm.exceptions.Timeout):
            logger.error(
                f"Request timeout: {exc.message}",
                extra=log_extra,
                exc_info=self.include_debug_info,
            )
            return ErrorResponse.build(
                status_code=408,
                error_type="timeout_error",
                message=exc.message,
                code="request_timeout",
                retry_after=60,  # Suggest retry after 60 seconds
                details=(
                    {"exception_type": type(exc).__name__}
                    if self.include_debug_info
                    else None
                ),
            )

        # =============================================================================
        # 429 - Rate Limit
        # =============================================================================

        elif isinstance(exc, litellm.exceptions.RateLimitError):
            # Extract retry_after if available
            retry_after = getattr(exc, "retry_after", None)
            if retry_after is None:
                retry_after = 60  # Default to 60 seconds

            logger.warning(
                f"Rate limit exceeded (retry after {retry_after}s): {exc.message}",
                extra=log_extra,
                exc_info=self.include_debug_info,
            )
            return ErrorResponse.build(
                status_code=429,
                error_type="rate_limit_error",
                message=exc.message,
                code="rate_limit_exceeded",
                retry_after=retry_after,
                details=(
                    {"exception_type": type(exc).__name__}
                    if self.include_debug_info
                    else None
                ),
            )

        # =============================================================================
        # 503 - Service Unavailable
        # =============================================================================

        elif isinstance(exc, litellm.exceptions.ServiceUnavailableError):
            logger.error(
                f"Service unavailable: {exc.message}",
                extra=log_extra,
                exc_info=self.include_debug_info,
            )
            return ErrorResponse.build(
                status_code=503,
                error_type="service_unavailable",
                message=exc.message,
                code="service_unavailable",
                retry_after=30,  # Suggest retry after 30 seconds
                details=(
                    {"exception_type": type(exc).__name__}
                    if self.include_debug_info
                    else None
                ),
            )

        # =============================================================================
        # 500 - API Error (Generic)
        # =============================================================================

        elif isinstance(exc, litellm.exceptions.APIError):
            logger.error(
                f"API error: {exc.message}",
                extra=log_extra,
                exc_info=self.include_debug_info,
            )
            return ErrorResponse.build(
                status_code=500,
                error_type="api_error",
                message=exc.message,
                code="api_error",
                details=(
                    {"exception_type": type(exc).__name__}
                    if self.include_debug_info
                    else None
                ),
            )

        # =============================================================================
        # Catch-all for unexpected exceptions
        # =============================================================================

        else:
            logger.exception(
                f"Unexpected error: {type(exc).__name__}: {str(exc)}",
                extra=log_extra,
            )
            return ErrorResponse.build(
                status_code=500,
                error_type="internal_error",
                message="Internal server error",
                code="internal_error",
                details=(
                    {
                        "exception_type": type(exc).__name__,
                        "exception_message": str(exc),
                    }
                    if self.include_debug_info
                    else None
                ),
            )


# =============================================================================
# FastAPI exception handlers
# =============================================================================


def register_exception_handlers(app, include_debug_info: bool = False):
    """
    Register exception handlers with FastAPI application.

    This function sets up exception handlers for all LiteLLM exceptions,
    ensuring consistent error handling across the entire application.

    Args:
        app: FastAPI application instance
        include_debug_info: Whether to include debug info in responses

    Example:
        ```python
        from fastapi import FastAPI
        from proxy.error_handlers import register_exception_handlers

        app = FastAPI()
        register_exception_handlers(app, include_debug_info=False)
        ```
    """
    error_handler = LiteLLMErrorHandler(include_debug_info=include_debug_info)

    @app.exception_handler(litellm.exceptions.BadRequestError)
    async def handle_bad_request(
        request: Request, exc: litellm.exceptions.BadRequestError
    ):
        return await error_handler.handle_completion_error(exc)

    @app.exception_handler(litellm.exceptions.AuthenticationError)
    async def handle_auth_error(
        request: Request, exc: litellm.exceptions.AuthenticationError
    ):
        return await error_handler.handle_completion_error(exc)

    @app.exception_handler(litellm.exceptions.PermissionDeniedError)
    async def handle_permission_error(
        request: Request, exc: litellm.exceptions.PermissionDeniedError
    ):
        return await error_handler.handle_completion_error(exc)

    @app.exception_handler(litellm.exceptions.NotFoundError)
    async def handle_not_found(request: Request, exc: litellm.exceptions.NotFoundError):
        return await error_handler.handle_completion_error(exc)

    @app.exception_handler(litellm.exceptions.Timeout)
    async def handle_timeout(request: Request, exc: litellm.exceptions.Timeout):
        return await error_handler.handle_completion_error(exc)

    @app.exception_handler(litellm.exceptions.RateLimitError)
    async def handle_rate_limit(
        request: Request, exc: litellm.exceptions.RateLimitError
    ):
        return await error_handler.handle_completion_error(exc)

    @app.exception_handler(litellm.exceptions.ServiceUnavailableError)
    async def handle_service_unavailable(
        request: Request, exc: litellm.exceptions.ServiceUnavailableError
    ):
        return await error_handler.handle_completion_error(exc)

    @app.exception_handler(litellm.exceptions.APIError)
    async def handle_api_error(request: Request, exc: litellm.exceptions.APIError):
        return await error_handler.handle_completion_error(exc)

    logger.info(
        f"✅ Registered LiteLLM exception handlers (debug_info={include_debug_info})"
    )


# =============================================================================
# Testing and validation
# =============================================================================

if __name__ == "__main__":
    """
    Test error handler functionality.

    Usage:
        python -m src.proxy.error_handlers
    """
    import asyncio

    async def test_error_handler():
        """Test error handling for various exception types."""
        print("\n" + "=" * 70)
        print("Testing LiteLLMErrorHandler")
        print("=" * 70 + "\n")

        handler = LiteLLMErrorHandler(include_debug_info=True)

        # Test various exception types
        test_cases = [
            (
                litellm.exceptions.BadRequestError(
                    message="Invalid parameter", model="gpt-4", llm_provider="openai"
                ),
                400,
                "bad_request",
            ),
            (
                litellm.exceptions.AuthenticationError(
                    message="Invalid API key", model="gpt-4", llm_provider="openai"
                ),
                401,
                "invalid_api_key",
            ),
            (
                litellm.exceptions.RateLimitError(
                    message="Rate limit exceeded", model="gpt-4", llm_provider="openai"
                ),
                429,
                "rate_limit_exceeded",
            ),
            (
                litellm.exceptions.ServiceUnavailableError(
                    message="Service temporarily unavailable",
                    model="gpt-4",
                    llm_provider="openai",
                ),
                503,
                "service_unavailable",
            ),
        ]

        for exc, expected_status, expected_code in test_cases:
            print(f"Test: {type(exc).__name__}")
            response = await handler.handle_completion_error(exc, request_id="test-123")

            print(f"  Status Code: {response.status_code}")
            print(f"  Expected: {expected_status}")
            print(f"  Match: {response.status_code == expected_status}")

            # Check error code
            import json

            raw_body = response.body
            match raw_body:
                case memoryview():
                    body = raw_body.tobytes().decode("utf8")
                case bytes():
                    body = raw_body.decode("utf8")
                case _:
                    raise ValueError(f"${raw_body} must be bytes or memoryview but is: {type(raw_body)}")
            body = json.loads(body)
            actual_code = body["error"].get("code")
            print(f"  Error Code: {actual_code}")
            print(f"  Expected: {expected_code}")
            print(f"  Match: {actual_code == expected_code}")
            print()

        print("=" * 70)
        print("✅ All tests completed!")
        print("=" * 70 + "\n")

    asyncio.run(test_error_handler())
