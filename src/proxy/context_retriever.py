"""
Context Retriever Module for Supermemory Integration

This module provides context retrieval functionality from Supermemory's /v4/profile endpoint.
It enhances LLM prompts with relevant user-specific memories and documents.

Architecture:
    - Uses persistent httpx.AsyncClient for cookie persistence (Cloudflare compatibility)
    - Queries Supermemory API based on user messages
    - Returns structured context for prompt enhancement
    - Configurable per-model and globally

Example:
    ```python
    retriever = ContextRetriever(
        api_key="sm_...",
        base_url="https://api.supermemory.ai",
        http_client=my_persistent_client
    )

    context = await retriever.retrieve_context(
        query="litellm project",
        user_id="developer-123",
        container_tag="supermemory"
    )

    enhanced_messages = retriever.inject_context(messages, context)
    ```

References:
    - Supermemory API: https://docs.supermemory.ai/
    - User snippet: /v4/profile endpoint usage
"""

import logging
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class ContextRetrievalError(Exception):
    """Base exception for context retrieval failures."""

    pass


class SupermemoryAPIError(ContextRetrievalError):
    """Supermemory API returned an error response."""

    def __init__(
        self, status_code: int, message: str, response_body: Optional[str] = None
    ):
        self.status_code = status_code
        self.message = message
        self.response_body = response_body
        super().__init__(f"Supermemory API error {status_code}: {message}")


