# LiteLLM Memory Proxy - Gemini Agent Context

This document serves as the primary context and instruction manual for Gemini agents working on the LiteLLM Memory Proxy repository. It synthesizes development workflows, architectural details, and tool usage guidelines.

## 🚨 CRITICAL: Version Control (Jujutsu)

**DO NOT USE GIT COMMANDS.** This project uses [Jujutsu (jj)](https://github.com/martinvonz/jj).

### Essential Commands

| Task | Command |
|------|---------|
| **Status** | `run_shell_command("jj status")` |
| **New Task** | `run_shell_command("jj new && jj bookmark create <TOPIC>")` |
| **Commit** | `run_shell_command("jj commit -m 'Message'")` |
| **Undo** | `run_shell_command("jj undo")` |
| **Merge** | `run_shell_command("jj new @ main && jj bookmark set -r @ <TOPIC>")` |

**Workflow Rule:** Always create a bookmark before starting work. Prefer merges over rebases.

---

## 🛠️ Gemini Tool Usage

You have access to advanced codebase analysis tools. Use them instead of basic shell commands whenever possible.

**PRIORITY INSTRUCTION:** Always prioritize JetBrains MCP tools for file operations, code generation, and refactoring.

| Task | Preferred Tool | ❌ Avoid |
|------|----------------|----------|
| **Code Generation** | `create_new_file` | `write_file`, `touch` |
| **Edit Code** | `replace_text_in_file` | `replace`, `sed`, `write_file` |
| **Refactor** | `rename_refactoring` | Manual search/replace |
| **Code Analysis** | `get_file_problems`, `get_symbol_info` | Manual linting |
| **Explore Codebase** | `codebase_investigator(objective="...")` | Manual `ls -R` |
| **Find Files** | `find_files_by_glob`, `find_files_by_name_keyword` | `find . -name ...` |
| **Read Code** | `get_file_text_by_path` | `cat`, `less`, `read_file` |
| **Search Content** | `search_in_files_by_text`, `search_in_files_by_regex` | `grep`, `ripgrep` |
| **Analyze Structure** | `list_directory_tree` | `tree` |
| **Run Tests** | `execute_run_configuration` or `run_shell_command("./scripts/testing/RUN_TESTS.sh ...")` | `pytest` directly |

### Best Practices
1.  **Investigate First:** Use `codebase_investigator` for complex requests to understand dependencies and architecture.
2.  **Precise Edits:** Use `replace_text_in_file` for targeted changes to preserve formatting.
3.  **Verify:** Always run related tests after changes.
4.  **Refactor Safely:** Use `rename_refactoring` to ensure all references are updated atomically.

---

## 🚀 Quick Start & Setup

### Prerequisites
*   Python 3.13+
*   Poetry (dependency management)
*   LiteLLM CLI (`uvx install 'litellm[proxy]'`)

### Installation
```bash
poetry install
```

### Environment Setup
Set these environment variables (e.g., in `.env` or export):
```bash
export ANTHROPIC_API_KEY="sk-ant-..."
export OPENAI_API_KEY="sk-..."
export SUPERMEMORY_API_KEY="sm_..."
```

### Running the Project
Start the Memory Proxy (SDK mode, port 8764):
```bash
poetry run python deploy/run_unified_proxy.py --mode sdk
```

---

## 🧪 Testing Strategy

Use the provided `RUN_TESTS.sh` script for all testing needs.

| Scope | Command | Description |
|-------|---------|-------------|
| **All** | `./scripts/testing/RUN_TESTS.sh` | Run all standard tests (excluding pipeline) |
| **Unit** | `./scripts/testing/RUN_TESTS.sh unit` | Memory Proxy unit tests only |
| **Integration** | `./scripts/testing/RUN_TESTS.sh integration` | Integration tests |
| **E2E** | `./scripts/testing/RUN_TESTS.sh e2e` | End-to-end tests |
| **Fast** | `./scripts/testing/RUN_TESTS.sh fast` | Skip slow tests |
| **Coverage** | `./scripts/testing/RUN_TESTS.sh coverage` | Generate HTML coverage report |

**Test Locations:**
*   `tests/src/test_memory_proxy.py`: Main test suite.
*   `tests/test_schema_env_sync.py`: Configuration sync tests.
*   `tests/src/test_interceptor.py`: Interceptor component tests.

---

## 🏗️ Architecture Overview

**Pattern:** Self-Contained SDK Gateway

The system uses an in-process SDK approach to ensure persistent HTTP sessions (critical for Cloudflare compatibility).

1.  **Client Interceptor (Edge)**:
    *   Runs locally (e.g., port 8888).
    *   Tags requests with `x-memory-user-id`.

2.  **Memory Proxy (Core)**:
    *   FastAPI app using `litellm` Python SDK.
    *   **Session Manager**: Maintains persistent `httpx.AsyncClient` per user to preserve cookies.
    *   **Zero-Hop**: No external binary process; direct SDK calls.

### Key Files
*   `src/proxy/litellm_proxy_sdk.py`: Main FastAPI app (SDK implementation).
*   `src/proxy/session_manager.py`: Persistent session handling.
*   `src/interceptor/intercepting_contexter.py`: Edge interceptor.

---

## 📂 Project Structure

```text
litellm/
├── config/                 # Configuration files
│   ├── config.yaml         # Core configuration
│   └── config-schema.json  # Validation schema
├── deploy/                 # Deployment and startup scripts
│   └── start_proxies.py    # Orchestrator script
├── docs/                   # Comprehensive documentation
│   ├── architecture/       # Design docs
│   ├── guides/             # User guides
│   └── troubleshooting/    # Common issues
├── src/                    # Source code
│   ├── interceptor/        # CLI Interceptor component
│   └── proxy/              # Core Memory Proxy logic
│       ├── litellm_proxy_with_memory.py # Main FastAPI app
│       ├── memory_router.py             # Routing logic
│       └── config_parser.py             # Configuration handling
├── tests/                  # Test suite
│   └── src/                # Source tests
├── RUN_TESTS.sh            # Test runner
├── CLAUDE.md               # Context for Claude agents
└── GEMINI.md               # Context for Gemini agents (This file)
```

---

## 🗺️ Modernization Roadmap

The following tasks are identified to modernize the codebase and align documentation with reality:

1.  **Documentation Sync:**
    *   Update `docs/architecture/OVERVIEW.md` to reflect the `src/` directory structure.
    *   Update `README.md` and `CLAUDE.md` with correct file paths.

2.  **Root Cleanup:**
    *   Move root-level utility scripts (e.g., `add_context_config.py`, `diagnose_503.py`) to a dedicated `scripts/` directory or `archive/`.
    *   Remove obsolete backup files (`pyproject.toml.b`).
    *   Move root-level tests (`test_*.py`) to `tests/`.

3.  **Entry Point Standardization:**
    *   Formalize `deploy/start_proxies.py` as a proper CLI entry point (e.g., `litellm-memory start`).
    *   Ensure `pyproject.toml` scripts correctly point to reachable modules.

4.  **Dependency Management:**
    *   Verify `pyproject.toml` dependencies against actual imports (some root scripts might have unlisted deps).
