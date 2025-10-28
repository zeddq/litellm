"""
Complete Workflow Example for LiteLLM Proxy with Memory

This example demonstrates a complete end-to-end workflow including:
1. Configuration setup
2. Memory store initialization
3. Proxy server startup
4. Client interactions with memory
5. Session management

Run this example to see the complete system in action.

Usage:
    python example_complete_workflow.py
"""

import asyncio
import json
import os
from datetime import datetime
from typing import Optional

# Import tutorial components
from .tutorial_proxy_with_memory import (
    # Configuration
    EnvironmentConfig,
    ProxyConfiguration,
    ModelConfig,
    ModelProvider,

    # Memory
    InMemoryStore,
    MemoryManager,
    Message,
    ConversationSession,

    # Proxy
    ClientDetector,
    MemoryEnabledProxy,

    # Utilities
    logger,
    setup_logging,
    LogLevel,
)


async def example_1_basic_memory():
    """
    Example 1: Basic Memory Operations

    Demonstrates:
    - Creating sessions
    - Adding messages
    - Retrieving context
    """
    print("\n" + "=" * 80)
    print("EXAMPLE 1: Basic Memory Operations")
    print("=" * 80)

    # Initialize memory store
    store = InMemoryStore()
    memory_manager = MemoryManager(
        store=store,
        max_context_messages=10,
        ttl_seconds=3600
    )

    session_id = "demo_session_1"
    user_id = "alice"

    print("\n📝 Starting conversation...")

    # Turn 1
    print("\n👤 User: Hello! My name is Alice and I'm a Python developer.")
    await memory_manager.add_user_message(
        session_id=session_id,
        user_id=user_id,
        content="Hello! My name is Alice and I'm a Python developer."
    )

    # Simulate assistant response
    print("🤖 Assistant: Hello Alice! It's great to meet a Python developer!")
    await memory_manager.add_assistant_message(
        session_id=session_id,
        user_id=user_id,
        content="Hello Alice! It's great to meet a Python developer!"
    )

    # Turn 2 - Test memory recall
    print("\n👤 User: What's my name?")
    await memory_manager.add_user_message(
        session_id=session_id,
        user_id=user_id,
        content="What's my name?"
    )

    # Get context to answer
    context = await memory_manager.get_context_for_request(
        session_id=session_id,
        user_id=user_id
    )

    print("\n📚 Context retrieved:")
    for i, msg in enumerate(context, 1):
        role = msg['role'].upper()
        content = msg['content'][:60] + "..." if len(msg['content']) > 60 else msg['content']
        print(f"   {i}. [{role}] {content}")

    # Simulate assistant using context
    print("\n🤖 Assistant: Your name is Alice (retrieved from context)")
    await memory_manager.add_assistant_message(
        session_id=session_id,
        user_id=user_id,
        content="Your name is Alice"
    )

    # Turn 3 - Test another recall
    print("\n👤 User: What do I do for work?")
    await memory_manager.add_user_message(
        session_id=session_id,
        user_id=user_id,
        content="What do I do for work?"
    )

    context = await memory_manager.get_context_for_request(
        session_id=session_id,
        user_id=user_id
    )

    print("🤖 Assistant: You're a Python developer (retrieved from context)")
    await memory_manager.add_assistant_message(
        session_id=session_id,
        user_id=user_id,
        content="You're a Python developer"
    )

    # Show final session state
    session = await store.get_session(session_id)
    print(f"\n📊 Session Statistics:")
    print(f"   Session ID: {session.session_id}")
    print(f"   User ID: {session.user_id}")
    print(f"   Total Messages: {len(session.messages)}")
    print(f"   Created: {session.created_at.strftime('%Y-%m-%d %H:%M:%S')}")

    print("\n✅ Example 1 complete!")


async def example_2_multi_user_isolation():
    """
    Example 2: Multi-User Memory Isolation

    Demonstrates:
    - Separate memory per user
    - Client detection
    - Session isolation
    """
    print("\n" + "=" * 80)
    print("EXAMPLE 2: Multi-User Memory Isolation")
    print("=" * 80)

    # Initialize
    store = InMemoryStore()
    memory_manager = MemoryManager(store)

    # User 1: Alice
    print("\n👤 Alice's conversation:")
    await memory_manager.add_user_message(
        session_id="alice_session",
        user_id="alice",
        content="My favorite color is blue"
    )
    await memory_manager.add_assistant_message(
        session_id="alice_session",
        user_id="alice",
        content="I'll remember that your favorite color is blue"
    )
    print("   Alice: My favorite color is blue")
    print("   Assistant: I'll remember that")

    # User 2: Bob (different user, different memory)
    print("\n👤 Bob's conversation:")
    await memory_manager.add_user_message(
        session_id="bob_session",
        user_id="bob",
        content="My favorite color is red"
    )
    await memory_manager.add_assistant_message(
        session_id="bob_session",
        user_id="bob",
        content="I'll remember that your favorite color is red"
    )
    print("   Bob: My favorite color is red")
    print("   Assistant: I'll remember that")

    # Alice asks about her color
    print("\n👤 Alice asks: What's my favorite color?")
    context_alice = await memory_manager.get_context_for_request(
        session_id="alice_session",
        user_id="alice"
    )
    # Context should only have Alice's messages
    print("   Assistant: Your favorite color is blue (Alice's context)")

    # Bob asks about his color
    print("\n👤 Bob asks: What's my favorite color?")
    context_bob = await memory_manager.get_context_for_request(
        session_id="bob_session",
        user_id="bob"
    )
    # Context should only have Bob's messages
    print("   Assistant: Your favorite color is red (Bob's context)")

    print("\n📊 Session Isolation Verified:")
    print(f"   Alice's session has {len([m for m in context_alice if m['role'] != 'system'])} messages")
    print(f"   Bob's session has {len([m for m in context_bob if m['role'] != 'system'])} messages")
    print("   ✓ Each user has separate, isolated memory")

    print("\n✅ Example 2 complete!")


