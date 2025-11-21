#!/usr/bin/env python3
"""
Port Registry for PyCharm/IntelliJ Project Interceptors

Manages persistent port assignments for projects to ensure each project
consistently uses the same interceptor port across sessions.
"""
import json
import socket
import fcntl
import os
from pathlib import Path
from typing import Optional, Dict
import logging

logger = logging.getLogger(__name__)


class PortRegistry:
    """Manages persistent port assignments for projects."""

    DEFAULT_PORT_MIN = 8895
    DEFAULT_PORT_MAX = 9999
    REGISTRY_DIR = Path.home() / ".config" / "litellm"
    REGISTRY_FILE = REGISTRY_DIR / "port_registry.json"

    def __init__(
        self,
        port_min: Optional[int] = None,
        port_max: Optional[int] = None,
        registry_file: Optional[Path] = None,
    ):
        """
        Initialize port registry.

        Args:
            port_min: Minimum port number (default: 8888)
            port_max: Maximum port number (default: 9999)
            registry_file: Custom registry file path (default: ~/.config/litellm/port_registry.json)
        """
        self.port_min = port_min or int(
            os.getenv("INTERCEPTOR_PORT_MIN", self.DEFAULT_PORT_MIN)
        )
        self.port_max = port_max or int(
            os.getenv("INTERCEPTOR_PORT_MAX", self.DEFAULT_PORT_MAX)
        )
        # Check PORT_REGISTRY_PATH environment variable before using default
        env_registry_path = os.getenv("PORT_REGISTRY_PATH")
        if env_registry_path and not registry_file:
            self.registry_file = Path(env_registry_path)
        else:
            self.registry_file = registry_file or self.REGISTRY_FILE

        # Ensure registry directory exists
        self.registry_file.parent.mkdir(parents=True, exist_ok=True)

        # Initialize registry file if it doesn't exist
        if not self.registry_file.exists():
            self._initialize_registry()

    def _initialize_registry(self):
        """Create a new registry file with default structure."""
        default_registry = {
            "version": "1.0",
            "port_range": {"start": self.port_min, "end": self.port_max},
            "mappings": {},
            "next_available": self.port_min,
        }
        self._write_registry(default_registry)
        logger.info(f"Initialized new port registry at {self.registry_file}")

    def _read_registry(self) -> dict:
        """Read registry with file locking."""
        try:
            with open(self.registry_file, "r") as f:
                # Acquire shared lock for reading
                fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                try:
                    data = json.load(f)
                    return data
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except json.JSONDecodeError:
            logger.error(f"Corrupted registry file, creating backup and reinitializing")
            # Backup corrupted file
            backup_path = self.registry_file.with_suffix(".json.backup")
            self.registry_file.rename(backup_path)
            self._initialize_registry()
            return self._read_registry()

    def _write_registry(self, data: dict):
        """Write registry with file locking."""
        with open(self.registry_file, "w") as f:
            # Acquire exclusive lock for writing
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                json.dump(data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    def _normalize_project_path(self, project_path: str) -> str:
        """Normalize project path to handle symlinks and case sensitivity."""
        return str(Path(project_path).resolve())

    def is_port_available(self, port: int) -> bool:
        """
        Check if a port is available for use.

        Args:
            port: Port number to check

        Returns:
            True if port is available, False otherwise
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind(("", port))
            sock.close()
            return True
        except OSError:
            return False

    def get_port(self, project_path: str) -> Optional[int]:
        """
        Get the assigned port for a project.

        Args:
            project_path: Absolute path to the project

        Returns:
            Assigned port number or None if not found
        """
        normalized_path = self._normalize_project_path(project_path)
        registry = self._read_registry()
        return registry["mappings"].get(normalized_path)

    def get_or_allocate_port(self, project_path: str) -> int:
        """
        Get existing port or allocate a new one for a project.

        Args:
            project_path: Absolute path to the project

        Returns:
            Assigned port number

        Raises:
            RuntimeError: If no ports available in the configured range
        """
        normalized_path = self._normalize_project_path(project_path)

        # Check if project already has a port
        existing_port = self.get_port(normalized_path)
        if existing_port:
            logger.info(
                f"Project {normalized_path} already assigned to port {existing_port}"
            )
            return existing_port

        # Allocate new port
        registry = self._read_registry()
        mappings = registry["mappings"]
        next_available = registry["next_available"]

        # Find next available port that's not in use
        allocated_port = None
        attempts = 0
        max_attempts = self.port_max - self.port_min + 1

        while attempts < max_attempts:
            candidate_port = next_available

            # Check if port is in configured range
            if candidate_port > self.port_max:
                candidate_port = self.port_min

            # Check if port is already assigned to another project
            if candidate_port in mappings.values():
                next_available = candidate_port + 1
                attempts += 1
                continue

            # Check if port is actually available
            if self.is_port_available(candidate_port):
                allocated_port = candidate_port
                break

            logger.debug(f"Port {candidate_port} is in use, trying next")
            next_available = candidate_port + 1
            attempts += 1

        if allocated_port is None:
            raise RuntimeError(
                f"No available ports in range {self.port_min}-{self.port_max}. "
                f"Consider expanding the range or cleaning up unused ports."
            )

        # Update registry
        mappings[normalized_path] = allocated_port
        registry["next_available"] = (allocated_port + 1) if (allocated_port + 1) <= self.port_max else self.port_min
        self._write_registry(registry)

        logger.info(
            f"Allocated port {allocated_port} to project {normalized_path}"
        )
        return allocated_port

    def list_mappings(self) -> Dict[str, int]:
        """
        Get all project to port mappings.

        Returns:
            Dictionary mapping project paths to port numbers
        """
        registry = self._read_registry()
        return registry["mappings"].copy()

    def remove_mapping(self, project_path: str) -> bool:
        """
        Remove a project's port mapping.

        Args:
            project_path: Absolute path to the project

        Returns:
            True if mapping was removed, False if not found
        """
        normalized_path = self._normalize_project_path(project_path)
        registry = self._read_registry()

        if normalized_path in registry["mappings"]:
            del registry["mappings"][normalized_path]
            self._write_registry(registry)
            logger.info(f"Removed port mapping for project {normalized_path}")
            return True

        return False

    def allocate_port(self, project_path: str) -> int:
        """
        Backward-compatible alias for get_or_allocate_port().

        Args:
            project_path: Absolute path to the project

        Returns:
            Assigned port number

        Raises:
            RuntimeError: If no ports available in the configured range
        """
        return self.get_or_allocate_port(project_path)

    def deallocate_port(self, project_path: str) -> bool:
        """
        Backward-compatible alias for remove_mapping().

        Args:
            project_path: Absolute path to the project

        Returns:
            True if mapping was removed, False if not found
        """
        return self.remove_mapping(project_path)

    def get_info(self) -> dict:
        """
        Get registry information.

        Returns:
            Dictionary with registry metadata and statistics
        """
        registry = self._read_registry()
        mappings = registry["mappings"]

        return {
            "registry_file": str(self.registry_file),
            "port_range": f"{self.port_min}-{self.port_max}",
            "total_ports": self.port_max - self.port_min + 1,
            "allocated_ports": len(mappings),
            "available_ports": (self.port_max - self.port_min + 1) - len(mappings),
            "next_available": registry["next_available"],
        }
