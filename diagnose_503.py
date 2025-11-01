#!/usr/bin/env python3
"""
503 Error Diagnostic Script

This script tests various components to identify the root cause of 503 errors:
1. Direct Supermemory API connectivity
2. LiteLLM binary health and configuration
3. Memory Proxy forwarding
4. Network and cookie behavior
"""

import asyncio
import httpx
import json
import os
import sys
from datetime import datetime
from typing import Optional, Dict, Any

# ANSI color codes for output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"
BOLD = "\033[1m"


def print_header(text: str):
    """Print section header."""
    print(f"\n{BOLD}{BLUE}{'=' * 70}{RESET}")
    print(f"{BOLD}{BLUE}{text}{RESET}")
    print(f"{BOLD}{BLUE}{'=' * 70}{RESET}\n")


def print_success(text: str):
    """Print success message."""
    print(f"{GREEN}✅ {text}{RESET}")


def print_error(text: str):
    """Print error message."""
    print(f"{RED}❌ {text}{RESET}")


def print_warning(text: str):
    """Print warning message."""
    print(f"{YELLOW}⚠️  {text}{RESET}")


def print_info(text: str):
    """Print info message."""
    print(f"{BLUE}ℹ️  {text}{RESET}")


async def test_direct_supermemory():
    """Test 1: Direct connection to Supermemory API."""
    print_header("TEST 1: Direct Supermemory API Connection")

    # Check for API key
    api_key = os.getenv("SUPERMEMORY_API_KEY")
    if not api_key:
        api_key = os.getenv("ANTHROPIC_API_KEY")  # Fallback

    if not api_key:
        print_error("No API key found! Set SUPERMEMORY_API_KEY or ANTHROPIC_API_KEY")
        return {"success": False, "error": "No API key"}

    print_info(f"Using API key: {api_key[:15]}...")

    # Create client with cookie tracking
    client = httpx.AsyncClient(
        timeout=30.0,
        follow_redirects=True
    )

    try:
        print_info("Sending request to https://api.supermemory.ai/v3/api.anthropic.com/v1/messages")

        response = await client.post(
            "https://api.supermemory.ai/v3/api.anthropic.com/v1/messages",
            headers={
                "anthropic-version": "2023-06-01",
                "x-api-key": api_key,
                "content-type": "application/json"
            },
            json={
                "model": "claude-sonnet-4-5-20250929",
                "messages": [{"role": "user", "content": "Hello, this is a diagnostic test"}],
                "max_tokens": 50
            }
        )

        print_info(f"Response Status: {response.status_code}")
        print_info(f"Response Headers: {dict(response.headers)}")

        # Check for cookies
        cookie_count = len(client.cookies)
        print_info(f"Cookies received: {cookie_count}")
        if cookie_count > 0:
            print_info(f"Cookie names: {list(client.cookies.keys())}")

            # Check specifically for Cloudflare cookies
            cf_cookies = [name for name in client.cookies.keys() if 'cf' in name.lower()]
            if cf_cookies:
                print_success(f"Cloudflare cookies detected: {cf_cookies}")
            else:
                print_warning("No Cloudflare-specific cookies found")

        # Analyze response
        if response.status_code == 200:
            print_success("Direct Supermemory connection works!")
            try:
                data = response.json()
                print_info(f"Response type: {data.get('type', 'unknown')}")
                if 'content' in data:
                    print_info(f"Got valid response content")
            except:
                print_warning("Response not JSON")
            return {"success": True, "status": 200, "cookies": cookie_count}

        elif response.status_code == 429:
            print_error("Rate limited by Supermemory (429)")
            print_info(f"Response body: {response.text[:500]}")
            return {"success": False, "status": 429, "error": "Rate limited"}

        elif response.status_code == 503:
            print_error("Service unavailable (503) from Supermemory")
            print_info(f"Response body: {response.text[:500]}")
            return {"success": False, "status": 503, "error": "Service unavailable"}

        elif response.status_code in [401, 403]:
            print_error(f"Authentication error ({response.status_code})")
            print_info(f"Response body: {response.text[:500]}")
            return {"success": False, "status": response.status_code, "error": "Auth error"}

        else:
            print_error(f"Unexpected status code: {response.status_code}")
            print_info(f"Response body: {response.text[:500]}")
            return {"success": False, "status": response.status_code}

    except httpx.ConnectError as e:
        print_error(f"Connection error: {e}")
        return {"success": False, "error": f"Connection failed: {e}"}

    except httpx.TimeoutException as e:
        print_error(f"Request timeout: {e}")
        return {"success": False, "error": "Timeout"}

    except Exception as e:
        print_error(f"Unexpected error: {type(e).__name__}: {e}")
        return {"success": False, "error": str(e)}

    finally:
        await client.aclose()


