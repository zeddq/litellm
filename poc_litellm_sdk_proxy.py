#!/usr/bin/env python3
"""
PROOF OF CONCEPT: LiteLLM SDK with Persistent Sessions

This POC tests:
1. Can we inject custom httpx.AsyncClient into LiteLLM SDK?
2. Do cookies persist across requests?
3. Does Cloudflare accept the persistent session?
4. Do we retain LiteLLM features?
"""

import asyncio
import httpx
import litellm
import os
import json
from datetime import datetime

# Configure LiteLLM
litellm.set_verbose = True  # Detailed logging

class PersistentSessionManager:
    """
    Manages persistent httpx.AsyncClient for LiteLLM SDK.

    This ensures cookies (like cf_clearance) persist across all requests.
    """

    def __init__(self):
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(600.0),
            follow_redirects=True,
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20)
        )
        print(f"🍪 Created persistent httpx.AsyncClient (id: {id(self.client)})")

    async def close(self):
        """Close the persistent client."""
        await self.client.aclose()
        print("🔒 Closed persistent client")


async def test_sdk_with_persistent_session():
    """Test LiteLLM SDK with our persistent session."""

    print("=" * 70)
    print("PROOF OF CONCEPT: LiteLLM SDK + Persistent Sessions")
    print("=" * 70)

    # Create persistent session manager
    session_manager = PersistentSessionManager()

    # Inject into LiteLLM SDK
    print("\n1️⃣  Injecting persistent client into LiteLLM SDK...")
    litellm.aclient_session = session_manager.client
    print(f"   ✅ Injected client id: {id(litellm.aclient_session)}")

    # Configure Supermemory model
    print("\n2️⃣  Configuring Supermemory model...")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    supermemory_key = os.getenv("SUPERMEMORY_API_KEY")

    if not anthropic_key or not supermemory_key:
        print("   ❌ Missing API keys!")
        print("   Set ANTHROPIC_API_KEY and SUPERMEMORY_API_KEY")
        return

    print(f"   Anthropic key: {anthropic_key[:20]}...")
    print(f"   Supermemory key: {supermemory_key[:20]}...")

    # Test 1: Single request
    print("\n3️⃣  TEST 1: Single request through SDK")
    print("   " + "-" * 60)

    try:
        response1 = await litellm.acompletion(
            model="anthropic/claude-sonnet-4-5-20250929",
            messages=[{"role": "user", "content": "Say 'test 1' only"}],
            max_tokens=10,
            api_base="https://api.supermemory.ai/v3/api.anthropic.com",
            api_key=anthropic_key,
            extra_headers={
                "x-supermemory-api-key": supermemory_key,
                "x-sm-user-id": "poc-test-user"
            }
        )

        cookie_count = len(session_manager.client.cookies)
        print(f"   ✅ Request succeeded!")
        print(f"   📊 Status: Success")
        print(f"   🍪 Cookies: {cookie_count}")

        if cookie_count > 0:
            print(f"   🍪 Cookie names: {list(session_manager.client.cookies.keys())}")
            cf_cookies = [name for name in session_manager.client.cookies.keys() if 'cf' in name.lower()]
            if cf_cookies:
                print(f"   ☁️  Cloudflare cookies: {cf_cookies}")

        print(f"   💬 Response: {response1.choices[0].message.content}")

    except litellm.ServiceUnavailableError as e:
        print(f"   ❌ 503 Service Unavailable: {e}")
        print(f"   🍪 Cookies: {len(session_manager.client.cookies)}")
        return False

    except litellm.RateLimitError as e:
        print(f"   ❌ 429 Rate Limited: {e}")
        print(f"   🍪 Cookies: {len(session_manager.client.cookies)}")
        return False

    except Exception as e:
        print(f"   ❌ Error: {type(e).__name__}: {e}")
        print(f"   🍪 Cookies: {len(session_manager.client.cookies)}")
        return False

    # Test 2: Multiple consecutive requests (cookie persistence test)
    print("\n4️⃣  TEST 2: Multiple requests (cookie persistence)")
    print("   " + "-" * 60)

    for i in range(3):
        print(f"\n   Request {i+1}/3:")

        try:
            response = await litellm.acompletion(
                model="anthropic/claude-sonnet-4-5-20250929",
                messages=[{"role": "user", "content": f"Say 'test {i+1}' only"}],
                max_tokens=10,
                api_base="https://api.supermemory.ai/v3/api.anthropic.com",
                api_key=anthropic_key,
                extra_headers={
                    "x-supermemory-api-key": supermemory_key,
                    "x-sm-user-id": "poc-test-user"
                }
            )

            cookie_count = len(session_manager.client.cookies)
            print(f"   ✅ Success! Cookies: {cookie_count}")

            # Verify same client is being used
            if id(litellm.aclient_session) == id(session_manager.client):
                print(f"   ✅ Same client reused (persistent session working)")
            else:
                print(f"   ⚠️  WARNING: Different client detected!")

        except Exception as e:
            print(f"   ❌ Failed: {type(e).__name__}: {str(e)[:100]}")
            print(f"   🍪 Cookies: {len(session_manager.client.cookies)}")

        # Small delay between requests
        await asyncio.sleep(1)

    # Final stats
    print("\n5️⃣  FINAL STATISTICS")
    print("   " + "-" * 60)
    print(f"   Client ID: {id(session_manager.client)}")
    print(f"   LiteLLM client ID: {id(litellm.aclient_session)}")
    print(f"   Same client: {id(session_manager.client) == id(litellm.aclient_session)}")
    print(f"   Total cookies: {len(session_manager.client.cookies)}")

    if session_manager.client.cookies:
        print(f"   Cookie details:")
        for name, value in session_manager.client.cookies.items():
            print(f"     - {name}: {value[:20]}..." if len(value) > 20 else f"     - {name}: {value}")

    # Cleanup
    await session_manager.close()

    print("\n" + "=" * 70)
    print("POC COMPLETE")
    print("=" * 70)

    return True


