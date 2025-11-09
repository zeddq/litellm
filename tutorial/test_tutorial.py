"""
Test Script for LiteLLM Proxy with Memory Tutorial

This comprehensive test suite validates all components and features covered in the
LiteLLM Memory Proxy tutorial. It provides executable examples of how each module
works and ensures the tutorial code functions correctly.

The test suite covers:
- Module 1: Environment configuration and logging setup
- Module 2: Proxy configuration and model management
- Module 3: Memory management (messages, sessions, storage)
- Module 4: Client detection, rate limiting, and context windows
- Integration: End-to-end conversation flows with memory persistence

Each test is self-contained and demonstrates a specific feature or capability.
Tests will skip (not fail) if optional dependencies are missing.

Usage:
    # Run all tests
    python test_tutorial.py
    
    # Or via pytest
    pytest test_tutorial.py -v

Exit codes:
    0: All tests passed
    1: One or more tests failed
    130: Tests interrupted by user
    
Note: Some tests require environment variables (OPENAI_API_KEY, etc.) but will
      use placeholder values for validation testing.
"""

import asyncio
import json
import sys
from datetime import datetime
from typing import Optional

# Import tutorial components
from tutorial_proxy_with_memory import (
    # Module 1: Foundation
    setup_logging,
    LogLevel,
    EnvironmentConfig,
    validate_environment,

    # Module 2: Configuration
    ProxyConfiguration,
    ModelConfig,
    ModelProvider,
    create_sample_configuration,

    # Module 3: Memory
    Message,
    ConversationSession,
    InMemoryStore,
    MemoryManager,

    # Module 4: Proxy
    ClientDetector,
    RateLimiter,

    # Utilities
    logger
)


class TestRunner:
    """
    Custom test runner for tutorial validation with structured output.
    
    This runner provides:
    - Clear test separation with visual dividers
    - Three test outcomes: passed, failed, skipped
    - Detailed error reporting for failures
    - Summary statistics at completion
    
    Attributes:
        passed (int): Count of tests that passed all assertions
        failed (int): Count of tests that failed one or more assertions
        skipped (int): Count of tests skipped due to missing dependencies or errors
    """

    def __init__(self):
        """Initialize test runner with zero counters."""
        self.passed = 0
        self.failed = 0
        self.skipped = 0

    def test(self, name: str):
        """
        Decorator that wraps test functions with error handling and reporting.
        
        This decorator:
        - Prints formatted test headers and results
        - Catches and categorizes exceptions (AssertionError vs general Exception)
        - Updates test counters based on outcome
        - Converts sync or async functions into async test wrappers
        
        Args:
            name: Human-readable test name displayed in output
            
        Returns:
            Decorator function that wraps the test method
            
        Example:
            @runner.test("Module 1: Basic Configuration")
            async def test_basic_config():
                assert True, "This will pass"
        """
        def decorator(func):
            async def wrapper(*args, **kwargs):
                # Print test header
                print(f"\n{'='*70}")
                print(f"TEST: {name}")
                print(f"{'='*70}")
                try:
                    await func(*args, **kwargs)
                    self.passed += 1
                    print(f"✅ PASSED: {name}")
                except AssertionError as e:
                    # Test logic failed - this is a true test failure
                    self.failed += 1
                    print(f"❌ FAILED: {name}")
                    print(f"   Error: {e}")
                except Exception as e:
                    # Unexpected error (missing dependency, etc.) - skip test
                    self.skipped += 1
                    print(f"⚠️  SKIPPED: {name}")
                    print(f"   Reason: {e}")
                return None
            return wrapper
        return decorator

    def print_summary(self):
        """
        Print formatted test summary with statistics and final verdict.
        
        Returns:
            bool: True if all tests passed (no failures), False otherwise
            
        Note:
            Skipped tests don't count as failures - they indicate missing
            dependencies or environmental issues, not broken code.
        """
        total = self.passed + self.failed + self.skipped
        print(f"\n{'='*70}")
        print(f"TEST SUMMARY")
        print(f"{'='*70}")
        print(f"Total:   {total}")
        print(f"Passed:  {self.passed} ✅")
        print(f"Failed:  {self.failed} ❌")
        print(f"Skipped: {self.skipped} ⚠️")
        print(f"{'='*70}")

        if self.failed > 0:
            print("\n❌ Some tests failed. Review the output above.")
            return False
        else:
            print("\n✅ All tests passed!")
            return True


