#!/usr/bin/env python3
"""
Interceptor CLI - Unified command-line interface for PyCharm/IntelliJ interceptor

Combines interceptor proxy server and port management into a single tool.
"""
import argparse
import sys
import os
from pathlib import Path


def cmd_run(args):
    """Run the interceptor proxy server."""
    from .intercepting_contexter import app, INTERCEPTOR_PORT, INSTANCE_ID, TARGET_LLM_URL, CUSTOM_HEADERS, logger
    import uvicorn

    logger.info("=" * 60)
    logger.info("PyCharm AI Chat Interceptor")
    logger.info("=" * 60)
    logger.info(f"Instance ID: {INSTANCE_ID}")
    logger.info(f"Listening on: http://0.0.0.0:{INTERCEPTOR_PORT}")
    logger.info(f"Forwarding to: {TARGET_LLM_URL}")
    logger.info(f"Custom headers: {CUSTOM_HEADERS}")
    logger.info("=" * 60)

    uvicorn.run(app, host=args.host, port=INTERCEPTOR_PORT)


def cmd_list(args):
    """List all project to port mappings."""
    from .port_manager import list_mappings
    from .port_registry import PortRegistry

    registry = PortRegistry(
        port_min=args.port_min,
        port_max=args.port_max,
        registry_file=Path(args.registry) if args.registry else None,
    )
    list_mappings(registry)


def cmd_show(args):
    """Show port for a specific project."""
    from .port_manager import show_project_port
    from .port_registry import PortRegistry

    registry = PortRegistry(
        port_min=args.port_min,
        port_max=args.port_max,
        registry_file=Path(args.registry) if args.registry else None,
    )
    project_path = args.path or str(Path.cwd().resolve())
    show_project_port(registry, project_path)


def cmd_allocate(args):
    """Allocate port for a project."""
    from .port_manager import allocate_port
    from .port_registry import PortRegistry

    registry = PortRegistry(
        port_min=args.port_min,
        port_max=args.port_max,
        registry_file=Path(args.registry) if args.registry else None,
    )
    project_path = args.path or str(Path.cwd().resolve())
    allocate_port(registry, project_path)


def cmd_remove(args):
    """Remove port mapping for a project."""
    from .port_manager import remove_mapping
    from .port_registry import PortRegistry

    registry = PortRegistry(
        port_min=args.port_min,
        port_max=args.port_max,
        registry_file=Path(args.registry) if args.registry else None,
    )
    project_path = args.path or str(Path.cwd().resolve())
    remove_mapping(registry, project_path)


def cmd_check(args):
    """Check if a specific port is available."""
    from .port_manager import check_port
    from .port_registry import PortRegistry

    registry = PortRegistry(
        port_min=args.port_min,
        port_max=args.port_max,
        registry_file=Path(args.registry) if args.registry else None,
    )
    check_port(registry, args.port)


def cmd_reset(args):
    """Reset the registry."""
    from .port_manager import reset_registry
    from .port_registry import PortRegistry

    registry = PortRegistry(
        port_min=args.port_min,
        port_max=args.port_max,
        registry_file=Path(args.registry) if args.registry else None,
    )
    reset_registry(registry)


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="interceptor",
        description="PyCharm/IntelliJ Interceptor - AI Chat proxy with automatic port coordination",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run interceptor (auto-assigns port)
  interceptor run

  # List all project mappings
  interceptor list

  # Show port for current project
  interceptor show

  # Allocate port for specific project
  interceptor allocate /path/to/project

  # Remove port mapping
  interceptor remove /path/to/project

  # Check port availability
  interceptor check 8888

  # Reset registry
  interceptor reset

Environment Variables:
  INTERCEPTOR_PORT      Override automatic port allocation
  INTERCEPTOR_PORT_MIN  Minimum port in range (default: 8888)
  INTERCEPTOR_PORT_MAX  Maximum port in range (default: 9999)
  TARGET_LLM_URL       Target LLM proxy URL (default: http://localhost:8764)
  SUPERMEMORY_USERNAME Instance identifier
        """,
    )

    # Global options
    parser.add_argument(
        "--port-min",
        type=int,
        help="Minimum port number (default: 8888 or INTERCEPTOR_PORT_MIN)",
    )
    parser.add_argument(
        "--port-max",
        type=int,
        help="Maximum port number (default: 9999 or INTERCEPTOR_PORT_MAX)",
    )
    parser.add_argument(
        "--registry",
        type=str,
        help="Custom registry file path",
    )

    # Subcommands
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Run command
    run_parser = subparsers.add_parser(
        "run",
        help="Run the interceptor proxy server",
        description="Start the interceptor proxy server with automatic port allocation",
    )
    run_parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind to (default: 0.0.0.0)",
    )
    run_parser.set_defaults(func=cmd_run)

    # List command
    list_parser = subparsers.add_parser(
        "list",
        help="List all project to port mappings",
        description="Display all project to port mappings in the registry",
    )
    list_parser.set_defaults(func=cmd_list)

    # Show command
    show_parser = subparsers.add_parser(
        "show",
        help="Show port for a project",
        description="Display the assigned port for a specific project",
    )
    show_parser.add_argument(
        "path",
        nargs="?",
        help="Project path (default: current directory)",
    )
    show_parser.set_defaults(func=cmd_show)

    # Allocate command
    allocate_parser = subparsers.add_parser(
        "allocate",
        help="Allocate port for a project",
        description="Allocate or show port assignment for a project",
    )
    allocate_parser.add_argument(
        "path",
        nargs="?",
        help="Project path (default: current directory)",
    )
    allocate_parser.set_defaults(func=cmd_allocate)

    # Remove command
    remove_parser = subparsers.add_parser(
        "remove",
        help="Remove port mapping",
        description="Remove port assignment for a project",
    )
    remove_parser.add_argument(
        "path",
        nargs="?",
        help="Project path (default: current directory)",
    )
    remove_parser.set_defaults(func=cmd_remove)

    # Check command
    check_parser = subparsers.add_parser(
        "check",
        help="Check port availability",
        description="Check if a specific port is available",
    )
    check_parser.add_argument(
        "port",
        type=int,
        help="Port number to check",
    )
    check_parser.set_defaults(func=cmd_check)

    # Reset command
    reset_parser = subparsers.add_parser(
        "reset",
        help="Reset the registry",
        description="Remove all port mappings from the registry",
    )
    reset_parser.set_defaults(func=cmd_reset)

    # Parse arguments
    args = parser.parse_args()

    # Execute command
    if hasattr(args, "func"):
        try:
            args.func(args)
        except KeyboardInterrupt:
            print("\n\nInterrupted by user")
            sys.exit(0)
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
