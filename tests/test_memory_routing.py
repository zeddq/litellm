"""
Test script for Memory Routing functionality

Run this to validate the routing logic before deploying.
"""

import sys
import json
from proxy.memory_router import MemoryRouter

# Test cases
TEST_CASES = [
    {
        "name": "PyCharm AI Chat",
        "headers": {
            "user-agent": "OpenAIClientImpl/Java unknown",
            "x-stainless-lang": "java",
            "authorization": "Bearer sk-1234"
        },
        "expected_user_id": "pycharm-ai-chat"
    },
    {
        "name": "Claude Code Python SDK",
        "headers": {
            "user-agent": "anthropic-sdk-python/0.8.0",
            "anthropic-version": "2023-06-01",
            "authorization": "Bearer sk-1234"
        },
        "expected_user_id": "claude-code"
    },
    {
        "name": "Claude Code CLI",
        "headers": {
            "user-agent": "Claude Code/1.0.0",
            "authorization": "Bearer sk-1234"
        },
        "expected_user_id": "claude-code-cli"
    },
    {
        "name": "Custom Header - Project Alpha",
        "headers": {
            "user-agent": "MyApp/1.0",
            "x-memory-user-id": "project-alpha",
            "authorization": "Bearer sk-1234"
        },
        "expected_user_id": "project-alpha"
    },
    {
        "name": "Custom Header - Mobile App",
        "headers": {
            "user-agent": "MobileApp/2.1",
            "x-memory-user-id": "mobile-app-prod",
            "authorization": "Bearer sk-1234"
        },
        "expected_user_id": "mobile-app-prod"
    },
    {
        "name": "Unknown Client (Default)",
        "headers": {
            "user-agent": "curl/7.68.0",
            "authorization": "Bearer sk-1234"
        },
        "expected_user_id": "default-dev"
    },
    {
        "name": "Custom App without Pattern",
        "headers": {
            "user-agent": "RandomApp/3.0",
            "authorization": "Bearer sk-1234"
        },
        "expected_user_id": "default-dev"
    }
]


def test_routing():
    """Test all routing cases."""
    print("=" * 70)
    print("MEMORY ROUTING TEST SUITE")
    print("=" * 70)
    print()

    # Initialize router
    try:
        router = MemoryRouter("config.yaml")
        print("✓ Router initialized successfully")
        print()
    except Exception as e:
        print(f"✗ Failed to initialize router: {e}")
        return False

    passed = 0
    failed = 0
    results = []

    for test_case in TEST_CASES:
        name = test_case["name"]
        headers = test_case["headers"]
        expected = test_case["expected_user_id"]

        print("-" * 70)
        print(f"Test: {name}")
        print("-" * 70)

        # Get routing info
        routing_info = router.get_routing_info(headers)
        actual = routing_info["user_id"]

        # Display headers
        print("Headers:")
        for key, value in headers.items():
            if key.lower() not in ['authorization']:
                print(f"  {key}: {value}")

        # Display routing decision
        print(f"\nExpected User ID: {expected}")
        print(f"Actual User ID:   {actual}")

        # Check match
        if actual == expected:
            print("✓ PASS")
            passed += 1
            result = "PASS"
        else:
            print("✗ FAIL")
            failed += 1
            result = "FAIL"

        # Display routing details
        if routing_info.get("matched_pattern"):
            pattern = routing_info["matched_pattern"]
            print(f"\nMatched Pattern:")
            print(f"  Header: {pattern['header']}")
            print(f"  Value: {pattern['value']}")
            print(f"  Pattern: {pattern['pattern']}")

        if routing_info.get("custom_header_present"):
            print(f"\nCustom Header Present: Yes")

        if routing_info.get("is_default"):
            print(f"\nUsing Default: Yes")

        print()

        results.append({
            "name": name,
            "expected": expected,
            "actual": actual,
            "result": result
        })

    # Summary
    print("=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    print(f"Total:  {len(TEST_CASES)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print()

    if failed > 0:
        print("Failed Tests:")
        for r in results:
            if r["result"] == "FAIL":
                print(f"  - {r['name']}: expected '{r['expected']}', got '{r['actual']}'")
        print()

    success = failed == 0
    if success:
        print("✓ All tests passed!")
    else:
        print("✗ Some tests failed")

    return success


def test_header_injection():
    """Test header injection."""
    print("\n" + "=" * 70)
    print("HEADER INJECTION TEST")
    print("=" * 70)
    print()

    router = MemoryRouter("config.yaml")

    test_headers = {
        "user-agent": "OpenAIClientImpl/Java unknown",
        "content-type": "application/json",
        "authorization": "Bearer sk-1234"
    }

    print("Original Headers:")
    for key, value in test_headers.items():
        if key.lower() != 'authorization':
            print(f"  {key}: {value}")

    # Inject memory headers
    injected = router.inject_memory_headers(test_headers, "sm_test_key")

    print("\nInjected Headers:")
    for key, value in injected.items():
        if key.lower() not in ['authorization', 'x-supermemory-api-key']:
            print(f"  {key}: {value}")
        elif key == 'x-sm-user-id':
            print(f"  {key}: {value}")
        elif key == 'x-supermemory-api-key':
            print(f"  {key}: sm_***")

    # Verify injection
    assert 'x-sm-user-id' in injected, "x-sm-user-id not injected"
    assert 'x-supermemory-api-key' in injected, "x-supermemory-api-key not injected"
    assert injected['x-sm-user-id'] == 'pycharm-ai-chat', "Wrong user ID"

    print("\n✓ Header injection test passed")
    return True


def test_model_detection():
    """Test Supermemory model detection."""
    print("\n" + "=" * 70)
    print("MODEL DETECTION TEST")
    print("=" * 70)
    print()

    router = MemoryRouter("config.yaml")

    models = [
        ("claude-sonnet-4.5", True, "Should use Supermemory"),
        ("gpt-5-pro", False, "Should not use Supermemory"),
        ("gpt-5-codex", False, "Should not use Supermemory"),
        ("gemini-2.5-pro", False, "Should not use Supermemory")
    ]

    all_passed = True
    for model_name, expected, description in models:
        result = router.should_use_supermemory(model_name)
        status = "✓" if result == expected else "✗"
        print(f"{status} {model_name}: {description} - {result}")
        if result != expected:
            all_passed = False

    if all_passed:
        print("\n✓ All model detection tests passed")
    else:
        print("\n✗ Some model detection tests failed")

    return all_passed


def main():
    """Run all tests."""
    try:
        test1 = test_routing()
        test2 = test_header_injection()
        test3 = test_model_detection()

        print("\n" + "=" * 70)
        print("FINAL RESULT")
        print("=" * 70)

        if test1 and test2 and test3:
            print("✓ ALL TESTS PASSED")
            return 0
        else:
            print("✗ SOME TESTS FAILED")
            return 1

    except FileNotFoundError:
        print("✗ config.yaml not found")
        print("Make sure you're running from the litellm directory")
        return 1
    except Exception as e:
        print(f"✗ Test suite error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