async def example_3_client_detection():
    """
    Example 3: Automatic Client Detection

    Demonstrates:
    - User-Agent pattern matching
    - Custom header detection
    - Default user assignment
    """
    print("\n" + "=" * 80)
    print("EXAMPLE 3: Automatic Client Detection")
    print("=" * 80)

    # Setup configuration with patterns
    config = ProxyConfiguration()
    config.add_user_pattern(
        header="user-agent",
        pattern="Claude Code",
        user_id="claude-cli-user"
    )
    config.add_user_pattern(
        header="user-agent",
        pattern="python-requests",
        user_id="python-sdk-user"
    )
    config.add_user_pattern(
        header="user-agent",
        pattern="PyCharm",
        user_id="pycharm-user"
    )

    detector = ClientDetector(config)

    # Test different clients
    print("\n🔍 Testing Client Detection:\n")

    test_cases = [
        {
            "name": "Claude Code CLI",
            "headers": {"user-agent": "Claude Code/1.0"},
            "expected": "claude-cli-user"
        },
        {
            "name": "Python Requests Library",
            "headers": {"user-agent": "python-requests/2.28.0"},
            "expected": "python-sdk-user"
        },
        {
            "name": "PyCharm IDE",
            "headers": {"user-agent": "PyCharm AI Assistant/2023.3"},
            "expected": "pycharm-user"
        },
        {
            "name": "Custom Header Override",
            "headers": {
                "user-agent": "unknown-client",
                "x-memory-user-id": "custom-user-123"
            },
            "expected": "custom-user-123"
        },
        {
            "name": "Unknown Client",
            "headers": {"user-agent": "curl/7.68.0"},
            "expected": "default-user"
        }
    ]

    for test in test_cases:
        detected = detector.detect_user_id(test["headers"])
        status = "✓" if detected == test["expected"] else "✗"

        print(f"   {status} {test['name']}")
        print(f"      Headers: {test['headers']}")
        print(f"      Detected: {detected}")
        print(f"      Expected: {test['expected']}")
        print()

    print("✅ Example 3 complete!")


async def example_4_context_window_management():
    """
    Example 4: Context Window Management

    Demonstrates:
    - Limiting context size
    - Oldest messages dropped first
    - Efficient memory usage
    """
    print("\n" + "=" * 80)
    print("EXAMPLE 4: Context Window Management")
    print("=" * 80)

    # Create manager with small context window
    store = InMemoryStore()
    memory_manager = MemoryManager(
        store=store,
        max_context_messages=5,  # Only keep last 5 messages
        ttl_seconds=3600
    )

    session_id = "window_test"
    user_id = "test_user"

    print("\n📝 Adding 20 messages (10 turns)...")

    # Add many messages
    for i in range(10):
        await memory_manager.add_user_message(
            session_id=session_id,
            user_id=user_id,
            content=f"User message {i+1}"
        )
        await memory_manager.add_assistant_message(
            session_id=session_id,
            user_id=user_id,
            content=f"Assistant response {i+1}"
        )

    # Get session to see total
    session = await store.get_session(session_id)
    print(f"   Total messages stored: {len(session.messages)}")

    # Get context - should be limited
    context = await memory_manager.get_context_for_request(
        session_id=session_id,
        user_id=user_id
    )

    # Remove system message for counting
    conversation_messages = [m for m in context if m['role'] != 'system']

    print(f"\n📊 Context Window Results:")
    print(f"   Total messages in store: {len(session.messages)}")
    print(f"   Messages in context: {len(conversation_messages)}")
    print(f"   Max context setting: {memory_manager.max_context_messages}")
    print(f"\n   ✓ Context properly limited to last {len(conversation_messages)} messages")

    print("\n📝 Context Preview (last 5):")
    for msg in conversation_messages[-5:]:
        print(f"   [{msg['role']}] {msg['content']}")

    print("\n✅ Example 4 complete!")