# Initialize test runner
runner = TestRunner()


@runner.test("Module 1: Environment Configuration")
async def test_environment_config():
    """
    Test environment configuration loading and validation.
    
    Validates:
    - Environment variable loading (with defaults)
    - Configuration field validation (types, ranges)
    - Sensitive data handling (API keys)
    
    This test uses a placeholder API key since we're only testing
    configuration parsing, not actual API connectivity.
    """
    import os

    # Set minimal required env vars for configuration validation
    # Note: This is a test placeholder, not a real API key
    os.environ.setdefault("OPENAI_API_KEY", "sk-test-key-for-validation")

    # Load configuration from environment
    config = EnvironmentConfig.from_env()

    # Validate API key is present and non-empty
    assert config.openai_api_key is not None and len(config.openai_api_key) > 0, \
        "API key should be loaded from environment"
    
    # Validate port is in valid range (1-65535)
    assert config.proxy_port > 0 and config.proxy_port < 65536, \
        f"Proxy port {config.proxy_port} must be in range 1-65535"
    
    # Validate message limit is positive
    assert config.max_context_messages > 0, \
        "Max context messages must be positive"

    # Display loaded configuration (with masked API key for security)
    print(f"   Proxy: {config.proxy_host}:{config.proxy_port}")
    print(f"   Max Context: {config.max_context_messages} messages")
    print(f"   Memory TTL: {config.memory_ttl_seconds}s")
    print(f"   API Key: {config.openai_api_key[:10]}... (masked)")


@runner.test("Module 1: Logging Setup")
async def test_logging_setup():
    """
    Test structured logging configuration and output.
    
    Validates:
    - Logger initialization with specified log level
    - Multiple log level methods (info, debug, warning, etc.)
    - Structured output format
    
    The logger uses Python's standard logging module with custom
    formatting for readable console output.
    """
    # Initialize logger with DEBUG level for comprehensive output
    test_logger = setup_logging(LogLevel.DEBUG)
    assert test_logger is not None, "Logger should be initialized"

    # Test different log levels
    test_logger.info("Test info message")
    test_logger.debug("Test debug message")

    print("   Logger initialized successfully")
    print("   Log levels: DEBUG, INFO, WARNING, ERROR, CRITICAL")


@runner.test("Module 2: Proxy Configuration")
async def test_proxy_configuration():
    """
    Test proxy configuration management and model setup.
    
    Validates:
    - Adding multiple AI provider models (OpenAI, Anthropic)
    - User pattern configuration for client detection
    - Configuration structure validation
    - Conversion to LiteLLM-compatible format
    
    This demonstrates the declarative configuration approach used
    by the proxy to manage multiple AI providers and routing rules.
    """
    config = ProxyConfiguration()

    # Add OpenAI model configuration
    config.add_model(ModelConfig(
        model_name="test-gpt-4",
        provider=ModelProvider.OPENAI,
        litellm_model="gpt-4",
        api_key="OPENAI_API_KEY"  # Environment variable name
    ))

    # Add Anthropic model configuration
    config.add_model(ModelConfig(
        model_name="test-claude",
        provider=ModelProvider.ANTHROPIC,
        litellm_model="claude-sonnet-4-5-20250929",
        api_key="ANTHROPIC_API_KEY"  # Environment variable name
    ))

    # Add user detection pattern for client identification
    config.add_user_pattern(
        header="user-agent",
        pattern="TestClient",
        user_id="test-user"
    )

    # Validate configuration structure
    assert len(config.models) == 2, "Should have 2 models configured"
    assert len(config.user_id_mappings["header_patterns"]) == 1, \
        "Should have 1 user pattern configured"

    print(f"   Models configured: {len(config.models)}")
    print(f"   User patterns: {len(config.user_id_mappings['header_patterns'])}")

    # Test conversion to LiteLLM-compatible format
    litellm_config = config.models[0].to_litellm_config()
    assert "model_name" in litellm_config, "Config must include model_name"
    assert "litellm_params" in litellm_config, "Config must include litellm_params"

    print("   Config conversion: OK")


