# Interceptor Module Guide

The interceptor module provides a FastAPI-based proxy and supporting tooling that assigns stable ports to each JetBrains project and forwards requests to the LiteLLM proxy with the required headers.

## Overview
- **Purpose:** Prevent port conflicts by assigning a unique, persistent port per project.
- **Port range:** Defaults to 8888-9999 (configurable with environment variables).
- **Registry storage:** JSON file at `~/.config/litellm/port_registry.json` with file-locking for concurrency safety.
- **Manual override:** Set `INTERCEPTOR_PORT` to bypass the registry and use a specific port.

## Components
- **Port Registry (`port_registry.py`):** Core module for allocating, listing, and removing port mappings.
- **Interceptor Proxy (`intercepting_contexter.py`):** FastAPI proxy that fetches/allocates the project port and forwards requests to the target LiteLLM proxy while adding identification headers. Supports streaming and non-streaming flows.
- **Port Manager CLI (`port_manager.py`):** Command-line utility for viewing mappings, checking availability, and resetting the registry.

## Installation
The interceptor CLI is installed with the project via Poetry:
```bash
poetry install
poetry run interceptor --help
```

## Running the Interceptor
Start the proxy from your project directory:
```bash
python src/interceptor/intercepting_contexter.py
```
The first run allocates a port for the project; subsequent runs reuse it. To force a specific port, set `INTERCEPTOR_PORT=9000` (or another value) before launching.

### Configuration
Set the port range through environment variables:
```bash
export INTERCEPTOR_PORT_MIN=8888
export INTERCEPTOR_PORT_MAX=9999
python src/interceptor/intercepting_contexter.py
```

## Port Manager CLI
Common commands for managing port assignments:
```bash
# List all project mappings
poetry run interceptor list

# Show port for the current project
poetry run interceptor show

# Allocate a port for the current project
poetry run interceptor allocate

# Remove a mapping
poetry run interceptor remove

# Check if a port is available
poetry run interceptor check 8888

# Reset the registry
poetry run interceptor reset
```

## Registry Format
The registry file stores version, port range, mappings, and the next available port:
```json
{
  "version": "1.0",
  "port_range": { "start": 8888, "end": 9999 },
  "mappings": {
    "/Users/username/project1": 8888,
    "/Users/username/project2": 8889
  },
  "next_available": 8890
}
```

## Port Allocation Logic
1. Return an existing mapping if it exists.
2. Validate the configured port range.
3. Iterate until finding an available port, skipping reserved or in-use values.
4. Persist the new mapping and return the assigned port.
5. Allow explicit override through the `INTERCEPTOR_PORT` environment variable.