async def test_litellm_binary_health():
    """Test 2: LiteLLM binary health check."""
    print_header("TEST 2: LiteLLM Binary Health Check")

    litellm_url = "http://localhost:4000"
    print_info(f"Testing LiteLLM binary at {litellm_url}")

    client = httpx.AsyncClient(timeout=10.0)

    try:
        # Test /health endpoint
        print_info("Checking /health endpoint...")
        response = await client.get(f"{litellm_url}/health")

        if response.status_code == 200:
            print_success("LiteLLM binary is healthy")
            print_info(f"Response: {response.text}")
            return {"success": True, "healthy": True}
        else:
            print_error(f"Unexpected health status: {response.status_code}")
            return {"success": False, "healthy": False, "status": response.status_code}

    except httpx.ConnectError:
        print_error("Cannot connect to LiteLLM binary!")
        print_warning("Is LiteLLM running on port 4000?")
        print_info("Start it with: poetry run start-proxies")
        return {"success": False, "error": "Connection refused"}

    except Exception as e:
        print_error(f"Error: {e}")
        return {"success": False, "error": str(e)}

    finally:
        await client.aclose()


async def test_litellm_models():
    """Test 3: Check available models in LiteLLM."""
    print_header("TEST 3: LiteLLM Available Models")

    litellm_url = "http://localhost:4000"
    client = httpx.AsyncClient(timeout=10.0)

    try:
        print_info("Fetching /v1/models...")
        response = await client.get(
            f"{litellm_url}/v1/models",
            headers={"Authorization": "Bearer sk-1234"}
        )

        if response.status_code == 200:
            print_success("Successfully retrieved models list")
            data = response.json()

            if 'data' in data:
                models = data['data']
                print_info(f"Found {len(models)} models:")

                for model in models:
                    model_id = model.get('id', 'unknown')
                    print(f"  - {model_id}")

                # Check if claude-sonnet-4.5 is available
                claude_models = [m for m in models if 'claude' in m.get('id', '').lower()]
                if claude_models:
                    print_success(f"Found {len(claude_models)} Claude models")
                else:
                    print_warning("No Claude models found in model list")

                return {"success": True, "models": [m.get('id') for m in models]}
            else:
                print_warning("Unexpected response format")
                return {"success": True, "models": []}

        else:
            print_error(f"Failed to get models: {response.status_code}")
            return {"success": False, "status": response.status_code}

    except Exception as e:
        print_error(f"Error: {e}")
        return {"success": False, "error": str(e)}

    finally:
        await client.aclose()


async def test_litellm_completion():
    """Test 4: Send actual completion request through LiteLLM binary."""
    print_header("TEST 4: LiteLLM Binary Completion Request")

    litellm_url = "http://localhost:4000"
    client = httpx.AsyncClient(timeout=60.0)

    try:
        print_info("Sending completion request through LiteLLM binary...")

        response = await client.post(
            f"{litellm_url}/v1/chat/completions",
            headers={
                "Authorization": "Bearer sk-1234",
                "Content-Type": "application/json"
            },
            json={
                "model": "claude-sonnet-4.5",
                "messages": [{"role": "user", "content": "Say 'test' in one word"}],
                "max_tokens": 10
            }
        )

        print_info(f"Response Status: {response.status_code}")
        print_info(f"Response Headers: {dict(response.headers)}")

        if response.status_code == 200:
            print_success("LiteLLM binary successfully completed request!")
            data = response.json()
            print_info(f"Response: {json.dumps(data, indent=2)[:500]}")
            return {"success": True, "status": 200}

        elif response.status_code == 503:
            print_error("503 Service Unavailable from LiteLLM binary!")
            print_info(f"Response body: {response.text[:1000]}")

            # Try to parse error message
            try:
                error_data = response.json()
                print_warning(f"Error details: {json.dumps(error_data, indent=2)}")
            except:
                print_warning("Could not parse error response as JSON")

            return {"success": False, "status": 503, "body": response.text[:500]}

        elif response.status_code == 429:
            print_error("429 Rate Limited by LiteLLM binary")
            print_info(f"Response body: {response.text[:500]}")
            return {"success": False, "status": 429}

        else:
            print_error(f"Unexpected status: {response.status_code}")
            print_info(f"Response body: {response.text[:500]}")
            return {"success": False, "status": response.status_code}

    except Exception as e:
        print_error(f"Error: {e}")
        return {"success": False, "error": str(e)}

    finally:
        await client.aclose()