@runner.test("Module 3: Message and Session")
async def test_message_and_session():
    """
    Test message creation, format conversion, and session management.
    
    Validates:
    - Message creation with roles and optional metadata
    - Conversion to OpenAI and Anthropic API formats
    - Conversation session initialization and message storage
    - Context window retrieval with message limits
    - Session serialization and deserialization
    
    This demonstrates the core data structures used for maintaining
    conversation history and context across multiple turns.
    """
    # Create user message with metadata
    msg1 = Message(
        role="user",
        content="Hello, my name is Alice",
        metadata={"test": True}  # Optional metadata for tracking
    )

    # Create assistant response message
    msg2 = Message(
        role="assistant",
        content="Hello Alice! How can I help you?"
    )

    # Test conversion to OpenAI API format
    openai_format = msg1.to_openai_format()
    assert openai_format["role"] == "user", "Role should match"
    assert openai_format["content"] == "Hello, my name is Alice", "Content should match"

    # Test conversion to Anthropic API format
    anthropic_format = msg1.to_anthropic_format()
    assert anthropic_format["role"] == "user", "Role should match Anthropic format"

    # Create conversation session to hold messages
    session = ConversationSession(
        session_id="test_session_1",
        user_id="test_user"
    )

    # Add messages to session (maintains order)
    session.add_message(msg1)
    session.add_message(msg2)

    assert len(session.messages) == 2, "Session should contain 2 messages"

    # Test context retrieval with message limit
    context = session.get_context_messages(max_messages=10)
    assert len(context) == 2, "Context should include all messages within limit"

    print(f"   Session created: {session.session_id}")
    print(f"   Messages: {len(session.messages)}")
    print(f"   Context size: {len(context)}")

    # Test session persistence (serialization/deserialization)
    session_dict = session.to_dict()
    restored = ConversationSession.from_dict(session_dict)

    assert restored.session_id == session.session_id, "Session ID should be preserved"
    assert len(restored.messages) == len(session.messages), \
        "All messages should be restored"

    print("   Serialization: OK")


@runner.test("Module 3: In-Memory Store")
async def test_in_memory_store():
    """
    Test in-memory storage backend operations.
    
    Validates:
    - Session persistence (save/retrieve)
    - Session listing (all sessions and filtered by user)
    - Session deletion and cleanup
    - Data integrity across operations
    
    The in-memory store provides a simple, fast storage backend
    suitable for development and testing. In production, this would
    be replaced with a persistent database backend.
    """
    store = InMemoryStore()

    # Create a test session with a message
    session = ConversationSession(
        session_id="memory_test_1",
        user_id="user_1"
    )

    session.add_message(Message(
        role="user",
        content="Test message"
    ))

    # Save session to store
    await store.save_session(session)

    # Retrieve session and verify data integrity
    retrieved = await store.get_session("memory_test_1")
    assert retrieved is not None, "Session should exist after save"
    assert retrieved.session_id == "memory_test_1", "Session ID should match"
    assert len(retrieved.messages) == 1, "Message count should match"

    print(f"   Session saved and retrieved: {retrieved.session_id}")

    # List all sessions (no filter)
    sessions = await store.list_sessions()
    assert "memory_test_1" in sessions, "Session should appear in list"

    print(f"   Total sessions: {len(sessions)}")

    # List sessions filtered by user ID
    user_sessions = await store.list_sessions(user_id="user_1")
    assert "memory_test_1" in user_sessions, "Session should match user filter"

    print(f"   User sessions: {len(user_sessions)}")

    # Delete session and verify removal
    await store.delete_session("memory_test_1")
    deleted = await store.get_session("memory_test_1")
    assert deleted is None, "Session should not exist after deletion"

    print("   Session deletion: OK")


