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

| Task | Preferred Tool | ❌ Avoid |
|------|----------------|----------|
| **Explore Codebase** | `codebase_investigator(objective="...")` | Manual `ls -R` |
| **Find Files** | `find_files_by_glob`, `find_files_by_name_keyword` | `find . -name ...` |
| **Read Code** | `get_file_text_by_path` | `cat`, `less` |
| **Search Content** | `search_in_files_by_text`, `search_in_files_by_regex` | `grep`, `ripgrep` |
| **Analyze Structure** | `list_directory_tree`, `get_symbol_info` | `tree` |
| **Edit Code** | `replace_text_in_file` | `sed`, `write_file` (for small edits) |
| **Refactor** | `rename_refactoring` | Manual search/replace |
| **Run Tests** | `execute_run_configuration` or `run_shell_command("./RUN_TESTS.sh ...")` | `pytest` directly |

### Best Practices
1.  **Investigate First:** Use `codebase_investigator` for complex requests to understand dependencies and architecture.
2.  **Precise Edits:** Use `replace_text_in_file` for targeted changes to preserve formatting.
3.  **Verify:** Always run related tests after changes.

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
Start both the Memory Proxy (port 8764) and LiteLLM (port 8765):
```bash
poetry run start-proxies
```

---

## 🧪 Testing Strategy

Use the provided `RUN_TESTS.sh` script for all testing needs.

| Scope | Command | Description |
|-------|---------|-------------|
| **All** | `./RUN_TESTS.sh` | Run all standard tests (excluding pipeline) |
| **Unit** | `./RUN_TESTS.sh unit` | Memory Proxy unit tests only |
| **Integration** | `./RUN_TESTS.sh integration` | Integration tests |
| **E2E** | `./RUN_TESTS.sh e2e` | End-to-end tests |
| **Fast** | `./RUN_TESTS.sh fast` | Skip slow tests |
| **Coverage** | `./RUN_TESTS.sh coverage` | Generate HTML coverage report |

**Test Locations:**
*   `tests/src/test_memory_proxy.py`: Main test suite.
*   `tests/test_schema_env_sync.py`: Configuration sync tests.
*   `tests/src/test_interceptor.py`: Interceptor component tests.

---

## 🏗️ Architecture Overview

**Pattern:** External Binary Proxy

The system consists of two main components running as separate processes:

1.  **Memory Proxy (FastAPI, Port 8764)**:
    *   Handles client connections.
    *   Detects client identity via `User-Agent` or `x-memory-user-id`.
    *   Routes requests to LiteLLM.
    *   Injects memory context.

2.  **LiteLLM Binary (External, Port 8765)**:
    *   Manages LLM provider connections (OpenAI, Anthropic, etc.).
    *   Handles rate limiting and caching.

### Key Files
*   `config.yaml`: Main configuration (models, routing, memory).
*   `litellm_proxy_with_memory.py`: FastAPI app entry point.
*   `memory_router.py`: Client detection and routing logic.
*   `start_proxies.py`: Orchestrator script.

---

## 📂 Project Structure

```text
litellm/
├── config.yaml             # Core configuration
├── litellm_proxy_with_memory.py # Main proxy application
├── memory_router.py        # Routing logic
├── start_proxies.py        # Startup script
├── RUN_TESTS.sh            # Test runner
├── CLAUDE.md               # Context for Claude agents
├── GEMINI.md               # Context for Gemini agents (This file)
├── docs/                   # Comprehensive documentation
│   ├── architecture/       # Design docs
│   ├── guides/             # User guides
│   └── troubleshooting/    # Common issues
└── tests/                  # Test suite
```
