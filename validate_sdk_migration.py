#!/usr/bin/env python3
"""
SDK Migration Validation Script

Validates the SDK-based proxy migration with comprehensive checks:
1. Pre-migration: Binary proxy functionality
2. Post-migration: SDK proxy functionality
3. Feature parity verification
4. Performance comparison
5. Rollback readiness

Usage:
    python validate_sdk_migration.py --phase pre
    python validate_sdk_migration.py --phase post
    python validate_sdk_migration.py --phase all
    python validate_sdk_migration.py --phase rollback

Exit Codes:
    0 - All checks passed
    1 - Some checks failed (details in output)
    2 - Critical failure (cannot proceed)
"""

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Dict, Any, Optional

import httpx


# =============================================================================
# Configuration
# =============================================================================


class ValidationPhase(Enum):
    """Validation phases."""

    PRE = "pre"  # Before migration
    POST = "post"  # After migration
    ALL = "all"  # Full validation
    ROLLBACK = "rollback"  # Verify rollback capability


@dataclass
class ValidationResult:
    """Result of a validation check."""

    name: str
    passed: bool
    message: str
    details: Optional[Dict[str, Any]] = None
    critical: bool = False


@dataclass
class ValidationConfig:
    """Configuration for validation."""

    binary_proxy_url: str = "http://localhost:8765"
    sdk_proxy_url: str = "http://localhost:8764"
    config_path: str = "config/config.yaml"
    master_key: str = "sk-1234"
    timeout: float = 30.0


# =============================================================================
# Validation Checks
# =============================================================================