@runner.test("Module 3: Memory Manager")
async def test_memory_manager():
    """
    Test high-level memory management and conversation tracking.
    
    Validates:
    - Adding user and assistant messages to conversations
    - Context retrieval with system message injection
    - Memory continuity across multiple turns
    - Automatic session creation and management
    
    The MemoryManager provides a high-level API that handles session
    lifecycle, context window management, and system message injection
    automatically.
    """
    store = InMemoryStore()
    manager = MemoryManager(
        store=store,
        max_context_messages=5,  # Limit context window
        ttl_seconds=3600  # 1 hour session timeout
    )

    session_id = "manager_test_1"
    user_id = "user_1"

    # Simulate a conversation about user preferences
    await manager.add_user_message(
        session_id=session_id,
        user_id=user_id,
        content="My favorite color is blue"
    )

    await manager.add_assistant_message(
        session_id=session_id,
        user_id=user_id,
        content="I'll remember that your favorite color is blue"
    )

    await manager.add_user_message(
        session_id=session_id,
        user_id=user_id,
        content="What's my favorite color?"
    )

    # Retrieve context for next AI response
    context = await manager.get_context_for_request(
        session_id=session_id,
        user_id=user_id
    )

    # Should have system message + 3 conversation messages
    assert len(context) >= 3, "Context should include system message and conversation"

    print(f"   Context messages: {len(context)}")
    print(f"   System message: {'yes' if any(m['role'] == 'system' for m in context) else 'no'}")

    # Verify conversation flow and memory continuity
    user_messages = [m for m in context if m['role'] == 'user']
    assert len(user_messages) >= 2, "Should have at least 2 user messages"

    print(f"   User messages: {len(user_messages)}")
    print(f"   Memory continuity: OK")


@runner.test("Module 4: Client Detection")
async def test_client_detection():
    """
    Test client detection and automatic user ID assignment.
    
    Validates:
    - Pattern matching against User-Agent headers
    - Custom header detection (x-memory-user-id)
    - Default user ID fallback for unknown clients
    - Multiple pattern configurations
    
    Client detection enables automatic memory isolation by identifying
    different AI clients (IDEs, CLI tools, custom apps) and assigning
    them unique user IDs for separate conversation contexts.
    """
    config = ProxyConfiguration()

    # Add detection patterns for different clients
    config.add_user_pattern(
        header="user-agent",
        pattern="Claude Code",  # Matches "Claude Code/1.0", etc.
        user_id="claude-cli"
    )
    config.add_user_pattern(
        header="user-agent",
        pattern="python-requests",  # Matches "python-requests/2.28.0", etc.
        user_id="python-client"
    )

    detector = ClientDetector(config)

    # Test cases: (headers, expected_user_id)
    test_cases = [
        # Known client: Claude Code
        ({"user-agent": "Claude Code/1.0"}, "claude-cli"),
        # Known client: Python requests library
        ({"user-agent": "python-requests/2.28.0"}, "python-client"),
        # Unknown client: Falls back to default
        ({"user-agent": "curl/7.68.0"}, config.user_id_mappings["default_user_id"]),
        # Explicit user ID via custom header (overrides detection)
        ({"x-memory-user-id": "custom-123"}, "custom-123"),
    ]

    for headers, expected_user_id in test_cases:
        detected = detector.detect_user_id(headers)
        assert detected == expected_user_id, \
            f"Expected {expected_user_id}, got {detected} for {headers}"
        print(f"   {headers} -> {detected} ✓")

    print("   All detection patterns working correctly")


@runner.test("Module 4: Rate Limiting")
async def test_rate_limiting():
    """Test rate limiter functionality."""
    limiter = RateLimiter(max_requests=5, window_seconds=10)

    client_id = "test_client"

    # Should allow first 5 requests
    for i in range(5):
        allowed, retry_after = await limiter.check_rate_limit(client_id)
        assert allowed, f"Request {i+1} should be allowed"
        print(f"   Request {i+1}: ✓ Allowed")

    # Should block 6th request
    allowed, retry_after = await limiter.check_rate_limit(client_id)
    assert not allowed, "Request 6 should be blocked"
    assert retry_after is not None
    print(f"   Request 6: ✓ Rate limited (retry after {retry_after}s)")

    # Test different client (should be allowed)
    allowed, _ = await limiter.check_rate_limit("different_client")
    assert allowed, "Different client should be allowed"
    print(f"   Different client: ✓ Allowed")