class ContextRetriever:
    """
    Retrieves relevant context from Supermemory API.

    This class handles:
    - HTTP communication with Supermemory /v4/profile endpoint
    - Cookie persistence via injected httpx.AsyncClient
    - Query generation from user messages
    - Context formatting for prompt injection

    Attributes:
        api_key: Supermemory API key
        base_url: Supermemory API base URL
        http_client: Persistent httpx.AsyncClient (for cookie persistence)
        default_container_tag: Default container tag for queries
        max_context_length: Maximum characters to retrieve
        timeout: Request timeout in seconds
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.supermemory.ai",
        http_client: Optional[httpx.AsyncClient] = None,
        default_container_tag: str = "supermemory",
        max_context_length: int = 4000,
        timeout: float = 10.0,
    ):
        """
        Initialize context retriever.

        Args:
            api_key: Supermemory API key
            base_url: Supermemory API base URL
            http_client: Optional persistent HTTP client (recommended for Cloudflare)
            default_container_tag: Default container tag for queries
            max_context_length: Maximum context length in characters
            timeout: Request timeout in seconds
        """
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.http_client = http_client
        self.default_container_tag = default_container_tag
        self.max_context_length = max_context_length
        self.timeout = timeout

        logger.info(
            f"ContextRetriever initialized: "
            f"base_url={self.base_url}, "
            f"container_tag={self.default_container_tag}, "
            f"max_length={self.max_context_length}"
        )

    async def retrieve_context(
        self,
        query: str,
        user_id: str,
        container_tag: Optional[str] = None,
        max_results: int = 5,
    ) -> Dict[str, Any]:
        """
        Retrieve relevant context from Supermemory.

        Queries the /v4/profile endpoint with the given parameters and returns
        relevant memories/documents.

        Args:
            query: Search query (typically extracted from user message)
            user_id: User ID for memory isolation
            container_tag: Container tag to search in (defaults to default_container_tag)
            max_results: Maximum number of results to return

        Returns:
            Dict with retrieved context:
            {
                "success": bool,
                "results": List[Dict],
                "query": str,
                "user_id": str,
                "formatted_context": str
            }

        Raises:
            SupermemoryAPIError: If API returns error response
            ContextRetrievalError: For other retrieval failures
        """
        container_tag = container_tag or self.default_container_tag

        logger.info(
            f"Retrieving context: query='{query[:50]}...', "
            f"user_id={user_id}, container={container_tag}"
        )

        # Prepare request payload
        payload = {
            "q": query,
            "containerTag": container_tag,
            "limit": max_results,
        }

        # Prepare headers
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "x-sm-user-id": user_id,
        }

        # Make request
        try:
            # Use provided client or create temporary one
            if self.http_client:
                response = await self.http_client.post(
                    f"{self.base_url}/v4/profile",
                    json=payload,
                    headers=headers,
                    timeout=self.timeout,
                )
            else:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(
                        f"{self.base_url}/v4/profile",
                        json=payload,
                        headers=headers,
                    )

            # Check response status
            if response.status_code != 200:
                error_body = response.text
                logger.error(
                    f"Supermemory API error: status={response.status_code}, "
                    f"body={error_body[:500]}"
                )
                raise SupermemoryAPIError(
                    status_code=response.status_code,
                    message=f"API returned {response.status_code}",
                    response_body=error_body,
                )

            # Parse response
            data = response.json()

            logger.info(
                f"Context retrieved successfully: "
                f"found {len(data.get('results', []))} results"
            )

            # Format context for injection
            formatted_context = self._format_context(data.get("results", []))

            return {
                "success": True,
                "results": data.get("results", []),
                "query": query,
                "user_id": user_id,
                "formatted_context": formatted_context,
                "metadata": {
                    "container_tag": container_tag,
                    "result_count": len(data.get("results", [])),
                },
            }

        except httpx.TimeoutException as e:
            logger.error(f"Supermemory API timeout after {self.timeout}s: {e}")
            raise ContextRetrievalError(f"Request timeout after {self.timeout}s") from e

        except httpx.HTTPError as e:
            logger.error(f"HTTP error retrieving context: {e}")
            raise ContextRetrievalError(f"HTTP error: {e}") from e

        except Exception as e:
            logger.error(f"Unexpected error retrieving context: {e}", exc_info=True)
            raise ContextRetrievalError(f"Unexpected error: {e}") from e

    def _format_context(self, results: List[Dict[str, Any]]) -> str:
        """
        Format retrieved results into a context string.

        Args:
            results: List of result dictionaries from Supermemory

        Returns:
            Formatted context string ready for prompt injection
        """
        if not results:
            return ""

        # Build context string
        context_parts = ["<relevant_context>"]

        for i, result in enumerate(results, 1):
            # Extract relevant fields (adjust based on actual API response structure)
            title = result.get("title", "Untitled")
            content = result.get("content", result.get("text", ""))
            source = result.get("source", "")

            # Truncate content if needed
            if len(content) > 500:
                content = content[:497] + "..."

            context_parts.append(f"\n[Memory {i}: {title}]")
            if source:
                context_parts.append(f"Source: {source}")
            context_parts.append(content)

        context_parts.append("\n</relevant_context>")

        full_context = "\n".join(context_parts)

        # Truncate if exceeds max length
        if len(full_context) > self.max_context_length:
            full_context = full_context[: self.max_context_length - 3] + "..."
            logger.warning(
                f"Context truncated from {len(full_context)} to {self.max_context_length} chars"
            )

        return full_context

    @staticmethod
    def extract_query_from_messages(
        messages: List[Dict[str, Any]],
        strategy: str = "last_user",
    ) -> str:
        """
        Extract query from message list for context retrieval.

        Strategies:
        - "last_user": Use last user message (default)
        - "first_user": Use first user message
        - "all_user": Concatenate all user messages
        - "last_assistant": Use last assistant message

        Args:
            messages: List of chat messages
            strategy: Query extraction strategy

        Returns:
            Extracted query string
        """
        if not messages:
            return ""

        if strategy == "last_user":
            # Find last user message
            for msg in reversed(messages):
                if msg.get("role") == "user":
                    content = msg.get("content", "")
                    if isinstance(content, str):
                        return content
                    elif isinstance(content, list):
                        # Handle content blocks (for Claude)
                        text_parts = [
                            block.get("text", "")
                            for block in content
                            if block.get("type") == "text"
                        ]
                        return " ".join(text_parts)

        elif strategy == "first_user":
            # Find first user message
            for msg in messages:
                if msg.get("role") == "user":
                    content = msg.get("content", "")
                    if isinstance(content, str):
                        return content

        elif strategy == "all_user":
            # Concatenate all user messages
            user_contents = []
            for msg in messages:
                if msg.get("role") == "user":
                    content = msg.get("content", "")
                    if isinstance(content, str):
                        user_contents.append(content)
            return " | ".join(user_contents)

        elif strategy == "last_assistant":
            # Find last assistant message
            for msg in reversed(messages):
                if msg.get("role") == "assistant":
                    content = msg.get("content", "")
                    if isinstance(content, str):
                        return content

        return ""

    @staticmethod
    def inject_context_into_messages(
        messages: List[Dict[str, Any]],
        context: str,
        injection_strategy: str = "dual",
        static_system_prompt: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Inject retrieved context into message list.

        Strategies:
        - "system": Add as system message at start (DEPRECATED - breaks caching)
        - "dual": Static system message (cacheable) + dynamic context (separate)
        - "user_prefix": Prepend to first user message
        - "user_suffix": Append to last user message

        Args:
            messages: Original message list
            context: Formatted context string
            injection_strategy: Where to inject context
            static_system_prompt: Optional static system prompt (for "dual" strategy)

        Returns:
            Enhanced message list with context injected
        """
        if not context:
            return messages

        enhanced_messages = messages.copy()

        if injection_strategy == "dual":
            # RECOMMENDED: Separate static (cacheable) from dynamic (not cached)

            # 1. Ensure static system message exists and is FIRST
            has_static_system = False
            for i, msg in enumerate(enhanced_messages):
                if msg.get("role") == "system" and not msg.get(
                    "supermemory_context"
                ):
                    has_static_system = True
                    # Mark as cacheable
                    msg["cache_control"] = {"type": "ephemeral"}
                    logger.info(
                        "✅ Marked existing static system message as cacheable"
                    )
                    break

            if not has_static_system:
                # Create default static system message
                default_prompt = static_system_prompt or (
                    "You are a helpful AI assistant with access to the user's personal memory. "
                    "When answering questions, use the context provided in the following message "
                    "to give personalized and accurate responses. "
                    "Always cite sources when using information from the user's memory."
                )

                static_msg = {
                    "role": "system",
                    "content": default_prompt,
                    "cache_control": {"type": "ephemeral"},  # CACHE THIS
                }
                enhanced_messages.insert(0, static_msg)
                logger.info("✅ Created static system message (cacheable)")

            # 2. Insert dynamic context as SEPARATE system message (NOT cached)
            context_message = {
                "role": "system",
                "content": (
                    "# User's Relevant Memory\n\n"
                    f"{context}\n\n"
                    "Use the above context to provide personalized responses."
                ),
                "supermemory_context": True,  # Marker to identify dynamic context
                # NO cache_control - this changes every request
            }

            # Find position: after first system message, before other messages
            insert_position = (
                1 if enhanced_messages[0].get("role") == "system" else 0
            )
            enhanced_messages.insert(insert_position, context_message)

            logger.info(
                "✅ Context injection strategy: DUAL "
                "(static system cached ✓, dynamic context not cached ✓)"
            )

        elif injection_strategy == "system":
            # OLD STRATEGY - BREAKS CACHING
            logger.warning(
                "⚠️  Using 'system' injection strategy - this BREAKS prompt caching! "
                "The system message will be different for every request (due to dynamic context), "
                "resulting in 0% cache hit rate. Consider using 'dual' strategy instead."
            )

            # Check if system message already exists
            has_system = False
            for i, msg in enumerate(enhanced_messages):
                if msg.get("role") == "system":
                    # Append context to existing system message
                    original_content = msg.get("content", "")
                    enhanced_messages[i]["content"] = (
                        f"{original_content}\n\n"
                        f"You have access to the following relevant context:\n{context}"
                    )
                    has_system = True
                    logger.info(
                        "Context appended to existing system message (NOT CACHED)"
                    )
                    break

            if not has_system:
                # Create new system message with context
                system_message = {
                    "role": "system",
                    "content": (
                        "You have access to the following relevant context from the user's memory. "
                        "Use this information to provide more personalized and accurate responses.\n\n"
                        f"{context}"
                    ),
                }
                enhanced_messages.insert(0, system_message)
                logger.info("Context injected as system message (NOT CACHED)")

        elif injection_strategy == "user_prefix":
            # Prepend to first user message
            for i, msg in enumerate(enhanced_messages):
                if msg.get("role") == "user":
                    original_content = msg.get("content", "")
                    enhanced_messages[i][
                        "content"
                    ] = f"{context}\n\n---\n\n{original_content}"
                    logger.info("Context prepended to first user message")
                    break

        elif injection_strategy == "user_suffix":
            # Append to last user message
            for i in range(len(enhanced_messages) - 1, -1, -1):
                if enhanced_messages[i].get("role") == "user":
                    original_content = enhanced_messages[i].get("content", "")
                    enhanced_messages[i][
                        "content"
                    ] = f"{original_content}\n\n---\n\n{context}"
                    logger.info("Context appended to last user message")
                    break

        return enhanced_messages


