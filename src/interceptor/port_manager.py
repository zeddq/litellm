#!/usr/bin/env python3
"""
Port Manager CLI

Command-line tool for managing PyCharm/IntelliJ project port assignments.
"""
import argparse
import os
import sys
from pathlib import Path
from typing import Optional
from .port_registry import PortRegistry


def list_mappings(registry: PortRegistry):
    """List all project to port mappings."""
    mappings = registry.list_mappings()
    info = registry.get_info()

    print(f"\nOTEL_SERVICE_NAME: {os.getenv("OTEL_SERVICE_NAME")}")
    print("\n" + "=" * 80)
    print("Port Registry Information")
    print("=" * 80)
    print(f"Registry File:    {info['registry_file']}")
    print(f"Port Range:       {info['port_range']}")
    print(f"Total Ports:      {info['total_ports']}")
    print(f"Allocated Ports:  {info['allocated_ports']}")
    print(f"Available Ports:  {info['available_ports']}")
    print(f"Next Available:   {info['next_available']}")
    print("=" * 80)

    if not mappings:
        print("\nNo project mappings found.")
        return

    print(f"\nProject Mappings ({len(mappings)}):")
    print("-" * 80)

    # Sort by port for easier reading
    sorted_mappings = sorted(mappings.items(), key=lambda x: x[1])

    for project_path, port in sorted_mappings:
        # Show project name (last directory) and full path
        project_name = Path(project_path).name
        status = "✓" if registry.is_port_available(port) else "⚠ IN USE"
        print(f"  Port {port:5d} {status:>10s}  →  {project_name}")
        print(f"             {project_path}")


def show_project_port(registry: PortRegistry, project_path: str):
    """Show the port assigned to a specific project."""
    port = registry.get_port(project_path)

    if port:
        project_name = Path(project_path).name
        available = registry.is_port_available(port)
        status = "available" if available else "IN USE"

        print(f"\nProject: {project_name}")
        print(f"Path:    {project_path}")
        print(f"Port:    {port} ({status})")
    else:
        print(f"\nNo port assigned to project: {project_path}")
        print("Run the interceptor in this project to allocate a port.")


def allocate_port(registry: PortRegistry, project_path: str):
    """Allocate or show port for a project."""
    try:
        port = registry.get_or_allocate_port(project_path)
        project_name = Path(project_path).name

        print(f"\nProject: {project_name}")
        print(f"Path:    {project_path}")
        print(f"Port:    {port}")
        print("\n✓ Port allocated successfully")
    except RuntimeError as e:
        print(f"\n✗ Error: {e}", file=sys.stderr)
        sys.exit(1)


def remove_mapping(registry: PortRegistry, project_path: str):
    """Remove a project's port mapping."""
    removed = registry.remove_mapping(project_path)

    if removed:
        project_name = Path(project_path).name
        print(f"\n✓ Removed port mapping for project: {project_name}")
        print(f"  Path: {project_path}")
    else:
        print(f"\n✗ No mapping found for project: {project_path}", file=sys.stderr)
        sys.exit(1)


def check_port(registry: PortRegistry, port: int):
    """Check if a specific port is available."""
    available = registry.is_port_available(port)
    mappings = registry.list_mappings()

    # Check if port is assigned to a project
    assigned_to = None
    for project_path, assigned_port in mappings.items():
        if assigned_port == port:
            assigned_to = project_path
            break

    print(f"\nPort {port}:")

    if assigned_to:
        project_name = Path(assigned_to).name
        print(f"  Status:       Assigned to project")
        print(f"  Project:      {project_name}")
        print(f"  Path:         {assigned_to}")
        print(f"  Available:    {'Yes' if available else 'No (currently in use)'}")
    else:
        if available:
            print(f"  Status:       Available (not assigned)")
        else:
            print(f"  Status:       In use by another process")
            print(f"  Not assigned to any project in registry")


def reset_registry(registry: PortRegistry):
    """Reset the registry (remove all mappings)."""
    print("\n⚠ WARNING: This will remove all project port mappings!")
    response = input("Are you sure? (yes/no): ")

    if response.lower() == "yes":
        # Read and clear mappings
        registry_data = registry._read_registry()
        registry_data["mappings"] = {}
        registry_data["next_available"] = registry.port_min
        registry._write_registry(registry_data)

        print("\n✓ Registry reset successfully")
        print(f"  Registry file: {registry.registry_file}")
    else:
        print("\n✗ Operation cancelled")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Manage PyCharm/IntelliJ project port assignments",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List all mappings
  python port_manager.py list

  # Show port for current project
  python port_manager.py show

  # Show port for specific project
  python port_manager.py show /path/to/project

  # Allocate port for current project
  python port_manager.py allocate

  # Remove mapping for current project
  python port_manager.py remove

  # Check if a specific port is available
  python port_manager.py check 8888

  # Reset registry (remove all mappings)
  python port_manager.py reset
        """,
    )

    parser.add_argument(
        "command",
        choices=["list", "show", "allocate", "remove", "check", "reset"],
        help="Command to execute",
    )

    parser.add_argument(
        "path_or_port",
        nargs="?",
        help="Project path or port number (depends on command)",
    )

    parser.add_argument(
        "--port-min",
        type=int,
        help="Minimum port number (default: 8888 or INTERCEPTOR_PORT_MIN env var)",
    )

    parser.add_argument(
        "--port-max",
        type=int,
        help="Maximum port number (default: 9999 or INTERCEPTOR_PORT_MAX env var)",
    )

    parser.add_argument(
        "--registry",
        type=str,
        help="Custom registry file path",
    )

    args = parser.parse_args()

    # Initialize registry
    registry_file = Path(args.registry) if args.registry else None
    registry = PortRegistry(
        port_min=args.port_min,
        port_max=args.port_max,
        registry_file=registry_file,
    )

    # Execute command
    if args.command == "list":
        list_mappings(registry)

    elif args.command == "show":
        project_path = args.path_or_port or str(Path.cwd().resolve())
        show_project_port(registry, project_path)

    elif args.command == "allocate":
        project_path = args.path_or_port or str(Path.cwd().resolve())
        allocate_port(registry, project_path)

    elif args.command == "remove":
        project_path = args.path_or_port or str(Path.cwd().resolve())
        remove_mapping(registry, project_path)

    elif args.command == "check":
        if not args.path_or_port:
            print("✗ Error: Port number required for 'check' command", file=sys.stderr)
            sys.exit(1)
        try:
            port = int(args.path_or_port)
            check_port(registry, port)
        except ValueError:
            print(f"✗ Error: Invalid port number: {args.path_or_port}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "reset":
        reset_registry(registry)


if __name__ == "__main__":
    main()