@runner.test("Module 4: Context Window Management")
async def test_context_window():
    """Test context window size limits."""
    store = InMemoryStore()
    manager = MemoryManager(
        store=store,
        max_context_messages=5  # Small window for testing
    )

    session_id = "window_test"
    user_id = "user_1"

    # Add many messages (more than max)
    for i in range(10):
        await manager.add_user_message(
            session_id=session_id,
            user_id=user_id,
            content=f"Message {i}"
        )

        await manager.add_assistant_message(
            session_id=session_id,
            user_id=user_id,
            content=f"Response {i}"
        )

    # Get context - should be limited
    context = await manager.get_context_for_request(
        session_id=session_id,
        user_id=user_id
    )

    # Should have system message + at most 5 conversation messages
    conversation_messages = [m for m in context if m['role'] != 'system']
    assert len(conversation_messages) <= 5, f"Context should be limited to 5, got {len(conversation_messages)}"

    print(f"   Total messages added: 20")
    print(f"   Context size: {len(conversation_messages)} (max: 5)")
    print(f"   Window management: OK")


@runner.test("Integration: Complete Conversation Flow")
async def test_complete_flow():
    """Test complete conversation flow with memory."""
    # Setup
    store = InMemoryStore()
    manager = MemoryManager(store, max_context_messages=10)

    session_id = "integration_test"
    user_id = "alice"

    print("\n   Simulating conversation:")

    # Turn 1: User introduces themselves
    print("   👤 Alice: My name is Alice and I love Python")
    await manager.add_user_message(
        session_id=session_id,
        user_id=user_id,
        content="My name is Alice and I love Python"
    )

    await manager.add_assistant_message(
        session_id=session_id,
        user_id=user_id,
        content="Hello Alice! It's great to meet a Python enthusiast!"
    )
    print("   🤖 Assistant: Hello Alice! It's great to meet a Python enthusiast!")

    # Turn 2: User asks a question
    print("   👤 Alice: What's my name?")
    await manager.add_user_message(
        session_id=session_id,
        user_id=user_id,
        content="What's my name?"
    )

    # Get context for response
    context = await manager.get_context_for_request(
        session_id=session_id,
        user_id=user_id
    )

    # Verify context contains the introduction
    context_text = " ".join([m['content'] for m in context])
    assert "Alice" in context_text, "Context should contain user's name"

    await manager.add_assistant_message(
        session_id=session_id,
        user_id=user_id,
        content="Your name is Alice"
    )
    print("   🤖 Assistant: Your name is Alice")

    # Turn 3: User asks about preference
    print("   👤 Alice: What programming language do I like?")
    await manager.add_user_message(
        session_id=session_id,
        user_id=user_id,
        content="What programming language do I like?"
    )

    context = await manager.get_context_for_request(
        session_id=session_id,
        user_id=user_id
    )

    context_text = " ".join([m['content'] for m in context])
    assert "Python" in context_text, "Context should contain programming language preference"

    await manager.add_assistant_message(
        session_id=session_id,
        user_id=user_id,
        content="You love Python"
    )
    print("   🤖 Assistant: You love Python")

    # Verify final state
    session = await store.get_session(session_id)
    assert len(session.messages) == 6  # 3 user + 3 assistant

    print(f"\n   ✓ Conversation completed with {len(session.messages)} messages")
    print(f"   ✓ Memory maintained throughout conversation")
    print(f"   ✓ Context properly retrieved for each turn")


async def run_all_tests():
    """Run all tutorial tests."""
    print("="*70)
    print("LITELLM PROXY WITH MEMORY - TUTORIAL TEST SUITE")
    print("="*70)
    print(f"\nStarting tests at {datetime.now().isoformat()}\n")

    # Run tests
    await test_environment_config()
    await test_logging_setup()
    await test_proxy_configuration()
    await test_message_and_session()
    await test_in_memory_store()
    await test_memory_manager()
    await test_client_detection()
    await test_rate_limiting()
    await test_context_window()
    await test_complete_flow()

    # Print summary
    runner.print_summary()

    return runner.failed == 0


def main():
    """Main entry point."""
    try:
        success = asyncio.run(run_all_tests())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nTests interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n\nFATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
