#!/usr/bin/env python3
"""
Add context_retrieval configuration section to config.yaml.
This script inserts the configuration after the user_id_mappings section.
"""

from pathlib import Path


def add_context_retrieval_config():
    """Add context_retrieval section to config.yaml after user_id_mappings."""
    config_path = Path("config/config.yaml")

    if not config_path.exists():
        print(f"Error: {config_path} not found!")
        return False

    # Read the current config
    content = config_path.read_text()
    lines = content.splitlines(keepends=True)

    # Find the line with 'default_user_id: "default-dev"'
    insertion_index = None
    for i, line in enumerate(lines):
        if 'default_user_id: "default-dev"' in line:
            insertion_index = i + 1  # Insert after this line
            break

    if insertion_index is None:
        print("Error: Could not find 'default_user_id' line in config.yaml")
        return False

    # Configuration section to add
    context_retrieval_config = """
# Context retrieval configuration for Supermemory integration
# Enables automatic retrieval and injection of relevant context from Supermemory
context_retrieval:
  # Enable/disable context retrieval globally
  enabled: true

  # Supermemory API key (use environment variable for security)
  api_key: os.environ/SUPERMEMORY_API_KEY

  # Supermemory API base URL
  base_url: https://api.supermemory.ai

  # Query extraction strategy:
  # - last_user: Use only the last user message as query
  # - first_user: Use only the first user message as query
  # - all_user: Concatenate all user messages as query
  # - last_assistant: Use the last assistant message as query (for follow-ups)
  query_strategy: last_user

  # Context injection strategy:
  # - system: Inject as a system message (recommended for most models)
  # - user_prefix: Prepend to the first user message
  # - user_suffix: Append to the last user message
  injection_strategy: system

  # Container tag for Supermemory organization
  container_tag: supermemory

  # Maximum length of retrieved context in characters (100-100000)
  max_context_length: 4000

  # Maximum number of context results to retrieve (1-20)
  max_results: 5

  # API request timeout in seconds (1.0-60.0)
  timeout: 10.0

  # Enable context retrieval only for specific models (whitelist approach)
  # If specified, only these models will use context retrieval
  # Leave empty or null to enable for all models
  enabled_for_models:
    - claude-sonnet-4.5
    - claude-haiku-4.5

  # Disable context retrieval for specific models (blacklist approach)
  # Cannot be used together with enabled_for_models
  # disabled_for_models:
  #   - gpt-5-pro

"""

    # Insert the configuration
    lines.insert(insertion_index, context_retrieval_config)

    # Write back to file
    config_path.write_text("".join(lines))

    print(f"✅ Successfully added context_retrieval configuration to {config_path}")
    print(f"   Inserted after line {insertion_index}")
    return True


if __name__ == "__main__":
    success = add_context_retrieval_config()
    exit(0 if success else 1)
