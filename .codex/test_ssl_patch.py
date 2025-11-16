#!/usr/bin/env python3
"""
Test script to verify SSL patching is working correctly.
"""
import os
import ssl
import sys

print("🔍 Testing SSL Configuration...")
print(f"Python version: {sys.version}")
print(f"SSL version: {ssl.OPENSSL_VERSION}")
print()

# Check environment variables
print("📋 Environment Variables:")
print(f"  SSL_CERT_FILE: {os.getenv('SSL_CERT_FILE', 'NOT SET')}")
print(f"  CODEX_PROXY_CERT: {os.getenv('CODEX_PROXY_CERT', 'NOT SET')}")
print(f"  REQUESTS_CA_BUNDLE: {os.getenv('REQUESTS_CA_BUNDLE', 'NOT SET')}")
print()

# Check if sitecustomize was loaded
print("📦 Checking sitecustomize.py:")
try:
    import sitecustomize
    print("  ✅ sitecustomize.py loaded")
except ImportError:
    print("  ⚠️  sitecustomize.py not found")
print()

# Check SSL context
print("🔐 Checking SSL Context:")
try:
    context = ssl.create_default_context()

    # Check verify flags
    flags = context.verify_flags
    print(f"  Verify flags: {flags}")

    # Check for Python 3.13+ specific flags
    if hasattr(ssl, 'VERIFY_X509_STRICT'):
        strict_set = bool(flags & ssl.VERIFY_X509_STRICT)
        print(f"  VERIFY_X509_STRICT: {'ENABLED ❌' if strict_set else 'DISABLED ✅'}")
    else:
        print("  VERIFY_X509_STRICT: Not available (Python < 3.13)")

    if hasattr(ssl, 'VERIFY_X509_PARTIAL_CHAIN'):
        partial_set = bool(flags & ssl.VERIFY_X509_PARTIAL_CHAIN)
        print(f"  VERIFY_X509_PARTIAL_CHAIN: {'ENABLED ❌' if partial_set else 'DISABLED ✅'}")
    else:
        print("  VERIFY_X509_PARTIAL_CHAIN: Not available (Python < 3.13)")

    print()

    # Check CA certs loaded
    cert_file = os.getenv('SSL_CERT_FILE') or os.getenv('CODEX_PROXY_CERT')
    if cert_file and os.path.exists(cert_file):
        print(f"  ✅ Certificate file exists: {cert_file}")
    else:
        print(f"  ⚠️  Certificate file not found: {cert_file}")

except Exception as e:
    print(f"  ❌ Error creating SSL context: {e}")
    sys.exit(1)

print()

# Test urllib
print("🌐 Testing urllib with SSL:")
try:
    from urllib.request import urlopen

    # Test with a simple request (not PyPI to avoid MITM)
    test_url = "https://pypi.org/simple/"

    print(f"  Attempting connection to {test_url}...")

    # Create context manually
    context = ssl.create_default_context()
    if hasattr(ssl, 'VERIFY_X509_STRICT'):
        context.verify_flags &= ~ssl.VERIFY_X509_STRICT
    if hasattr(ssl, 'VERIFY_X509_PARTIAL_CHAIN'):
        context.verify_flags &= ~ssl.VERIFY_X509_PARTIAL_CHAIN

    cert_file = os.getenv('SSL_CERT_FILE') or os.getenv('CODEX_PROXY_CERT')
    if cert_file and os.path.exists(cert_file):
        context.load_verify_locations(cafile=cert_file)

    with urlopen(test_url, context=context, timeout=10) as response:
        status = response.status
        print(f"  ✅ Connection successful! Status: {status}")

except Exception as e:
    print(f"  ❌ Connection failed: {e}")
    print("  This is expected if the MITM proxy certificate isn't properly configured")

print()
print("=" * 60)
print("Test complete!")
