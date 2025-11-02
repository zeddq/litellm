# PyCharm/IntelliJ Interceptor Port Management

This directory contains the interceptor proxy and port management system for PyCharm and other JetBrains IDEs.

## Overview

The port management system ensures that each project gets a consistent, unique port for its interceptor proxy. This prevents port conflicts when running multiple projects simultaneously and maintains port consistency across sessions.

## Components

### 1. Port Registry (`port_registry.py`)

The core module that manages port assignments:

- **Storage**: JSON file at `~/.config/litellm/port_registry.json`
- **Port Range**: 8888-9999 (configurable via environment variables)
- **Concurrency**: File locking prevents race conditions during concurrent access
- **Persistence**: Port assignments persist across sessions

### 2. Interceptor Proxy (`intercepting_contexter.py`)

The FastAPI-based proxy that:

- Automatically gets or allocates a port from the registry
- Forwards requests to the target LLM proxy
- Adds custom headers for user identification
- Supports both streaming and non-streaming responses

### 3. Port Manager CLI (`port_manager.py`)

Command-line tool for managing port assignments:

```bash
# List all project mappings
python port_manager.py list

# Show port for current project
python port_manager.py show

# Allocate port for a specific project
python port_manager.py allocate /path/to/project

# Remove port mapping
python port_manager.py remove /path/to/project

# Check port availability
python port_manager.py check 8888

# Reset registry (remove all mappings)
python port_manager.py reset
```

## Usage

### Running the Interceptor

The interceptor automatically uses the port registry when started:

```bash
cd /path/to/your/project
python src/interceptor/intercepting_contexter.py
```

The first time a project runs, it will be assigned a port (e.g., 8888). Subsequent runs will use the same port.

### Explicit Port Override

To override the automatic port allocation, set the `INTERCEPTOR_PORT` environment variable:

```bash
INTERCEPTOR_PORT=9000 python src/interceptor/intercepting_contexter.py
```

This bypasses the registry and uses the specified port directly.

### Configuration

Configure the port range using environment variables:

```bash
# Set custom port range
export INTERCEPTOR_PORT_MIN=8888
export INTERCEPTOR_PORT_MAX=9999

# Run interceptor
python src/interceptor/intercepting_contexter.py
```

## Registry File Format

The registry is stored as JSON at `~/.config/litellm/port_registry.json`:

```json
{
  "version": "1.0",
  "port_range": {
    "start": 8888,
    "end": 9999
  },
  "mappings": {
    "/Users/username/project1": 8888,
    "/Users/username/project2": 8889,
    "/Users/username/project3": 8890
  },
  "next_available": 8891
}
```

### Fields

- `version`: Registry format version
- `port_range`: Configured min/max ports
- `mappings`: Project path → port assignments
- `next_available`: Next port to try for allocation

## Port Allocation Logic

When a project requests a port:

1. **Check existing mapping**: If project already has a port, return it
2. **Find available port**: Search from `next_available` within the range
3. **Skip in-use ports**: Check if port is actually available on the system
4. **Allocate and persist**: Assign port and save to registry
5. **Handle exhaustion**: Fail with clear error if no ports available

## Managing Port Mappings

### View All Mappings

```bash
$ cd /path/to/litellm
$ python src/interceptor/port_manager.py list

================================================================================
Port Registry Information
================================================================================
Registry File:    /Users/username/.config/litellm/port_registry.json
Port Range:       8888-9999
Total Ports:      1112
Allocated Ports:  3
Available Ports:  1109
Next Available:   8891
================================================================================

Project Mappings (3):
--------------------------------------------------------------------------------
  Port  8888          ✓  →  litellm
             /Users/username/litellm
  Port  8889    ⚠ IN USE  →  other-project
             /Users/username/other-project
  Port  8890          ✓  →  test-project
             /Users/username/test-project
```

### Check Specific Port

```bash
$ python src/interceptor/port_manager.py check 8888

Port 8888:
  Status:       Assigned to project
  Project:      litellm
  Path:         /Users/username/litellm
  Available:    Yes
```

### Remove Stale Mapping

```bash
$ python src/interceptor/port_manager.py remove /Users/username/old-project

✓ Removed port mapping for project: old-project
  Path: /Users/username/old-project
```

### Manual Port Allocation

```bash
$ python src/interceptor/port_manager.py allocate /Users/username/new-project

Project: new-project
Path:    /Users/username/new-project
Port:    8891

✓ Port allocated successfully
```

## Troubleshooting

### Port Already in Use

If the allocated port is in use by another process:

1. The interceptor will log a warning
2. Check which process is using the port: `lsof -i :8888`
3. Either stop that process or remove the mapping to get a new port:
   ```bash
   python src/interceptor/port_manager.py remove
   ```

### Port Range Exhausted

If all ports in the range are allocated:

1. Increase the port range:
   ```bash
   export INTERCEPTOR_PORT_MAX=19999
   ```
2. Or clean up unused mappings:
   ```bash
   python src/interceptor/port_manager.py list
   python src/interceptor/port_manager.py remove /path/to/unused/project
   ```

### Corrupted Registry

If the registry file becomes corrupted:

- The system automatically creates a backup (`.json.backup`)
- A fresh registry is initialized
- Previous mappings are lost (consider restoring from backup)

### Concurrent Access

File locking prevents race conditions, but if you experience issues:

1. Check for zombie lock files
2. Ensure the registry directory is writable: `~/.config/litellm/`
3. Check file permissions on `port_registry.json`

## Integration with JetBrains IDEs

### PyCharm Configuration

Configure PyCharm to use the interceptor:

1. Open Settings → Tools → LLM Services
2. Set API endpoint to: `http://localhost:<PORT>`
3. The port is shown in the interceptor startup logs

### Multiple Projects

When running multiple projects simultaneously:

- Each project automatically gets its own unique port
- Configure each IDE instance with its respective port
- Use the port manager CLI to view all active mappings

## API Reference

### PortRegistry Class

```python
from port_registry import PortRegistry

# Initialize
registry = PortRegistry(
    port_min=8888,  # Optional, defaults to env or 8888
    port_max=9999,  # Optional, defaults to env or 9999
    registry_file=None  # Optional custom path
)

# Get or allocate port
port = registry.get_or_allocate_port("/path/to/project")

# Check existing port
existing_port = registry.get_port("/path/to/project")  # Returns None if not found

# List all mappings
mappings = registry.list_mappings()  # Dict[str, int]

# Check port availability
available = registry.is_port_available(8888)  # bool

# Remove mapping
removed = registry.remove_mapping("/path/to/project")  # bool

# Get registry info
info = registry.get_info()  # dict with statistics
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `INTERCEPTOR_PORT` | (uses registry) | Override automatic port allocation |
| `INTERCEPTOR_PORT_MIN` | 8888 | Minimum port in allocation range |
| `INTERCEPTOR_PORT_MAX` | 9999 | Maximum port in allocation range |
| `TARGET_LLM_URL` | `http://localhost:8764` | Target proxy URL |
| `SUPERMEMORY_USERNAME` | `pycharm-{project}` | Instance identifier |

## Future Enhancements

The following features are planned for future implementation:

- **Automatic cleanup**: Remove mappings for deleted projects
- **Port recycling**: Reclaim ports from long-unused projects
- **Health monitoring**: Track which interceptors are actively running
- **Web UI**: Browser-based port management interface
- **Auto-discovery**: Detect and suggest available ports
- **Export/import**: Backup and restore registry mappings

## See Also

- [Interceptor Proxy Documentation](intercepting_contexter.py)
- [LiteLLM Proxy Documentation](../proxy/)
- [Configuration Guide](../../config/)
