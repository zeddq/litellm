#!/usr/bin/env python3
"""
Add context_retrieval documentation to CONFIGURATION.md.
Inserts the section after user_id_mappings and before model_list.
"""

from pathlib import Path


def add_context_retrieval_docs():
    """Add context_retrieval documentation section."""
    config_docs_path = Path("docs/guides/CONFIGURATION.md")

    if not config_docs_path.exists():
        print(f"Error: {config_docs_path} not found!")
        return False

    # Read the current documentation
    content = config_docs_path.read_text()
    lines = content.splitlines(keepends=True)

    # Find the line "### 3. model_list"
    insertion_index = None
    for i, line in enumerate(lines):
        if line.strip() == "### 3. model_list":
            insertion_index = i
            break

    if insertion_index is None:
        print("Error: Could not find '### 3. model_list' line")
        return False

    # Also need to update the TOC
    toc_update_needed = False
    for i, line in enumerate(lines):
        if "3. [Configuration Sections](#configuration-sections)" in line:
            # We should add context_retrieval to TOC, but let's skip for now
            pass

    # Documentation section to add
    context_retrieval_docs = """### 3. context_retrieval

Enables automatic retrieval and injection of relevant context from Supermemory into prompts.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `enabled` | boolean | No | Enable/disable context retrieval globally (default: false) |
| `api_key` | string | Yes* | Supermemory API key (use os.environ/SUPERMEMORY_API_KEY) |
| `base_url` | string | No | Supermemory API base URL (default: https://api.supermemory.ai) |
| `query_strategy` | string | No | How to extract query from messages (default: last_user) |
| `injection_strategy` | string | No | Where to inject context (default: system) |
| `container_tag` | string | No | Supermemory container tag (default: supermemory) |
| `max_context_length` | integer | No | Max context characters (100-100000, default: 4000) |
| `max_results` | integer | No | Max results to retrieve (1-20, default: 5) |
| `timeout` | float | No | API timeout in seconds (1.0-60.0, default: 10.0) |
| `enabled_for_models` | array | No | Whitelist of models (default: all models) |
| `disabled_for_models` | array | No | Blacklist of models (cannot use with enabled_for_models) |

*Required only if `enabled: true`

#### Query Strategies

Controls how the query is extracted from the message history for context retrieval:

- **`last_user`** (default): Use only the last user message as the query
- **`first_user`**: Use only the first user message as the query
- **`all_user`**: Concatenate all user messages as the query (separated by " | ")
- **`last_assistant`**: Use the last assistant message as the query (useful for follow-ups)

#### Injection Strategies

Controls where the retrieved context is injected into the message list:

- **`system`** (default, recommended): Add context as a system message at the start
  - Best for models like Claude that support system messages
  - Context is clearly separated from user content
- **`user_prefix`**: Prepend context to the first user message
  - Useful for models that don't support system messages
  - Context appears before user's first question
- **`user_suffix`**: Append context to the last user message
  - Context appears right before the model generates a response
  - Useful for emphasizing recent context

#### Model Filtering

You can control which models use context retrieval:

**Option 1: Whitelist (enabled_for_models)**
```yaml
context_retrieval:
  enabled: true
  enabled_for_models:
    - claude-sonnet-4.5
    - claude-haiku-4.5
  # Only these models will use context retrieval
```

**Option 2: Blacklist (disabled_for_models)**
```yaml
context_retrieval:
  enabled: true
  disabled_for_models:
    - gpt-5-pro
  # All models except gpt-5-pro will use context retrieval
```

**Option 3: All models (no filters)**
```yaml
context_retrieval:
  enabled: true
  # All models will use context retrieval
```

**Note:** You cannot specify both `enabled_for_models` and `disabled_for_models` - use one or the other.

#### Complete Example

```yaml
context_retrieval:
  # Enable context retrieval globally
  enabled: true

  # API configuration
  api_key: os.environ/SUPERMEMORY_API_KEY
  base_url: https://api.supermemory.ai

  # Query and injection strategies
  query_strategy: last_user        # Use last user message as query
  injection_strategy: system       # Inject as system message

  # Supermemory configuration
  container_tag: supermemory       # Container to search in
  max_context_length: 4000         # Max characters in context
  max_results: 5                   # Max memories to retrieve
  timeout: 10.0                    # API timeout

  # Enable only for specific models
  enabled_for_models:
    - claude-sonnet-4.5
    - claude-haiku-4.5
```

#### Minimal Example

```yaml
context_retrieval:
  enabled: true
  api_key: os.environ/SUPERMEMORY_API_KEY
```

#### How It Works

1. **Query Extraction**: When a chat request comes in, the system extracts a query from the message history using the configured `query_strategy`

2. **Context Retrieval**: The query is sent to Supermemory's `/v4/profile` endpoint with the user's ID (from memory routing) to retrieve relevant memories/documents

3. **Context Injection**: Retrieved context is formatted and injected into the message list using the configured `injection_strategy`

4. **Request Forwarding**: The enhanced messages (with context) are forwarded to the LLM provider

5. **Graceful Degradation**: If context retrieval fails for any reason, the original messages are used (no request failure)

#### Error Handling

Context retrieval is designed to fail gracefully:

- If the Supermemory API is unavailable, requests continue with original messages
- If the API key is missing/invalid, a warning is logged and requests proceed normally
- If the API times out, the timeout error is logged and original messages are used
- All context retrieval errors are logged but don't affect the primary request

#### Performance Considerations

- **Cookie Persistence**: The proxy uses a persistent HTTP client to maintain Cloudflare cookies, avoiding rate limiting
- **Timeout Configuration**: Set `timeout` based on your latency requirements (longer = more reliable, shorter = faster)
- **Max Results**: Fewer results (`max_results`) = faster retrieval and less context
- **Max Context Length**: Shorter context (`max_context_length`) = faster processing and lower token costs

#### Usage Tips

1. **Start Simple**: Begin with minimal configuration and only enable for one model
2. **Monitor Logs**: Check logs to see query extraction and context retrieval in action
3. **Tune Strategies**: Experiment with different query and injection strategies for your use case
4. **User Isolation**: Context retrieval respects user ID routing - each user sees only their memories
5. **API Key Security**: Always use environment variables for the API key, never hardcode

---

### 4. model_list
"""

    # Update section numbering in the content
    # We need to increment all section numbers >= 3
    updated_lines = []
    for line in lines[:insertion_index]:
        # Update TOC if needed
        if "3. [Configuration Sections]" in line:
            updated_lines.append(line)  # Keep as is, we're adding a subsection
        else:
            updated_lines.append(line)

    # Insert new section
    updated_lines.append(context_retrieval_docs)

    # Update remaining lines with incremented section numbers
    for line in lines[insertion_index:]:
        # Update section headers (### 3. -> ### 4., ### 4. -> ### 5., etc.)
        if line.startswith("### "):
            parts = line.split(".", 1)
            if len(parts) == 2 and parts[0].strip().startswith("### "):
                try:
                    section_num_part = parts[0].replace("###", "").strip()
                    section_num = int(section_num_part)
                    if section_num >= 3:
                        line = f"### {section_num + 1}.{parts[1]}"
                except ValueError:
                    pass  # Not a numbered section
        updated_lines.append(line)

    # Write back to file
    config_docs_path.write_text("".join(updated_lines))

    print(f"✅ Successfully added context_retrieval documentation to {config_docs_path}")
    print(f"   Inserted before line {insertion_index + 1}")
    print(f"   Updated section numbering (3+ -> 4+)")
    return True


if __name__ == "__main__":
    success = add_context_retrieval_docs()
    exit(0 if success else 1)