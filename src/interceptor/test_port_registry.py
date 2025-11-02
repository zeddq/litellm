#!/usr/bin/env python3
"""
Test script for Port Registry

Verifies port allocation, persistence, and concurrent access handling.
"""
import tempfile
import time
from pathlib import Path
from port_registry import PortRegistry


def test_basic_allocation():
    """Test basic port allocation."""
    print("\n" + "=" * 60)
    print("Test 1: Basic Port Allocation")
    print("=" * 60)

    # Use temporary file for testing
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        registry = PortRegistry(
            port_min=8888,
            port_max=8900,
            registry_file=tmp_path
        )

        # Allocate ports for different projects
        project1 = "/tmp/test/project1"
        project2 = "/tmp/test/project2"
        project3 = "/tmp/test/project3"

        port1 = registry.get_or_allocate_port(project1)
        print(f"✓ Project 1 allocated: {port1}")
        assert port1 == 8888, f"Expected 8888, got {port1}"

        port2 = registry.get_or_allocate_port(project2)
        print(f"✓ Project 2 allocated: {port2}")
        assert port2 == 8889, f"Expected 8889, got {port2}"

        port3 = registry.get_or_allocate_port(project3)
        print(f"✓ Project 3 allocated: {port3}")
        assert port3 == 8890, f"Expected 8890, got {port3}"

        # Verify same project gets same port
        port1_again = registry.get_or_allocate_port(project1)
        print(f"✓ Project 1 reuse: {port1_again}")
        assert port1_again == port1, f"Port changed from {port1} to {port1_again}"

        print("\n✅ Basic allocation test passed")

    finally:
        tmp_path.unlink(missing_ok=True)


def test_persistence():
    """Test that allocations persist across registry instances."""
    print("\n" + "=" * 60)
    print("Test 2: Persistence Across Instances")
    print("=" * 60)

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        # First registry instance
        registry1 = PortRegistry(
            port_min=8888,
            port_max=8900,
            registry_file=tmp_path
        )

        project = "/tmp/test/persistent_project"
        port1 = registry1.get_or_allocate_port(project)
        print(f"✓ Registry 1 allocated: {port1}")

        # Second registry instance (simulates restart)
        registry2 = PortRegistry(
            port_min=8888,
            port_max=8900,
            registry_file=tmp_path
        )

        port2 = registry2.get_port(project)
        print(f"✓ Registry 2 retrieved: {port2}")
        assert port2 == port1, f"Port changed from {port1} to {port2}"

        print("\n✅ Persistence test passed")

    finally:
        tmp_path.unlink(missing_ok=True)


def test_port_availability():
    """Test port availability checking."""
    print("\n" + "=" * 60)
    print("Test 3: Port Availability")
    print("=" * 60)

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        registry = PortRegistry(
            port_min=8888,
            port_max=8900,
            registry_file=tmp_path
        )

        # Check a port that should be available
        available = registry.is_port_available(8999)
        print(f"✓ Port 8999 available: {available}")
        assert available, "Port 8999 should be available"

        print("\n✅ Port availability test passed")

    finally:
        tmp_path.unlink(missing_ok=True)


def test_list_mappings():
    """Test listing all mappings."""
    print("\n" + "=" * 60)
    print("Test 4: List Mappings")
    print("=" * 60)

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        registry = PortRegistry(
            port_min=8888,
            port_max=8900,
            registry_file=tmp_path
        )

        # Allocate several ports
        projects = [
            "/tmp/test/proj1",
            "/tmp/test/proj2",
            "/tmp/test/proj3",
        ]

        for project in projects:
            port = registry.get_or_allocate_port(project)
            print(f"✓ Allocated {project}: {port}")

        # List all mappings
        mappings = registry.list_mappings()
        print(f"\n✓ Total mappings: {len(mappings)}")
        assert len(mappings) == 3, f"Expected 3 mappings, got {len(mappings)}"

        for project, port in mappings.items():
            print(f"  {Path(project).name} → {port}")

        print("\n✅ List mappings test passed")

    finally:
        tmp_path.unlink(missing_ok=True)


def test_remove_mapping():
    """Test removing a mapping."""
    print("\n" + "=" * 60)
    print("Test 5: Remove Mapping")
    print("=" * 60)

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        registry = PortRegistry(
            port_min=8888,
            port_max=8900,
            registry_file=tmp_path
        )

        project = "/tmp/test/remove_me"
        port = registry.get_or_allocate_port(project)
        print(f"✓ Allocated {project}: {port}")

        # Remove the mapping
        removed = registry.remove_mapping(project)
        print(f"✓ Removed mapping: {removed}")
        assert removed, "Remove should return True"

        # Verify it's gone
        port_after = registry.get_port(project)
        print(f"✓ Port after removal: {port_after}")
        assert port_after is None, f"Expected None, got {port_after}"

        print("\n✅ Remove mapping test passed")

    finally:
        tmp_path.unlink(missing_ok=True)


def test_registry_info():
    """Test getting registry information."""
    print("\n" + "=" * 60)
    print("Test 6: Registry Info")
    print("=" * 60)

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        registry = PortRegistry(
            port_min=8888,
            port_max=8900,
            registry_file=tmp_path
        )

        # Allocate a few ports
        for i in range(3):
            registry.get_or_allocate_port(f"/tmp/test/proj{i}")

        # Get info
        info = registry.get_info()
        print(f"✓ Registry file: {info['registry_file']}")
        print(f"✓ Port range: {info['port_range']}")
        print(f"✓ Total ports: {info['total_ports']}")
        print(f"✓ Allocated ports: {info['allocated_ports']}")
        print(f"✓ Available ports: {info['available_ports']}")
        print(f"✓ Next available: {info['next_available']}")

        assert info['allocated_ports'] == 3, "Should have 3 allocated ports"
        assert info['total_ports'] == 13, "Should have 13 total ports (8888-8900)"

        print("\n✅ Registry info test passed")

    finally:
        tmp_path.unlink(missing_ok=True)


def test_path_normalization():
    """Test that paths are normalized correctly."""
    print("\n" + "=" * 60)
    print("Test 7: Path Normalization")
    print("=" * 60)

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        registry = PortRegistry(
            port_min=8888,
            port_max=8900,
            registry_file=tmp_path
        )

        # Use relative path
        project = "."
        port1 = registry.get_or_allocate_port(project)
        print(f"✓ Relative path '.': {port1}")

        # Use absolute path for same directory
        project_abs = str(Path.cwd().resolve())
        port2 = registry.get_port(project_abs)
        print(f"✓ Absolute path: {port2}")

        assert port1 == port2, f"Ports should match: {port1} vs {port2}"

        print("\n✅ Path normalization test passed")

    finally:
        tmp_path.unlink(missing_ok=True)


def run_all_tests():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("Port Registry Test Suite")
    print("=" * 60)

    tests = [
        test_basic_allocation,
        test_persistence,
        test_port_availability,
        test_list_mappings,
        test_remove_mapping,
        test_registry_info,
        test_path_normalization,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"\n❌ Test failed: {e}")
            failed += 1
        except Exception as e:
            print(f"\n❌ Test error: {e}")
            failed += 1

    print("\n" + "=" * 60)
    print("Test Results")
    print("=" * 60)
    print(f"Passed: {passed}/{len(tests)}")
    print(f"Failed: {failed}/{len(tests)}")

    if failed == 0:
        print("\n🎉 All tests passed!")
    else:
        print(f"\n⚠️  {failed} test(s) failed")

    return failed == 0


if __name__ == "__main__":
    import sys
    success = run_all_tests()
    sys.exit(0 if success else 1)