async def test_memory_proxy():
    """Test 5: Send request through Memory Proxy."""
    print_header("TEST 5: Memory Proxy Forwarding")

    proxy_url = "http://localhost:8764"
    client = httpx.AsyncClient(timeout=60.0)

    try:
        # First check if proxy is running
        print_info("Checking if Memory Proxy is running...")
        try:
            health_response = await client.get(f"{proxy_url}/health")
            if health_response.status_code == 200:
                print_success("Memory Proxy is running")
            else:
                print_warning(f"Proxy health returned: {health_response.status_code}")
        except httpx.ConnectError:
            print_error("Memory Proxy is not running on port 8764!")
            print_info("Start it with: poetry run start-proxies")
            return {"success": False, "error": "Proxy not running"}

        # Test memory routing info
        print_info("\nChecking memory routing...")
        routing_response = await client.get(
            f"{proxy_url}/memory-routing/info",
            headers={"User-Agent": "DiagnosticScript/1.0"}
        )

        if routing_response.status_code == 200:
            routing_data = routing_response.json()
            print_success("Memory routing configured")
            print_info(f"User ID: {routing_data.get('user_id')}")
            print_info(f"Is default: {routing_data.get('is_default')}")

        # Send actual completion request
        print_info("\nSending completion request through Memory Proxy...")

        response = await client.post(
            f"{proxy_url}/v1/chat/completions",
            headers={
                "Authorization": "Bearer sk-1234",
                "Content-Type": "application/json",
                "User-Agent": "DiagnosticScript/1.0"
            },
            json={
                "model": "claude-sonnet-4.5",
                "messages": [{"role": "user", "content": "Say 'test' in one word"}],
                "max_tokens": 10
            }
        )

        print_info(f"Response Status: {response.status_code}")

        if response.status_code == 200:
            print_success("Memory Proxy successfully forwarded request!")
            data = response.json()
            print_info(f"Response: {json.dumps(data, indent=2)[:500]}")
            return {"success": True, "status": 200}

        elif response.status_code == 503:
            print_error("503 from Memory Proxy!")
            print_warning("This is the error you've been seeing")
            print_info(f"Response body: {response.text[:1000]}")
            return {"success": False, "status": 503, "body": response.text[:500]}

        else:
            print_error(f"Unexpected status: {response.status_code}")
            print_info(f"Response body: {response.text[:500]}")
            return {"success": False, "status": response.status_code}

    except Exception as e:
        print_error(f"Error: {e}")
        return {"success": False, "error": str(e)}

    finally:
        await client.aclose()


async def check_config_file():
    """Test 6: Analyze config.yaml."""
    print_header("TEST 6: Configuration Analysis")

    config_path = "config/config.yaml"

    if not os.path.exists(config_path):
        print_error(f"Config file not found: {config_path}")
        return {"success": False, "error": "Config not found"}

    print_success(f"Found config file: {config_path}")

    try:
        import yaml

        with open(config_path) as f:
            config = yaml.safe_load(f)

        print_info("\nAnalyzing configuration...")

        # Check model_list
        if 'model_list' in config:
            models = config['model_list']
            print_info(f"Found {len(models)} models configured")

            # Find claude-sonnet-4.5
            for model in models:
                if model.get('model_name') == 'claude-sonnet-4.5':
                    print_success("Found claude-sonnet-4.5 configuration:")
                    print(f"\n{json.dumps(model, indent=2)}\n")

                    # Check critical fields
                    params = model.get('litellm_params', {})
                    api_base = params.get('api_base', '')
                    api_key = params.get('api_key', '')
                    model_name = params.get('model', '')

                    if 'supermemory.ai' in api_base:
                        print_success("Model is configured to use Supermemory")
                        print_info(f"API Base: {api_base}")
                    else:
                        print_warning("Model is NOT using Supermemory proxy")

                    if api_key.startswith('os.environ/'):
                        env_var = api_key.replace('os.environ/', '')
                        actual_key = os.getenv(env_var)
                        if actual_key:
                            print_success(f"API key from {env_var}: {actual_key[:15]}...")
                        else:
                            print_error(f"Environment variable {env_var} is not set!")

                    print_info(f"Model identifier: {model_name}")

                    return {
                        "success": True,
                        "uses_supermemory": 'supermemory.ai' in api_base,
                        "api_base": api_base,
                        "model": model_name
                    }

            print_warning("claude-sonnet-4.5 not found in model list!")
            print_info("Available models:")
            for model in models:
                print(f"  - {model.get('model_name')}")

        else:
            print_error("No model_list in config!")

        return {"success": True}

    except Exception as e:
        print_error(f"Error reading config: {e}")
        return {"success": False, "error": str(e)}