class ValidationSuite:
    """Suite of validation checks."""

    def __init__(self, config: ValidationConfig):
        self.config = config
        self.results: List[ValidationResult] = []

    def add_result(self, result: ValidationResult):
        """Add a validation result."""
        self.results.append(result)

        # Print result immediately
        status = "✅ PASS" if result.passed else "❌ FAIL"
        critical_mark = " [CRITICAL]" if result.critical else ""
        print(f"{status}{critical_mark}: {result.name}")
        print(f"   {result.message}")

        if result.details:
            for key, value in result.details.items():
                print(f"   - {key}: {value}")
        print()

    async def check_health(self, url: str, name: str) -> ValidationResult:
        """Check if proxy health endpoint responds."""
        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                response = await client.get(f"{url}/health")

                if response.status_code == 200:
                    data = response.json()
                    return ValidationResult(
                        name=f"{name} Health Check",
                        passed=True,
                        message=f"{name} is healthy",
                        details={
                            "status": data.get("status"),
                            "models": data.get("models_configured", "N/A"),
                        },
                    )
                else:
                    return ValidationResult(
                        name=f"{name} Health Check",
                        passed=False,
                        message=f"Health check returned {response.status_code}",
                        critical=True,
                    )

        except Exception as e:
            return ValidationResult(
                name=f"{name} Health Check",
                passed=False,
                message=f"Health check failed: {str(e)}",
                critical=True,
            )

    async def check_models_list(self, url: str, name: str) -> ValidationResult:
        """Check if models list endpoint works."""
        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                headers = {"Authorization": f"Bearer {self.config.master_key}"}
                response = await client.get(f"{url}/v1/models", headers=headers)

                if response.status_code == 200:
                    data = response.json()
                    models = data.get("data", [])
                    model_ids = [m["id"] for m in models]

                    return ValidationResult(
                        name=f"{name} Models List",
                        passed=True,
                        message=f"Found {len(models)} models",
                        details={"models": ", ".join(model_ids)},
                    )
                else:
                    return ValidationResult(
                        name=f"{name} Models List",
                        passed=False,
                        message=f"Models list returned {response.status_code}",
                    )

        except Exception as e:
            return ValidationResult(
                name=f"{name} Models List",
                passed=False,
                message=f"Models list failed: {str(e)}",
            )

    async def check_memory_routing(self, url: str, name: str) -> ValidationResult:
        """Check memory routing functionality."""
        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                # Test default user
                response1 = await client.get(
                    f"{url}/memory-routing/info",
                    headers={"User-Agent": "test-client/1.0"},
                )

                # Test PyCharm client
                response2 = await client.get(
                    f"{url}/memory-routing/info",
                    headers={"User-Agent": "OpenAIClientImpl/Java"},
                )

                # Test custom user ID
                response3 = await client.get(
                    f"{url}/memory-routing/info",
                    headers={
                        "User-Agent": "test/1.0",
                        "x-memory-user-id": "custom-user",
                    },
                )

                if all(r.status_code == 200 for r in [response1, response2, response3]):
                    data1 = response1.json()
                    data2 = response2.json()
                    data3 = response3.json()

                    # Verify routing logic
                    default_user = data1["routing"]["user_id"]
                    pycharm_user = data2["routing"]["user_id"]
                    custom_user = data3["routing"]["user_id"]

                    passed = (
                        default_user == "default-dev"
                        and pycharm_user == "pycharm-ai"
                        and custom_user == "custom-user"
                    )

                    return ValidationResult(
                        name=f"{name} Memory Routing",
                        passed=passed,
                        message="Memory routing works correctly" if passed else "Memory routing logic incorrect",
                        details={
                            "default_user": default_user,
                            "pycharm_user": pycharm_user,
                            "custom_user": custom_user,
                        },
                    )
                else:
                    return ValidationResult(
                        name=f"{name} Memory Routing",
                        passed=False,
                        message="Memory routing endpoints not accessible",
                    )

        except Exception as e:
            return ValidationResult(
                name=f"{name} Memory Routing",
                passed=False,
                message=f"Memory routing check failed: {str(e)}",
            )

    async def check_authentication(self, url: str, name: str) -> ValidationResult:
        """Check authentication enforcement."""
        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                # Test without auth
                response1 = await client.get(f"{url}/v1/models")

                # Test with invalid key
                response2 = await client.get(
                    f"{url}/v1/models",
                    headers={"Authorization": "Bearer invalid-key"},
                )

                # Test with valid key
                response3 = await client.get(
                    f"{url}/v1/models",
                    headers={"Authorization": f"Bearer {self.config.master_key}"},
                )

                # Verify auth enforcement
                passed = (
                    response1.status_code == 401
                    and response2.status_code == 401
                    and response3.status_code == 200
                )

                return ValidationResult(
                    name=f"{name} Authentication",
                    passed=passed,
                    message="Authentication works correctly" if passed else "Authentication enforcement issues",
                    details={
                        "no_auth": response1.status_code,
                        "invalid_key": response2.status_code,
                        "valid_key": response3.status_code,
                    },
                )

        except Exception as e:
            return ValidationResult(
                name=f"{name} Authentication",
                passed=False,
                message=f"Authentication check failed: {str(e)}",
            )

    async def compare_performance(self) -> ValidationResult:
        """Compare performance between binary and SDK proxies."""
        try:
            test_payload = {
                "model": "gpt-4",
                "messages": [{"role": "user", "content": "Hi"}],
                "max_tokens": 5,
            }
            headers = {
                "Authorization": f"Bearer {self.config.master_key}",
                "Content-Type": "application/json",
            }

            # Note: This requires mocking or real API keys
            # For now, just measure proxy overhead
            num_requests = 10

            # Measure binary proxy
            binary_times = []
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                for _ in range(num_requests):
                    start = time.time()
                    try:
                        await client.get(
                            f"{self.config.binary_proxy_url}/health",
                            headers=headers,
                        )
                        elapsed = time.time() - start
                        binary_times.append(elapsed)
                    except:
                        pass

            # Measure SDK proxy
            sdk_times = []
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                for _ in range(num_requests):
                    start = time.time()
                    try:
                        await client.get(
                            f"{self.config.sdk_proxy_url}/health",
                            headers=headers,
                        )
                        elapsed = time.time() - start
                        sdk_times.append(elapsed)
                    except:
                        pass

            if binary_times and sdk_times:
                binary_avg = sum(binary_times) / len(binary_times) * 1000
                sdk_avg = sum(sdk_times) / len(sdk_times) * 1000

                return ValidationResult(
                    name="Performance Comparison",
                    passed=True,
                    message="Performance comparison completed",
                    details={
                        "binary_avg_ms": f"{binary_avg:.2f}",
                        "sdk_avg_ms": f"{sdk_avg:.2f}",
                        "sdk_faster": sdk_avg < binary_avg,
                    },
                )
            else:
                return ValidationResult(
                    name="Performance Comparison",
                    passed=False,
                    message="Could not measure performance (proxies not running?)",
                )

        except Exception as e:
            return ValidationResult(
                name="Performance Comparison",
                passed=False,
                message=f"Performance comparison failed: {str(e)}",
            )

    def check_config_exists(self) -> ValidationResult:
        """Check if configuration file exists."""
        config_path = Path(self.config.config_path)

        if config_path.exists():
            return ValidationResult(
                name="Configuration File",
                passed=True,
                message=f"Config found at {config_path}",
            )
        else:
            return ValidationResult(
                name="Configuration File",
                passed=False,
                message=f"Config not found at {config_path}",
                critical=True,
            )

    def check_sdk_components(self) -> ValidationResult:
        """Check if SDK components exist."""
        required_files = [
            "src/proxy/litellm_proxy_sdk.py",
            "src/proxy/session_manager.py",
            "src/proxy/config_parser.py",
            "src/proxy/error_handlers.py",
            "src/proxy/streaming_utils.py",
        ]

        missing_files = []
        for file_path in required_files:
            if not Path(file_path).exists():
                missing_files.append(file_path)

        if not missing_files:
            return ValidationResult(
                name="SDK Components",
                passed=True,
                message=f"All {len(required_files)} SDK components present",
            )
        else:
            return ValidationResult(
                name="SDK Components",
                passed=False,
                message=f"{len(missing_files)} components missing",
                details={"missing": missing_files},
                critical=True,
            )

    def check_binary_proxy_intact(self) -> ValidationResult:
        """Check if binary proxy files are intact."""
        required_files = [
            "src/proxy/litellm_proxy_with_memory.py",
            "src/proxy/memory_router.py",
        ]

        missing_files = []
        for file_path in required_files:
            if not Path(file_path).exists():
                missing_files.append(file_path)

        if not missing_files:
            return ValidationResult(
                name="Binary Proxy Intact",
                passed=True,
                message="Binary proxy files present",
            )
        else:
            return ValidationResult(
                name="Binary Proxy Intact",
                passed=False,
                message=f"{len(missing_files)} binary proxy files missing",
                details={"missing": missing_files},
                critical=True,
            )


