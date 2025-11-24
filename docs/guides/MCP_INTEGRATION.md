# MCP (Model Context Protocol) Integration

This proxy supports the [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) via
`litellm.experimental_mcp_client`. This allows you to connect standard MCP servers (stdio or SSE) and expose their tools
to any LLM supported by LiteLLM.

## Configuration

Configure MCP servers in your `config.yaml`:

```yaml
mcp_servers:
  # STDIO Transport (local processes)
  filesystem:
    transport: stdio
    command: "npx"
    args: ["-y", "@modelcontextprotocol/server-filesystem", "/Users/username/Desktop"]
    
  # SSE Transport (remote servers)
  weather_server:
    transport: sse
    url: "http://localhost:8000/sse"
```

## How it Works

1. **Initialization**: On startup, the proxy connects to all configured MCP servers and loads their tools.
2. **Injection**: When you make a request to `/v1/chat/completions`, the loaded MCP tools are automatically injected
   into the `tools` parameter sent to the LLM.
3. **Execution**: If the LLM decides to call an MCP tool, the proxy intercepts the tool call, executes it against the
   appropriate MCP server, and (in non-streaming mode) returns the result to the LLM for a final response.

## Supported Features

- **Transports**: `stdio` and `sse`.
- **Tool Execution**: Automatic execution for non-streaming requests.
- **Streaming**: Support for tool execution in streaming mode (tools are executed, result logged/streamed).

## Testing

You can test the integration using the included test suite:

```bash
./scripts/testing/RUN_TESTS.sh
```