async def test_comparison():
    """Compare with and without persistent sessions."""

    print("\n" + "=" * 70)
    print("COMPARISON TEST: With vs Without Persistent Sessions")
    print("=" * 70)

    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    supermemory_key = os.getenv("SUPERMEMORY_API_KEY")

    # Test A: Without persistent session (LiteLLM creates new clients)
    print("\n🔴 Test A: WITHOUT Persistent Session")
    print("   (LiteLLM creates new clients internally)")
    print("   " + "-" * 60)

    litellm.aclient_session = None  # Let LiteLLM manage clients

    try:
        response = await litellm.acompletion(
            model="anthropic/claude-sonnet-4-5-20250929",
            messages=[{"role": "user", "content": "Test without persistent session"}],
            max_tokens=10,
            api_base="https://api.supermemory.ai/v3/api.anthropic.com",
            api_key=anthropic_key,
            extra_headers={
                "x-supermemory-api-key": supermemory_key,
                "x-sm-user-id": "test-no-persistence"
            }
        )
        print("   ✅ Succeeded (but cookies likely not persisted)")

    except litellm.ServiceUnavailableError:
        print("   ❌ 503 - Cloudflare blocked (no cookie persistence)")

    except Exception as e:
        print(f"   ❌ Error: {type(e).__name__}")

    # Test B: With persistent session
    print("\n🟢 Test B: WITH Persistent Session")
    print("   (We control the httpx.AsyncClient)")
    print("   " + "-" * 60)

    persistent_client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)
    litellm.aclient_session = persistent_client

    try:
        response = await litellm.acompletion(
            model="anthropic/claude-sonnet-4-5-20250929",
            messages=[{"role": "user", "content": "Test with persistent session"}],
            max_tokens=10,
            api_base="https://api.supermemory.ai/v3/api.anthropic.com",
            api_key=anthropic_key,
            extra_headers={
                "x-supermemory-api-key": supermemory_key,
                "x-sm-user-id": "test-with-persistence"
            }
        )
        print(f"   ✅ Succeeded! Cookies: {len(persistent_client.cookies)}")

    except litellm.ServiceUnavailableError:
        print(f"   ❌ 503 - But check cookies: {len(persistent_client.cookies)}")

    except Exception as e:
        print(f"   ❌ Error: {type(e).__name__}")

    finally:
        await persistent_client.aclose()


if __name__ == "__main__":
    print(f"\n{'='*70}")
    print(f"LiteLLM SDK Persistent Session POC")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}\n")

    # Check dependencies
    print("📦 Dependencies:")
    try:
        import importlib.metadata
        version = importlib.metadata.version("litellm")
        print(f"   litellm version: {version}")
    except:
        print(f"   litellm: installed")
    print(f"   httpx: available ✅")

    # Run main test
    asyncio.run(test_sdk_with_persistent_session())

    # Optional: Run comparison
    # asyncio.run(test_comparison())