# =============================================================================
# Validation Phases
# =============================================================================


async def run_pre_migration_validation(config: ValidationConfig):
    """Run pre-migration validation checks."""
    print("=" * 70)
    print("PRE-MIGRATION VALIDATION")
    print("=" * 70)
    print("Validating binary proxy before migration...\n")

    suite = ValidationSuite(config)

    # File checks
    suite.add_result(suite.check_config_exists())
    suite.add_result(suite.check_binary_proxy_intact())

    # Binary proxy checks
    suite.add_result(await suite.check_health(config.binary_proxy_url, "Binary Proxy"))
    suite.add_result(await suite.check_models_list(config.binary_proxy_url, "Binary Proxy"))
    suite.add_result(await suite.check_memory_routing(config.binary_proxy_url, "Binary Proxy"))
    suite.add_result(await suite.check_authentication(config.binary_proxy_url, "Binary Proxy"))

    return suite


async def run_post_migration_validation(config: ValidationConfig):
    """Run post-migration validation checks."""
    print("=" * 70)
    print("POST-MIGRATION VALIDATION")
    print("=" * 70)
    print("Validating SDK proxy after migration...\n")

    suite = ValidationSuite(config)

    # File checks
    suite.add_result(suite.check_config_exists())
    suite.add_result(suite.check_sdk_components())
    suite.add_result(suite.check_binary_proxy_intact())

    # SDK proxy checks
    suite.add_result(await suite.check_health(config.sdk_proxy_url, "SDK Proxy"))
    suite.add_result(await suite.check_models_list(config.sdk_proxy_url, "SDK Proxy"))
    suite.add_result(await suite.check_memory_routing(config.sdk_proxy_url, "SDK Proxy"))
    suite.add_result(await suite.check_authentication(config.sdk_proxy_url, "SDK Proxy"))

    # Feature parity
    suite.add_result(await suite.compare_performance())

    return suite