# =============================================================================
# Helper Functions
# =============================================================================


async def retrieve_and_inject_context(
    retriever: ContextRetriever,
    messages: List[Dict[str, Any]],
    user_id: str,
    query_strategy: str = "last_user",
    injection_strategy: str = "dual",  # CHANGED: default to "dual"
    container_tag: Optional[str] = None,
    static_system_prompt: Optional[str] = None,  # NEW parameter
) -> tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """
    Helper function to retrieve context and inject into messages.

    This is a convenience function that combines query extraction,
    context retrieval, and message enhancement in one call.

    PROMPT CACHING STRATEGY:
    - Use injection_strategy="dual" (RECOMMENDED)
    - Static system prompt is cached (90% savings on repeated requests)
    - Dynamic Supermemory context is NOT cached (changes per request)

    Args:
        retriever: ContextRetriever instance
        messages: Original message list
        user_id: User ID for memory isolation
        query_strategy: How to extract query from messages
        injection_strategy: Where to inject context (use "dual" for caching)
        container_tag: Optional container tag override
        static_system_prompt: Optional custom static prompt (cached separately)

    Returns:
        Tuple of (enhanced_messages, context_metadata)
        If retrieval fails, returns (original_messages, None)
    """
    try:
        # Extract query from messages
        query = ContextRetriever.extract_query_from_messages(
            messages, strategy=query_strategy
        )

        if not query:
            logger.warning(
                "No query extracted from messages, skipping context retrieval"
            )
            return messages, None

        # Retrieve context
        context_data = await retriever.retrieve_context(
            query=query,
            user_id=user_id,
            container_tag=container_tag,
        )

        # Check if we got results
        if not context_data.get("results") or len(context_data["results"]) == 0:
            logger.info("No context results found, using original messages")
            return messages, context_data

        # Inject context into messages
        enhanced_messages = ContextRetriever.inject_context_into_messages(
            messages=messages,
            context=context_data["formatted_context"],
            injection_strategy=injection_strategy,
            static_system_prompt=static_system_prompt,  # Pass through
        )

        # Add metadata about caching strategy
        context_data["caching_strategy"] = injection_strategy
        if injection_strategy == "dual":
            context_data["cache_info"] = {
                "static_system_cached": True,
                "dynamic_context_cached": False,
                "expected_savings": "~40-60% on repeated requests (static prompt + tools)",
            }

        return enhanced_messages, context_data

    except ContextRetrievalError as e:
        logger.error(f"Context retrieval failed: {e}")
        # Return original messages on failure (graceful degradation)
        return messages, None
    except Exception as e:
        logger.error(f"Unexpected error in context retrieval: {e}", exc_info=True)
        return messages, None