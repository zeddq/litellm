#!/usr/bin/env python3
"""
Follow-up test: Test Supermemory with x-sm-user-id header
"""

import asyncio
import httpx
import os

async def test_with_user_id():
    """Test Supermemory with proper user ID header."""

    api_key = os.getenv("SUPERMEMORY_API_KEY") or os.getenv("ANTHROPIC_API_KEY")

    client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)

    try:
        print("Testing Supermemory WITH x-sm-user-id header...")

        response = await client.post(
            "https://api.supermemory.ai/v3/api.anthropic.com/v1/messages",
            headers={
                "anthropic-version": "2023-06-01",
                "x-api-key": api_key,
                "x-sm-user-id": "diagnostic-test-user",  # ← ADD THIS
                "content-type": "application/json"
            },
            json={
                "model": "claude-sonnet-4-5-20250929",
                "messages": [{"role": "user", "content": "Say 'test' in one word"}],
                "max_tokens": 10
            }
        )

        print(f"Status: {response.status_code}")
        print(f"Cookies: {len(client.cookies)}")
        if client.cookies:
            print(f"Cookie names: {list(client.cookies.keys())}")

        if response.status_code == 200:
            print("✅ SUCCESS! Supermemory works with x-sm-user-id header")
            data = response.json()
            print(f"Response: {data}")
        elif response.status_code == 503:
            print("❌ 503 - Supermemory is down")
            print(f"Body: {response.text[:500]}")
        elif response.status_code == 429:
            print("❌ 429 - Rate limited")
            print(f"Body: {response.text[:500]}")
        else:
            print(f"❌ Status {response.status_code}")
            print(f"Body: {response.text[:500]}")

        return response.status_code

    finally:
        await client.aclose()

if __name__ == "__main__":
    asyncio.run(test_with_user_id())