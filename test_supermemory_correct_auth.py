#!/usr/bin/env python3
"""
Test Supermemory with CORRECT authentication headers.

Supermemory requires:
1. x-api-key: Your Anthropic API key (for Claude)
2. x-supermemory-api-key: Your Supermemory API key (for proxy access)
3. x-sm-user-id: User ID for memory isolation
"""

import asyncio
import httpx
import os

async def test_correct_auth():
    """Test with all required headers."""

    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    supermemory_key = os.getenv("SUPERMEMORY_API_KEY")

    print(f"Anthropic Key: {anthropic_key[:20]}...")
    print(f"Supermemory Key: {supermemory_key[:20]}...")

    client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)

    try:
        print("\nTesting Supermemory with FULL authentication...")

        response = await client.post(
            "https://api.supermemory.ai/v3/api.anthropic.com/v1/messages",
            headers={
                "anthropic-version": "2023-06-01",
                "x-api-key": anthropic_key,                     # ← Anthropic API key
                "x-supermemory-api-key": supermemory_key,       # ← Supermemory API key
                "x-sm-user-id": "diagnostic-test-user",         # ← User ID for memory
                "content-type": "application/json"
            },
            json={
                "model": "claude-sonnet-4-5-20250929",
                "messages": [{"role": "user", "content": "Say 'test' in one word only"}],
                "max_tokens": 10
            }
        )

        print(f"\n📊 Status: {response.status_code}")
        print(f"🍪 Cookies: {len(client.cookies)}")

        if client.cookies:
            print(f"🍪 Cookie names: {list(client.cookies.keys())}")
            cf_cookies = [name for name in client.cookies.keys() if 'cf' in name.lower()]
            if cf_cookies:
                print(f"☁️  Cloudflare cookies: {cf_cookies}")

        print(f"\n📋 Response Headers:")
        for key in ['cf-ray', 'cf-cache-status', 'server', 'x-request-id']:
            if key in response.headers:
                print(f"  {key}: {response.headers[key]}")

        if response.status_code == 200:
            print("\n✅ SUCCESS! Supermemory works correctly!")
            data = response.json()
            print(f"\nResponse content:")
            if 'content' in data:
                for content in data['content']:
                    if content.get('type') == 'text':
                        print(f"  Text: {content.get('text')}")
            print(f"\nFull response: {data}")

            return True

        elif response.status_code == 503:
            print("\n❌ 503 - Service Unavailable")
            print(f"Body: {response.text[:1000]}")

            # Check if it's Cloudflare or Supermemory
            if 'cloudflare' in response.text.lower():
                print("\n🔍 This is a CLOUDFLARE 503 error")
                print("   → Cloudflare is rate limiting/blocking requests")
                print("   → Cookie persistence solution needed (Solution A)")
            else:
                print("\n🔍 This is a SUPERMEMORY 503 error")
                print("   → Supermemory API is down or overloaded")
                print("   → Wait or contact Supermemory support")

            return False

        elif response.status_code == 429:
            print("\n❌ 429 - Rate Limited")
            print(f"Body: {response.text[:1000]}")

            # Check rate limit headers
            if 'retry-after' in response.headers:
                print(f"   Retry after: {response.headers['retry-after']} seconds")

            return False

        elif response.status_code in [401, 403]:
            print(f"\n❌ {response.status_code} - Authentication Error")
            print(f"Body: {response.text[:500]}")
            print("\nCheck your API keys:")
            print("  - ANTHROPIC_API_KEY should be your Anthropic API key")
            print("  - SUPERMEMORY_API_KEY should be your Supermemory API key")

            return False

        else:
            print(f"\n❌ Unexpected status: {response.status_code}")
            print(f"Body: {response.text[:1000]}")

            return False

    except httpx.ConnectError as e:
        print(f"\n❌ Connection Error: {e}")
        print("Cannot reach Supermemory API - check network connectivity")
        return False

    except httpx.TimeoutException:
        print("\n❌ Request Timeout")
        print("Supermemory took too long to respond")
        return False

    except Exception as e:
        print(f"\n❌ Error: {type(e).__name__}: {e}")
        return False

    finally:
        await client.aclose()


async def test_multiple_requests():
    """Test cookie persistence with multiple requests."""

    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    supermemory_key = os.getenv("SUPERMEMORY_API_KEY")

    # Use PERSISTENT session
    client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)

    print("\n" + "="*70)
    print("Testing COOKIE PERSISTENCE with multiple requests")
    print("="*70)

    try:
        for i in range(3):
            print(f"\n📤 Request {i+1}/3...")

            response = await client.post(
                "https://api.supermemory.ai/v3/api.anthropic.com/v1/messages",
                headers={
                    "anthropic-version": "2023-06-01",
                    "x-api-key": anthropic_key,
                    "x-supermemory-api-key": supermemory_key,
                    "x-sm-user-id": "diagnostic-test-user",
                    "content-type": "application/json"
                },
                json={
                    "model": "claude-sonnet-4-5-20250929",
                    "messages": [{"role": "user", "content": f"Test {i+1}"}],
                    "max_tokens": 5
                }
            )

            cookie_count = len(client.cookies)
            print(f"   Status: {response.status_code}, Cookies: {cookie_count}")

            if response.status_code == 200:
                print(f"   ✅ Success")
            elif response.status_code == 429:
                print(f"   ⚠️  Rate limited")
            elif response.status_code == 503:
                print(f"   ❌ Service unavailable")

            # Small delay between requests
            await asyncio.sleep(1)

        print(f"\n🍪 Final cookie count: {len(client.cookies)}")
        if client.cookies:
            print(f"🍪 Cookies: {list(client.cookies.keys())}")

    finally:
        await client.aclose()


if __name__ == "__main__":
    print("="*70)
    print("SUPERMEMORY AUTHENTICATION TEST")
    print("="*70)

    # Test 1: Single request with correct auth
    success = asyncio.run(test_correct_auth())

    if success:
        # Test 2: Multiple requests for cookie persistence
        asyncio.run(test_multiple_requests())
    else:
        print("\n⚠️  Skipping cookie persistence test due to authentication failure")