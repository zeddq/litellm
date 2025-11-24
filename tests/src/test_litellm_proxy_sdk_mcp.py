from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.proxy.litellm_proxy_sdk import app


from src.proxy.schema import LiteLLMProxyConfig, MCPServerConfig, MCPTransport

@pytest.fixture
def mock_litellm_mcp():
    with patch("src.proxy.litellm_proxy_sdk.litellm") as mock:
        # Mock load_mcp_tools
        mock.experimental_mcp_client.load_mcp_tools = AsyncMock(
            return_value=[
                {
                    "type": "function",
                    "function": {
                        "name": "mcp_test_tool",
                        "description": "A test tool",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            ]
        )

        # Mock call_openai_tool
        mock.experimental_mcp_client.call_openai_tool = AsyncMock(
            return_value={"result": "success"}
        )

        # Mock acompletion
        mock.acompletion = AsyncMock()

        yield mock


@pytest.fixture
def client():
    return TestClient(app)


@pytest.mark.asyncio
async def test_mcp_flow(mock_litellm_mcp, client):
    """
    Test the full MCP flow:
    1. Startup loads tools
    2. Request injects tools
    3. Tool execution calls call_openai_tool
    """
    # 1. Setup Mock Config
    with patch("src.proxy.litellm_proxy_sdk.LiteLLMConfig") as MockConfig:
        mock_config_instance = MagicMock()
        mock_config_instance.get_master_key.return_value = "sk-1234"
        mock_config_instance.get_litellm_params.return_value = {"model": "gpt-4"}
        mock_config_instance.get_all_models.return_value = ["gpt-4"]
        mock_config_instance.get_litellm_settings.return_value = {}
        
        mock_config_instance.config.general_settings = MagicMock()
        mock_config_instance.config.general_settings.master_key = "sk-1234"

        # Configure MCP servers
        mcp_server_config_mock = MagicMock(spec=MCPServerConfig)
        mcp_server_config_mock.transport = MCPTransport.STDIO
        mcp_server_config_mock.command = "echo"
        mcp_server_config_mock.args = ["hello"]
        mcp_server_config_mock.url = None

        mock_config_instance.config.mcp_servers = {
            "test_server": mcp_server_config_mock
        }
        mock_config_instance.config.tool_execution = {} # Disable supermemory tools

        MockConfig.return_value = mock_config_instance

        # 2. Startup
        with TestClient(app) as test_client:
            # Verify load_mcp_tools called
            mock_litellm_mcp.experimental_mcp_client.load_mcp_tools.assert_called()

            # 3. Request with Tool Call
            # Mock acompletion to return a tool call first, then final response

            # Tool Call Response
            mock_function = MagicMock()
            mock_function.name = "mcp_test_tool"
            mock_function.arguments = "{}"

            mock_tool_call_obj = MagicMock()
            mock_tool_call_obj.id = "call_1"
            mock_tool_call_obj.function = mock_function
            mock_tool_call_obj.type = "function"
            
            tool_call_msg = MagicMock()
            tool_call_msg.tool_calls = [mock_tool_call_obj]
            tool_call_msg.content = None
            
            # Mock Choices for tool call
            choice1 = MagicMock()
            choice1.message = tool_call_msg
            choice1.finish_reason = "tool_calls"

            mock_response_1 = MagicMock()
            mock_response_1.choices = [choice1]
            # Mock model_dump for serialization in handle_non_streaming
            mock_response_1.model_dump.return_value = {
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "function": {
                                        "name": "mcp_test_tool",
                                        "arguments": "{}",
                                    },
                                    "type": "function",
                                }
                            ]
                        }
                    }
                ]
            }

            # Final Response
            final_msg = MagicMock()
            final_msg.tool_calls = None
            final_msg.content = "Tool executed."

            choice2 = MagicMock()
            choice2.message = final_msg
            choice2.finish_reason = "stop"

            mock_response_2 = MagicMock()
            mock_response_2.choices = [choice2]
            mock_response_2.model_dump.return_value = {
                "choices": [{"message": {"content": "Tool executed."}}]
            }

            mock_litellm_mcp.acompletion.side_effect = [
                mock_response_1,
                mock_response_2,
            ]

            response = test_client.post(
                "/v1/chat/completions",
                headers={"Authorization": "Bearer sk-1234"},
                json={
                    "model": "gpt-4",
                    "messages": [{"role": "user", "content": "Run mcp tool"}],
                },
            )

            assert response.status_code == 200

            # Verify injection
            call_args_list = mock_litellm_mcp.acompletion.call_args_list
            first_call_kwargs = call_args_list[0].kwargs
            assert "tools" in first_call_kwargs
            assert len(first_call_kwargs["tools"]) == 1
            assert first_call_kwargs["tools"][0]["function"]["name"] == "mcp_test_tool"

            # Verify execution
            mock_litellm_mcp.experimental_mcp_client.call_openai_tool.assert_called()

            # Verify loop (2 calls to acompletion)
            assert mock_litellm_mcp.acompletion.call_count == 2
