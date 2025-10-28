# LiteLLM Memory Proxy

**Last Updated**: 2025-10-24

## Overview

LiteLLM Memory Proxy is a developer-focused proxy service that bridges various AI clients (IDEs, CLI tools, custom apps) with LiteLLM and Supermemory. It solves critical pain points for developers working with multiple AI providers and tools.

**Key Problems Solved**:
- **Authentication Gap**: Adds API authentication for IDEs that lack configuration options for local models
- **Unified Analytics**: Single databank tracking LLM usage metrics (cost, latency, response quality)
- **Dynamic Memory**: Seamless Supermemory integration for inline dynamic RAG and contextual memory
- **Automatic Isolation**: Auto-recognizes users/projects to keep memories separate per scope

**Target Audience**: Developers using multiple AI clients (PyCharm, Claude Code, VS Code, custom apps)

**Architecture Pattern**: External binary proxy approach - memory routing proxy (FastAPI) forwards to standalone LiteLLM binary process for better separation of concerns and deployment flexibility.

---

## 🚨 CRITICAL: Version Control with Jujutsu (jj)

**DO NOT USE GIT COMMANDS**. This project uses [Jujutsu (jj)](https://github.com/martinvonz/jj) for version control.

### Essential jj Commands

```bash
# Start new work - create bookmark before making changes
jj new && jj bookmark new <TOPIC>

# Check status
jj status

# Stage and commit changes
jj commit -m "Add feature X"

# Undo last jj operation
jj undo

# Restore files (discard changes)
jj restore <file>              # restore specific file
jj restore --from=@- <file>    # restore from parent change

# Merge into main (prefer merges over rebases)
jj new @ main && jj bookmark set -r @ <TOPIC> 

# Push to remote (when configured)
jj git push
```

### jj Workflow Philosophy

1. **Always create bookmarks** before starting work
2. **Prefer merges over rebases** for cleaner history
3. **Use `jj undo`** freely - it's safe and reversible
4. **Commit early, commit often** - jj makes it easy to reorganize later

**Need more jj help?** Use the Context7 MCP server to fetch jj documentation:
```
Ask Claude: "Get me jj documentation about [topic]"
```

---

## 🔧 CRITICAL: Use JetBrains MCP Server

**ALWAYS use the JetBrains MCP server** for file operations and codebase exploration.

### Why JetBrains MCP?

- **Context-aware**: Understands code structure, symbols, dependencies
- **Faster**: Uses IDE's indexes instead of filesystem traversal
- **Intelligent**: Semantic search, refactoring support, real-time diagnostics
- **Integrated**: Direct access to run configurations, terminal, VCS

### Preferred Operations

| Task | JetBrains MCP Tool | ❌ Don't Use |
|------|-------------------|--------------|
| **Search files** | `find_files_by_name_keyword`, `find_files_by_glob` | `find`, `ls` |
| **Read files** | `get_file_text_by_path` | `cat`, `head` |
| **Edit files** | `replace_text_in_file` | `sed`, `awk` |
| **Search content** | `search_in_files_by_text`, `search_in_files_by_regex` | `grep`, `rg` |
| **File structure** | `list_directory_tree` | `ls -R`, `tree` |
| **Symbol info** | `get_symbol_info` | Manual code reading |
| **Refactoring** | `rename_refactoring` | Text search-replace |
| **Run tests** | `execute_run_configuration` | Manual bash commands |
| **File operations** | `create_new_file` | `touch`, `mkdir` |

### Example Workflows

```python
# ✅ CORRECT: Find all test files
find_files_by_glob(globPattern="test_*.py")

# ❌ WRONG: Using bash
bash("find . -name 'test_*.py'")

# ✅ CORRECT: Search for a function
search_in_files_by_text(searchText="def memory_router")

# ❌ WRONG: Using grep
bash("grep -r 'def memory_router' .")

# ✅ CORRECT: Refactor/rename
rename_refactoring(
    pathInProject="memory_router.py",
    symbolName="old_function_name",
    newName="new_function_name"
)

# ❌ WRONG: Text replacement
edit("memory_router.py", old_string="old_function_name", new_string="new_function_name")
```

---

## Requirements

### System Requirements
- **Python**: 3.13+ (required)
- **LiteLLM CLI**: Standalone binary
  ```bash
  # Install with uvx (recommended)
  uvx install 'litellm[proxy]'

  # Or with pipx
  pipx install 'litellm[proxy'

  # Verify installation
  litellm --version
  ```
- **Package Manager**: Poetry (preferred, but any pyproject.toml-compatible manager works)

### API Keys
Set these environment variables:
```bash
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
export SUPERMEMORY_API_KEY="sm_..."  # Optional
```

### Python Dependencies
All managed via Poetry:
```bash
poetry install
```

Key dependencies: FastAPI, Uvicorn, httpx, PyYAML, pytest

---

## Project Structure

```
litellm/
├── config.yaml                          # Main configuration (models, routing, memory)
├── litellm_proxy_with_memory.py         # Memory routing proxy (FastAPI app)
├── memory_router.py                     # Client detection & routing logic
├── start_proxies.py                     # Launch script (starts both proxies)
├── example_complete_workflow.py         # Usage examples
├── test_memory_proxy.py                 # Main test suite
├── test_tutorial.py                     # Tutorial tests
├── RUN_TESTS.sh                         # Test runner script
├── verify_setup.sh                      # Setup verification
├── docs/
│   ├── INDEX.md                         # Documentation hub
│   ├── architecture/OVERVIEW.md         # Architectural patterns
│   ├── getting-started/
│   │   ├── QUICKSTART.md               # 5-minute quick start
│   │   └── TUTORIAL.md                 # Step-by-step tutorial
│   ├── guides/
│   │   ├── testing/TESTING_GUIDE.md    # Testing strategies
│   │   ├── refactoring/REFACTORING_GUIDE.md
│   │   └── migration/MIGRATION_GUIDE.md
│   └── reference/CONFIGURATION.md       # Config reference
└── README.md                            # Main readme

# Ignore these files (temporary/deprecated)
config_old.yaml                          # Will be deleted
.envrc                                   # In-progress artifact
tutorial_proxy_with_memory.py            # Will be deleted
```

---

## Quick Start

### 1. Install Dependencies
```bash
poetry install
```

### 2. Configure Environment
```bash
# Create .env or export directly
export ANTHROPIC_API_KEY="sk-ant-..."
export OPENAI_API_KEY="sk-..."
export SUPERMEMORY_API_KEY="sm_..."
```

### 3. Verify Setup
```bash
./verify_setup.sh
```

### 4. Start Proxies
```bash
# Recommended: Start both proxies together
poetry run start-proxies

# Custom ports
poetry run start-proxies --litellm-port 8765 --memoryproxy-port 8764

# Custom config
poetry run start-proxies --config ./config.yaml
```

This starts:
- **LiteLLM binary** on port 8765 (external process)
- **Memory Proxy** on port 8764 (FastAPI app, forwards to LiteLLM)

### 5. Test It Works
```bash
# Check routing info
curl http://localhost:8764/memory-routing/info \
  -H "User-Agent: OpenAIClientImpl/Java"

# Send chat request
curl http://localhost:8764/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-1234" \
  -d '{"model": "claude-sonnet-4.5", "messages": [{"role": "user", "content": "Hello!"}]}'
```

**For detailed walkthrough**, see: `docs/getting-started/QUICKSTART.md`

---

## Configuration

### config.yaml Structure

```yaml
general_settings:
  master_key: sk-1234

model_list:
  - model_name: claude-sonnet-4.5
    litellm_params:
      api_base: https://api.supermemory.ai/v3/api.anthropic.com
      model: anthropic/claude-sonnet-4-5-20250929
      api_key: os.environ/ANTHROPIC_API_KEY
      custom_llm_provider: anthropic

  - model_name: gpt-4
    litellm_params:
      model: openai/gpt-4
      api_key: os.environ/OPENAI_API_KEY

# Memory routing configuration
user_id_mappings:
  custom_header: "x-memory-user-id"
  header_patterns:
    - header: "user-agent"
      pattern: "OpenAIClientImpl/Java"
      user_id: "pycharm-ai"
    - header: "user-agent"
      pattern: "Claude Code"
      user_id: "claude-cli"
  default_user_id: "default-dev"

litellm_settings:
  set_verbose: true
  json_logs: true
  use_client_cache: true
  drop_params: true
```

**For complete reference**, see: `docs/reference/CONFIGURATION.md`

---

## Development Workflow

### Common Tasks

#### 1. Add New Model
Edit `config.yaml`:
```yaml
model_list:
  - model_name: my-new-model
    litellm_params:
      model: provider/model-name
      api_key: os.environ/MY_API_KEY
```
Test: `poetry run start-proxies`

#### 2. Add Client Detection Pattern
Edit `config.yaml`:
```yaml
user_id_mappings:
  header_patterns:
    - header: "user-agent"
      pattern: "MyApp/.*"
      user_id: "my-app-user"
```
Test: `curl http://localhost:8764/memory-routing/info -H "User-Agent: MyApp/1.0"`

#### 3. Modify Memory Routing Logic
1. Use JetBrains MCP to search: `search_in_files_by_text("memory_router")`
2. Edit `memory_router.py` using JetBrains MCP: `replace_text_in_file(...)`
3. Run tests: `./RUN_TESTS.sh unit`
4. Commit: `jj commit -m "Update memory routing logic"`

#### 4. Test with Different Providers
```bash
# Edit config.yaml to add provider
poetry run start-proxies

# Test endpoint
curl http://localhost:8764/v1/chat/completions \
  -H "Authorization: Bearer sk-1234" \
  -d '{"model": "your-model", "messages": [...]}'
```

#### 5. Maintain Backward Compatibility
- Run full test suite: `./RUN_TESTS.sh all`
- Test with existing clients (PyCharm, Claude Code)
- Check integration tests: `./RUN_TESTS.sh integration`

---

## Testing

### Run Tests (Recommended Method)
```bash
# From venv: Run all tests
./RUN_TESTS.sh

# Specific test suites
./RUN_TESTS.sh unit           # Unit tests only
./RUN_TESTS.sh integration    # Integration tests
./RUN_TESTS.sh e2e            # End-to-end tests
./RUN_TESTS.sh coverage       # With coverage report
./RUN_TESTS.sh fast           # Skip slow tests
./RUN_TESTS.sh parallel       # Parallel execution

# Debug mode
./RUN_TESTS.sh debug
```

### Alternative Methods (Discouraged)
```bash
# Direct pytest (if you must)
poetry run pytest test_memory_proxy.py -v

# Specific test file
poetry run python test_tutorial.py
```

### Test Structure
- `test_memory_proxy.py` - Main test suite (routing, FastAPI, integration)
- `test_tutorial.py` - Tutorial examples (will be deleted)
- Coverage reports: `htmlcov/index.html` (after `./RUN_TESTS.sh coverage`)

**For detailed testing strategies**, see: `docs/guides/testing/TESTING_GUIDE.md`

---

## Architecture

### High-Level Overview

```
┌─────────────────────────────────────────────┐
│ AI Clients (PyCharm, Claude Code, curl)    │
└─────────────────┬───────────────────────────┘
                  │ HTTP requests
                  ▼
┌─────────────────────────────────────────────┐
│ Memory Proxy (Port 8764) - FastAPI         │
│ • Detects client via User-Agent            │
│ • Injects x-sm-user-id header              │
│ • Routes to LiteLLM                        │
└─────────────────┬───────────────────────────┘
                  │ HTTP forward
                  ▼
┌─────────────────────────────────────────────┐
│ LiteLLM Binary (Port 8765)                 │
│ External process: litellm --config ...     │
└─────────────────┬───────────────────────────┘
                  │
         ┌────────┴────────┬──────────┐
         ▼                 ▼          ▼
   ┌─────────┐      ┌──────────┐  ┌────────┐
   │ OpenAI  │      │Supermemory│  │ Gemini │
   │   API   │      │  + Claude │  │  API   │
   └─────────┘      └──────────┘  └────────┘
```

### Key Components

1. **Memory Proxy (`litellm_proxy_with_memory.py`)**
   - FastAPI application
   - Client detection and user ID assignment
   - Header injection for memory isolation
   - Request forwarding to LiteLLM

2. **Memory Router (`memory_router.py`)**
   - Pattern matching engine
   - User-Agent parsing
   - Custom header detection
   - Configurable routing rules

3. **LiteLLM Binary**
   - External process (subprocess)
   - Multi-provider routing
   - Rate limiting, caching, logging
   - Supermemory integration

### Benefits of Binary Approach
- **Separation of concerns**: Memory logic separate from LiteLLM
- **Independent scaling**: Scale components separately
- **Version management**: Upgrade LiteLLM without code changes
- **No SDK conflicts**: Pure HTTP communication
- **Production ready**: Process isolation, better error handling

**For detailed architecture**, see: `docs/architecture/OVERVIEW.md`

---

## API Documentation

### Memory Proxy Endpoints

#### GET /memory-routing/info
Get routing information for current request.

**Headers**:
- `User-Agent`: Client identifier (optional)
- `x-memory-user-id`: Explicit user ID (optional)

**Response**:
```json
{
  "user_id": "pycharm-ai",
  "matched_pattern": {
    "header": "user-agent",
    "pattern": "OpenAIClientImpl/Java",
    "user_id": "pycharm-ai"
  },
  "custom_header_present": false,
  "is_default": false
}
```

#### POST /v1/chat/completions
OpenAI-compatible chat completions endpoint with automatic memory routing.

**Headers**:
- `Authorization`: Bearer token (required)
- `Content-Type`: application/json
- `User-Agent`: Client identifier (auto-detected)
- `x-memory-user-id`: Explicit user ID (optional, overrides detection)

**Request Body**:
```json
{
  "model": "claude-sonnet-4.5",
  "messages": [
    {"role": "user", "content": "Hello!"}
  ],
  "max_tokens": 100
}
```

**Response**: Standard OpenAI chat completion format

#### GET /health
Health check endpoint.

**Response**: `{"status": "healthy"}`

---

## Client Configuration Examples

### PyCharm AI Assistant
1. Settings → AI Assistant → OpenAI Service
2. URL: `http://localhost:8764/v1`
3. API Key: `sk-1234` (from config.yaml master_key)
4. Model: `claude-sonnet-4.5`

Auto-detected as `pycharm-ai` user.

### Claude Code
```bash
# In your shell config
export ANTHROPIC_BASE_URL="http://localhost:8764"
```

Auto-detected as `claude-cli` user.

### Custom Application
```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8764/v1",
    api_key="sk-1234"
)

# Option 1: Auto-detection via User-Agent
# (set User-Agent in your HTTP client)

# Option 2: Explicit user ID
response = client.chat.completions.create(
    model="claude-sonnet-4.5",
    messages=[{"role": "user", "content": "Hello"}],
    extra_headers={"x-memory-user-id": "my-project"}
)
```

---

## Troubleshooting

### LiteLLM binary not found
```bash
# Install with uvx
uvx install litellm

# Or pipx
pipx install litellm

# Verify
which litellm
litellm --version
```

### Memory Proxy can't connect to LiteLLM
```bash
# Check LiteLLM is running
curl http://localhost:8765/health

# Check ports in use
lsof -i :8764
lsof -i :8765

# Check logs
# (in Memory Proxy terminal output)
```

### Client not detected correctly
```bash
# Debug routing
curl http://localhost:8764/memory-routing/info \
  -H "User-Agent: YourClient/1.0"

# Check config.yaml patterns
# Ensure pattern matches your User-Agent
```

### Tests failing
```bash
# Ensure in venv
poetry shell

# Run with verbose output
./RUN_TESTS.sh debug

# Check test dependencies
poetry install --with test
```

### Import errors
```bash
# Reinstall dependencies
poetry install

# Clear cache
rm -rf __pycache__
poetry cache clear --all pypi
```

---

## Documentation Hub

This project has extensive documentation organized by topic:

- **📚 [Documentation Index](docs/INDEX.md)** - Start here for all docs
- **🏗️ [Architecture Overview](docs/architecture/OVERVIEW.md)** - System design & patterns
- **🚀 [Quick Start](docs/getting-started/QUICKSTART.md)** - 5-minute setup guide
- **📖 [Tutorial](docs/getting-started/TUTORIAL.md)** - Step-by-step walkthrough
- **🧪 [Testing Guide](docs/guides/testing/TESTING_GUIDE.md)** - Testing strategies
- **♻️ [Refactoring Guide](docs/guides/refactoring/REFACTORING_GUIDE.md)** - Code improvement patterns
- **🔄 [Migration Guide](docs/guides/migration/MIGRATION_GUIDE.md)** - Upgrade paths
- **⚙️ [Configuration Reference](docs/reference/CONFIGURATION.md)** - Complete config docs

---

## Important Notes

### Current Status
- **Phase**: Early development (v0.x)
- **Stability**: Dev only (no production deployments yet)
- **Remote**: No remote git repository yet (local only)

### Known Issues / TODOs
- `config_old.yaml` will be deleted (use `config.yaml`)
- `.envrc` is in-progress (ignore for now)
- `tutorial_proxy_with_memory.py` will be removed

### Development Philosophy
1. **Use JetBrains MCP** for all file/code operations
2. **Use jj** for version control (no git)
3. **Test with RUN_TESTS.sh** from venv
4. **Maintain backward compatibility** for existing clients
5. **Document as you go** - update relevant docs/ files

### Getting Help
- Check docs/ for detailed guides
- Use Context7 MCP for jj documentation
- Use JetBrains MCP for codebase exploration
- Review test files for usage examples

---

## Recent Updates

**2025-10-24** - Major cleanup and documentation
- Added comprehensive documentation structure (docs/)
- Created QUICKSTART.md and full tutorial
- Added test suite with RUN_TESTS.sh
- Organized project structure
- Added this CLAUDE.md file

**2 days ago** - Initial project setup
- Core memory routing implementation
- FastAPI proxy with client detection
- LiteLLM binary integration
- Basic test coverage
- Poetry configuration

---

## Contributing Workflow

### Before You Start
1. Create a new bookmark: `jj new && jj bookmark create <TOPIC>`
2. Verify tests pass: `./RUN_TESTS.sh`

### Development Process
1. Use JetBrains MCP for code exploration and editing
2. Make changes to relevant files
3. Run tests frequently: `./RUN_TESTS.sh fast`
4. Commit with clear messages: `jj commit -m "Clear description"`

### Before Merging
1. Run full test suite: `./RUN_TESTS.sh all`
2. Update documentation if needed (docs/)
3. Test with actual clients (PyCharm, Claude Code)
4. Merge into main: `jj new @ main && jj bookmark set -r @ <TOPIC>`

### Best Practices
- **Small commits**: Commit early and often
- **Clear messages**: Describe what and why, not how
- **Test coverage**: Add tests for new features
- **Backward compatibility**: Don't break existing clients
- **Documentation**: Update docs/ when adding features

---

**Happy coding! 🚀**

For questions or issues, use JetBrains MCP to explore the codebase or check the documentation in `docs/`.