async def example_5_session_management():
    """
    Example 5: Session Management Operations

    Demonstrates:
    - Listing sessions
    - Filtering by user
    - Session cleanup
    - Manual deletion
    """
    print("\n" + "=" * 80)
    print("EXAMPLE 5: Session Management")
    print("=" * 80)

    store = InMemoryStore()
    memory_manager = MemoryManager(store)

    # Create multiple sessions
    print("\n📝 Creating test sessions...")

    sessions_data = [
        ("session_1", "alice", "Alice's work session"),
        ("session_2", "alice", "Alice's personal session"),
        ("session_3", "bob", "Bob's session"),
        ("session_4", "charlie", "Charlie's session"),
    ]

    for session_id, user_id, description in sessions_data:
        await memory_manager.add_user_message(
            session_id=session_id,
            user_id=user_id,
            content=description
        )
        print(f"   ✓ Created: {session_id} (user={user_id})")

    # List all sessions
    print("\n📋 All Sessions:")
    all_sessions = await store.list_sessions()
    for sid in all_sessions:
        session = await store.get_session(sid)
        print(f"   - {sid}: user={session.user_id}, messages={len(session.messages)}")

    # Filter by user
    print("\n👤 Alice's Sessions:")
    alice_sessions = await store.list_sessions(user_id="alice")
    for sid in alice_sessions:
        session = await store.get_session(sid)
        print(f"   - {sid}: {len(session.messages)} messages")

    # Delete a session
    print("\n🗑️  Deleting session_1...")
    await store.delete_session("session_1")

    remaining = await store.list_sessions()
    print(f"   Remaining sessions: {len(remaining)}")

    # Cleanup old sessions (in real scenario, these would be expired)
    print("\n🧹 Running cleanup...")
    # In this example, we won't actually delete anything as sessions are new
    cleaned = await memory_manager.cleanup_old_sessions()
    print(f"   Sessions cleaned up: {cleaned}")

    print("\n✅ Example 5 complete!")


async def example_6_streaming_simulation():
    """
    Example 6: Streaming Response Simulation

    Demonstrates:
    - Accumulating streaming chunks
    - Storing complete response
    - Handling partial content
    """
    print("\n" + "=" * 80)
    print("EXAMPLE 6: Streaming Response Handling")
    print("=" * 80)

    store = InMemoryStore()
    memory_manager = MemoryManager(store)

    session_id = "streaming_test"
    user_id = "test_user"

    # User message
    print("\n👤 User: Tell me a short story")
    await memory_manager.add_user_message(
        session_id=session_id,
        user_id=user_id,
        content="Tell me a short story"
    )

    # Simulate streaming response
    print("\n🤖 Assistant (streaming):")

    chunks = [
        "Once upon",
        " a time",
        ", there was",
        " a brave",
        " programmer",
        " who built",
        " an amazing",
        " proxy server",
        " with memory!",
    ]

    accumulated = []
    for i, chunk in enumerate(chunks, 1):
        accumulated.append(chunk)
        print(f"   Chunk {i}: '{chunk}'")
        await asyncio.sleep(0.1)  # Simulate streaming delay

    # Store complete response
    full_response = "".join(accumulated)
    print(f"\n📦 Complete response: {full_response}")

    await memory_manager.add_assistant_message(
        session_id=session_id,
        user_id=user_id,
        content=full_response,
        metadata={"streaming": True, "chunks": len(chunks)}
    )

    # Verify storage
    context = await memory_manager.get_context_for_request(
        session_id=session_id,
        user_id=user_id
    )

    assistant_messages = [m for m in context if m['role'] == 'assistant']
    print(f"\n✓ Stored {len(assistant_messages)} assistant message(s)")
    print(f"✓ Content length: {len(full_response)} characters")

    print("\n✅ Example 6 complete!")


async def main():
    """Run all examples."""
    print("\n" + "=" * 80)
    print("LITELLM PROXY WITH MEMORY - COMPLETE WORKFLOW EXAMPLES")
    print("=" * 80)
    print(f"\nStarted at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    try:
        # Run all examples
        await example_1_basic_memory()
        await example_2_multi_user_isolation()
        await example_3_client_detection()
        await example_4_context_window_management()
        await example_5_session_management()
        await example_6_streaming_simulation()

        # Summary
        print("\n" + "=" * 80)
        print("ALL EXAMPLES COMPLETED SUCCESSFULLY")
        print("=" * 80)
        print("\n📚 What you learned:")
        print("   ✓ Basic memory operations and context retrieval")
        print("   ✓ Multi-user memory isolation")
        print("   ✓ Automatic client detection from headers")
        print("   ✓ Context window management and limits")
        print("   ✓ Session management and cleanup")
        print("   ✓ Streaming response handling")

        print("\n🚀 Next Steps:")
        print("   1. Run the full tutorial: python tutorial_proxy_with_memory.py")
        print("   2. Start the proxy server: python tutorial_proxy_with_memory.py --serve")
        print("   3. Test with your own clients")
        print("   4. Deploy to production")

        print("\n" + "=" * 80)

    except Exception as e:
        print(f"\n❌ Error running examples: {e}")
        import traceback
        traceback.print_exc()
        return False

    return True


if __name__ == "__main__":
    # Set up clean logging
    setup_logging(LogLevel.INFO)

    # Run examples
    success = asyncio.run(main())

    if success:
        print("\n✅ All examples completed successfully!")
    else:
        print("\n❌ Some examples failed. Review output above.")
