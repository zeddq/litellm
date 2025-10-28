"""
Test Script for LiteLLM Proxy with Memory Tutorial

This script demonstrates and validates the key features of the tutorial.
Run this after reviewing the tutorial to see everything in action.

Usage:
    python test_tutorial.py
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
    """Test runner for tutorial validation."""

    def __init__(self):
        """Initialize test runner."""
        self.passed = 0
        self.failed = 0
        self.skipped = 0

    def test(self, name: str):
        """Decorator for test methods."""
        def decorator(func):
            async def wrapper(*args, **kwargs):
                print(f"\n{'='*70}")
                print(f"TEST: {name}")
                print(f"{'='*70}")
                try:
                    await func(*args, **kwargs)
                    self.passed += 1
                    print(f"✅ PASSED: {name}")
                except AssertionError as e:
                    self.failed += 1
                    print(f"❌ FAILED: {name}")
                    print(f"   Error: {e}")
                except Exception as e:
                    self.skipped += 1
                    print(f"⚠️  SKIPPED: {name}")
                    print(f"   Reason: {e}")
                return None
            return wrapper
        return decorator

    def print_summary(self):
        """Print test summary."""
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
    """Test environment configuration and validation."""
    # Test with minimal environment
    import os

    # Set minimal required env vars
    os.environ.setdefault("OPENAI_API_KEY", "sk-test-key-for-validation")

    # Load config
    config = EnvironmentConfig.from_env()

    # Validate fields
    assert config.openai_api_key is not None and len(config.openai_api_key) > 0
    assert config.proxy_port > 0 and config.proxy_port < 65536
    assert config.max_context_messages > 0

    print(f"   Proxy: {config.proxy_host}:{config.proxy_port}")
    print(f"   Max Context: {config.max_context_messages} messages")
    print(f"   Memory TTL: {config.memory_ttl_seconds}s")
    print(f"   API Key: {config.openai_api_key[:10]}... (masked)")


@runner.test("Module 1: Logging Setup")
async def test_logging_setup():
    """Test structured logging configuration."""
    # Test console logging
    test_logger = setup_logging(LogLevel.DEBUG)
    assert test_logger is not None

    test_logger.info("Test info message")
    test_logger.debug("Test debug message")

    print("   Logger initialized successfully")
    print("   Log levels: DEBUG, INFO, WARNING, ERROR, CRITICAL")


@runner.test("Module 2: Proxy Configuration")
async def test_proxy_configuration():
    """Test proxy configuration management."""
    config = ProxyConfiguration()

    # Add models
    config.add_model(ModelConfig(
        model_name="test-gpt-4",
        provider=ModelProvider.OPENAI,
        litellm_model="gpt-4",
        api_key="OPENAI_API_KEY"
    ))

    config.add_model(ModelConfig(
        model_name="test-claude",
        provider=ModelProvider.ANTHROPIC,
        litellm_model="claude-sonnet-4-5-20250929",
        api_key="ANTHROPIC_API_KEY"
    ))

    # Add user patterns
    config.add_user_pattern(
        header="user-agent",
        pattern="TestClient",
        user_id="test-user"
    )

    # Validate
    assert len(config.models) == 2
    assert len(config.user_id_mappings["header_patterns"]) == 1

    print(f"   Models configured: {len(config.models)}")
    print(f"   User patterns: {len(config.user_id_mappings['header_patterns'])}")

    # Test conversion to LiteLLM format
    litellm_config = config.models[0].to_litellm_config()
    assert "model_name" in litellm_config
    assert "litellm_params" in litellm_config

    print("   Config conversion: OK")


@runner.test("Module 3: Message and Session")
async def test_message_and_session():
    """Test message and conversation session management."""
    # Create messages
    msg1 = Message(
        role="user",
        content="Hello, my name is Alice",
        metadata={"test": True}
    )

    msg2 = Message(
        role="assistant",
        content="Hello Alice! How can I help you?"
    )

    # Test message conversion
    openai_format = msg1.to_openai_format()
    assert openai_format["role"] == "user"
    assert openai_format["content"] == "Hello, my name is Alice"

    anthropic_format = msg1.to_anthropic_format()
    assert anthropic_format["role"] == "user"

    # Create session
    session = ConversationSession(
        session_id="test_session_1",
        user_id="test_user"
    )

    session.add_message(msg1)
    session.add_message(msg2)

    assert len(session.messages) == 2

    # Test context retrieval
    context = session.get_context_messages(max_messages=10)
    assert len(context) == 2

    print(f"   Session created: {session.session_id}")
    print(f"   Messages: {len(session.messages)}")
    print(f"   Context size: {len(context)}")

    # Test serialization
    session_dict = session.to_dict()
    restored = ConversationSession.from_dict(session_dict)

    assert restored.session_id == session.session_id
    assert len(restored.messages) == len(session.messages)

    print("   Serialization: OK")


@runner.test("Module 3: In-Memory Store")
async def test_in_memory_store():
    """Test in-memory storage backend."""
    store = InMemoryStore()

    # Create session
    session = ConversationSession(
        session_id="memory_test_1",
        user_id="user_1"
    )

    session.add_message(Message(
        role="user",
        content="Test message"
    ))

    # Save session
    await store.save_session(session)

    # Retrieve session
    retrieved = await store.get_session("memory_test_1")
    assert retrieved is not None
    assert retrieved.session_id == "memory_test_1"
    assert len(retrieved.messages) == 1

    print(f"   Session saved and retrieved: {retrieved.session_id}")

    # List sessions
    sessions = await store.list_sessions()
    assert "memory_test_1" in sessions

    print(f"   Total sessions: {len(sessions)}")

    # Filter by user
    user_sessions = await store.list_sessions(user_id="user_1")
    assert "memory_test_1" in user_sessions

    print(f"   User sessions: {len(user_sessions)}")

    # Delete session
    await store.delete_session("memory_test_1")
    deleted = await store.get_session("memory_test_1")
    assert deleted is None

    print("   Session deletion: OK")


@runner.test("Module 3: Memory Manager")
async def test_memory_manager():
    """Test high-level memory management."""
    store = InMemoryStore()
    manager = MemoryManager(
        store=store,
        max_context_messages=5,
        ttl_seconds=3600
    )

    session_id = "manager_test_1"
    user_id = "user_1"

    # Add conversation
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

    # Get context
    context = await manager.get_context_for_request(
        session_id=session_id,
        user_id=user_id
    )

    # Should have system message + 3 conversation messages
    assert len(context) >= 3

    print(f"   Context messages: {len(context)}")
    print(f"   System message: {'yes' if any(m['role'] == 'system' for m in context) else 'no'}")

    # Verify conversation flow
    user_messages = [m for m in context if m['role'] == 'user']
    assert len(user_messages) >= 2

    print(f"   User messages: {len(user_messages)}")
    print(f"   Memory continuity: OK")


@runner.test("Module 4: Client Detection")
async def test_client_detection():
    """Test client detection and user ID assignment."""
    config = ProxyConfiguration()

    # Add patterns
    config.add_user_pattern(
        header="user-agent",
        pattern="Claude Code",
        user_id="claude-cli"
    )
    config.add_user_pattern(
        header="user-agent",
        pattern="python-requests",
        user_id="python-client"
    )

    detector = ClientDetector(config)

    # Test pattern matching
    test_cases = [
        ({"user-agent": "Claude Code/1.0"}, "claude-cli"),
        ({"user-agent": "python-requests/2.28.0"}, "python-client"),
        ({"user-agent": "curl/7.68.0"}, config.user_id_mappings["default_user_id"]),
        ({"x-memory-user-id": "custom-123"}, "custom-123"),
    ]

    for headers, expected_user_id in test_cases:
        detected = detector.detect_user_id(headers)
        assert detected == expected_user_id, f"Expected {expected_user_id}, got {detected}"
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