async def run_full_validation(config: ValidationConfig):
    """Run full validation (pre + post)."""
    print("=" * 70)
    print("FULL MIGRATION VALIDATION")
    print("=" * 70)
    print("Validating both proxies for feature parity...\n")

    # Run both phases
    pre_suite = await run_pre_migration_validation(config)
    print("\n")
    post_suite = await run_post_migration_validation(config)

    # Combine results
    all_results = pre_suite.results + post_suite.results
    return all_results


async def run_rollback_validation(config: ValidationConfig):
    """Verify rollback capability."""
    print("=" * 70)
    print("ROLLBACK VALIDATION")
    print("=" * 70)
    print("Verifying rollback readiness...\n")

    suite = ValidationSuite(config)

    # Check binary proxy still works
    suite.add_result(suite.check_binary_proxy_intact())
    suite.add_result(await suite.check_health(config.binary_proxy_url, "Binary Proxy"))
    suite.add_result(await suite.check_models_list(config.binary_proxy_url, "Binary Proxy"))

    return suite


# =============================================================================
# Main Execution
# =============================================================================


def print_summary(results: List[ValidationResult]):
    """Print validation summary."""
    print("\n" + "=" * 70)
    print("VALIDATION SUMMARY")
    print("=" * 70)

    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed
    critical_failed = sum(1 for r in results if not r.passed and r.critical)

    print(f"Total Checks: {total}")
    print(f"Passed: {passed} ✅")
    print(f"Failed: {failed} ❌")

    if critical_failed > 0:
        print(f"Critical Failures: {critical_failed} 🚨")

    print("\nFailed Checks:")
    for result in results:
        if not result.passed:
            critical_mark = " [CRITICAL]" if result.critical else ""
            print(f"  - {result.name}{critical_mark}: {result.message}")

    print("=" * 70)

    # Determine exit code
    if critical_failed > 0:
        return 2  # Critical failure
    elif failed > 0:
        return 1  # Some failures
    else:
        return 0  # All passed


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Validate SDK migration")
    parser.add_argument(
        "--phase",
        type=str,
        choices=["pre", "post", "all", "rollback"],
        default="all",
        help="Validation phase to run",
    )
    parser.add_argument(
        "--binary-url",
        type=str,
        default="http://localhost:8765",
        help="Binary proxy URL",
    )
    parser.add_argument(
        "--sdk-url",
        type=str,
        default="http://localhost:8764",
        help="SDK proxy URL",
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config/config.yaml",
        help="Config file path",
    )
    parser.add_argument(
        "--master-key",
        type=str,
        default="sk-1234",
        help="Master API key",
    )

    args = parser.parse_args()

    config = ValidationConfig(
        binary_proxy_url=args.binary_url,
        sdk_proxy_url=args.sdk_url,
        config_path=args.config,
        master_key=args.master_key,
    )

    # Run appropriate validation phase
    if args.phase == "pre":
        suite = await run_pre_migration_validation(config)
        results = suite.results
    elif args.phase == "post":
        suite = await run_post_migration_validation(config)
        results = suite.results
    elif args.phase == "rollback":
        suite = await run_rollback_validation(config)
        results = suite.results
    else:  # all
        results = await run_full_validation(config)

    # Print summary and exit
    exit_code = print_summary(results)
    sys.exit(exit_code)


if __name__ == "__main__":
    asyncio.run(main())