async def main():
    """Run all diagnostic tests."""
    print(f"\n{BOLD}{'=' * 70}")
    print("503 ERROR DIAGNOSTIC REPORT")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'=' * 70}{RESET}\n")

    results = {}

    # Test 1: Direct Supermemory
    results['supermemory'] = await test_direct_supermemory()

    # Test 2: LiteLLM binary health
    results['litellm_health'] = await test_litellm_binary_health()

    # Only continue if LiteLLM is running
    if results['litellm_health'].get('success'):
        # Test 3: LiteLLM models
        results['litellm_models'] = await test_litellm_models()

        # Test 4: LiteLLM completion
        results['litellm_completion'] = await test_litellm_completion()

        # Test 5: Memory Proxy
        results['memory_proxy'] = await test_memory_proxy()

    # Test 6: Config analysis
    results['config'] = await check_config_file()

    # Generate summary
    print_header("DIAGNOSTIC SUMMARY")

    print("\n📊 Test Results:")
    print(f"  Supermemory Direct:      {'✅' if results['supermemory'].get('success') else '❌'}")
    print(f"  LiteLLM Binary Health:   {'✅' if results['litellm_health'].get('success') else '❌'}")

    if results['litellm_health'].get('success'):
        print(f"  LiteLLM Models:          {'✅' if results.get('litellm_models', {}).get('success') else '❌'}")
        print(f"  LiteLLM Completion:      {'✅' if results.get('litellm_completion', {}).get('success') else '❌'}")
        print(f"  Memory Proxy:            {'✅' if results.get('memory_proxy', {}).get('success') else '❌'}")

    print(f"  Config File:             {'✅' if results['config'].get('success') else '❌'}")

    # Diagnosis
    print("\n🔍 Root Cause Analysis:")

    supermemory_works = results['supermemory'].get('success')
    litellm_works = results.get('litellm_completion', {}).get('success')
    proxy_works = results.get('memory_proxy', {}).get('success')

    if not supermemory_works:
        status = results['supermemory'].get('status', 'unknown')
        print_error(f"Direct Supermemory connection fails with status {status}")

        if status == 503:
            print_warning("Supermemory API itself is returning 503!")
            print_warning("This is NOT a cookie issue - Supermemory is down/unavailable")
            print_info("Recommendation: Wait for Supermemory to recover or contact support")

        elif status == 429:
            print_warning("Supermemory is rate limiting your API key")
            print_info("Recommendation: Implement Solution A (Direct Calls with cookie persistence)")

        elif status in [401, 403]:
            print_error("API key authentication problem")
            print_info("Check your SUPERMEMORY_API_KEY or ANTHROPIC_API_KEY")

    elif supermemory_works and not litellm_works:
        print_warning("Supermemory works directly, but LiteLLM binary fails")
        print_info("Problem: LiteLLM binary configuration or Supermemory proxy compatibility")
        print_info("Recommendation: Use Solution A (Direct Supermemory calls, bypass binary)")

    elif supermemory_works and litellm_works and not proxy_works:
        print_warning("Both work separately, but Memory Proxy forwarding fails")
        print_info("Problem: Memory Proxy forwarding logic")
        print_info("Check Memory Proxy logs for errors")

    elif supermemory_works and litellm_works and proxy_works:
        print_success("All components working!")
        print_info("The 503 errors you saw may have been transient")

    # Cookie analysis
    if supermemory_works:
        cookie_count = results['supermemory'].get('cookies', 0)
        if cookie_count == 0:
            print_info("\nℹ️  Note: No cookies received from Supermemory")
            print_info("This suggests Cloudflare is NOT challenging your requests")
            print_info("The 503 errors are likely NOT cookie-related")

    print(f"\n{BOLD}{'=' * 70}{RESET}\n")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nDiagnostic interrupted by user")
        sys.exit(1)