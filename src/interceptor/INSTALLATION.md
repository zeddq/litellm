# Interceptor Installation Guide

This guide explains how to install and use the unified `interceptor` CLI tool.

## Installation

The interceptor is installed as part of the litellm-memory project via Poetry.

### Install via Poetry

```bash
# From the project root
poetry install

# This installs the 'interceptor' command
```

### Verify Installation

```bash
# Show help
poetry run interceptor --help

# List port mappings
poetry run interceptor list
```

## Usage

The `interceptor` command provides a unified interface for running the interceptor proxy and managing port assignments.

### Run Interceptor Proxy

```bash
# Run in current project (auto-assigns port)
poetry run interceptor run

# Run on specific host
poetry run interceptor run --host 127.0.0.1
```

### Manage Port Mappings

```bash
# List all project mappings
poetry run interceptor list

# Show port for current project
poetry run interceptor show

# Show port for specific project
poetry run interceptor show /path/to/project

# Allocate port for current project
poetry run interceptor allocate

# Remove port mapping
poetry run interceptor remove

# Check if specific port is available
poetry run interceptor check 8888

# Reset registry (remove all mappings)
poetry run interceptor reset
```

### Configuration Options

Global options (apply to all commands):

```bash
--port-min PORT     Minimum port in range
--port-max PORT     Maximum port in range
--registry PATH     Custom registry file path
```

Example:

```bash
# Use custom port range
poetry run interceptor --port-min 9000 --port-max 9999 list
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `INTERCEPTOR_PORT` | (registry) | Override automatic port allocation |
| `INTERCEPTOR_PORT_MIN` | 8888 | Minimum port in range |
| `INTERCEPTOR_PORT_MAX` | 9999 | Maximum port in range |
| `TARGET_LLM_URL` | `http://localhost:8764` | Target LLM proxy URL |
| `SUPERMEMORY_USERNAME` | `pycharm-{project}` | Instance identifier |

## Creating a Shell Alias

For convenience, create an alias in your shell configuration:

### For zsh (~/.zshrc)

```bash
alias interceptor='poetry run interceptor'
```

### For bash (~/.bashrc)

```bash
alias interceptor='poetry run interceptor'
```

After adding the alias:

```bash
# Reload shell configuration
source ~/.zshrc  # or ~/.bashrc

# Now use interceptor directly
interceptor list
interceptor run
```

## PyCharm Integration

### 1. Find Your Port

```bash
cd /path/to/your/project
poetry run interceptor allocate
```

This will show the assigned port (e.g., 8888).

### 2. Configure PyCharm

1. Open PyCharm Settings (⌘, on Mac)
2. Navigate to: Tools → LLM Services
3. Set API endpoint: `http://localhost:8888` (use your assigned port)
4. Apply changes

### 3. Start Interceptor

In your project directory:

```bash
poetry run interceptor run
```

Keep this running while using PyCharm AI features.

## Multiple Projects

When working with multiple projects simultaneously:

1. Each project gets its own unique port automatically
2. Start the interceptor in each project:

```bash
# Terminal 1 - Project A
cd /path/to/projectA
poetry run interceptor run  # Assigns port 8888

# Terminal 2 - Project B  
cd /path/to/projectB
poetry run interceptor run  # Assigns port 8889
```

3. Configure each PyCharm instance with its respective port

4. View all assignments:

```bash
poetry run interceptor list
```

## Troubleshooting

### Command Not Found

If you get "command not found: interceptor":

```bash
# Make sure you're using poetry run
poetry run interceptor --help

# Or create a shell alias (see above)
```

### Port Already in Use

If the assigned port is in use:

```bash
# Check which process is using it
lsof -i :8888

# Remove the mapping to get a new port
poetry run interceptor remove
poetry run interceptor allocate
```

### Import Errors

If you get import errors:

```bash
# Reinstall the package
poetry install
```

### Registry Issues

If the registry is corrupted:

```bash
# The system will automatically create a backup
# Location: ~/.config/litellm/port_registry.json.backup

# Or reset the registry
poetry run interceptor reset
```

## Uninstallation

The interceptor is part of the litellm-memory package, so it's removed when you remove the package:

```bash
# To clean up port mappings
poetry run interceptor reset

# The registry file can be manually removed
rm ~/.config/litellm/port_registry.json
```

## Advanced Usage

### Custom Port Range

```bash
# Use ports 10000-10999
export INTERCEPTOR_PORT_MIN=10000
export INTERCEPTOR_PORT_MAX=10999

poetry run interceptor run
```

### Custom Registry Location

```bash
# Use custom registry file
poetry run interceptor --registry /tmp/my-registry.json list
```

### Explicit Port Override

```bash
# Bypass registry and use specific port
INTERCEPTOR_PORT=9000 poetry run interceptor run
```

## See Also

- [README.md](README.md) - Comprehensive documentation
- [PORT_COORDINATION_SUMMARY.md](PORT_COORDINATION_SUMMARY.md) - Implementation details
- [pyproject.toml](../../pyproject.toml) - Package configuration
