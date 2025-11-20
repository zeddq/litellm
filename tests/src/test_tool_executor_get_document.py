import pytest
from unittest.mock import AsyncMock, Mock, patch
from proxy.tool_executor import ToolExecutor, ToolExecutionError

class TestToolExecutorGetDocument:
    @pytest.fixture
    def mock_supermemory_client(self):
        with patch("proxy.tool_executor.Supermemory") as MockSupermemory:
            mock_client = Mock()
            MockSupermemory.return_value = mock_client
            # Setup documents.get
            mock_client.documents.get = Mock()
            yield mock_client

    @pytest.fixture
    def executor(self, mock_supermemory_client):
        return ToolExecutor(
            supermemory_api_key="test-key",
            supermemory_base_url="http://test-url"
        )

    @pytest.mark.asyncio
    async def test_get_tool_definitions(self, executor):
        """Verify tool definitions include both search and get document."""
        definitions = executor.get_tool_definitions()
        assert len(definitions) == 2
        
        tool_names = [d["function"]["name"] for d in definitions]
        assert "supermemoryToolSearch" in tool_names
        assert "supermemoryToolGetDocument" in tool_names
        
        # Check get document schema
        get_doc_def = next(d for d in definitions if d["function"]["name"] == "supermemoryToolGetDocument")
        assert "id" in get_doc_def["function"]["parameters"]["required"]

    @pytest.mark.asyncio
    async def test_execute_get_document_success(self, executor, mock_supermemory_client):
        """Test successful document retrieval."""
        # Mock response
        mock_doc = Mock()
        mock_doc.id = "doc-123"
        mock_doc.title = "Test Doc"
        mock_doc.content = "This is test content"
        mock_doc.url = "http://example.com/doc"
        mock_doc.type = "document"
        mock_doc.metadata = {"author": "Test"}
        
        mock_supermemory_client.documents.get.return_value = mock_doc

        result = await executor.execute_tool_call(
            tool_name="supermemoryToolGetDocument",
            tool_args={"id": "doc-123"},
            user_id="test-user",
            tool_call_id="call_1"
        )

        assert result["tool_call_id"] == "call_1"
        assert result["results_count"] == 1
        assert result["results"][0]["id"] == "doc-123"
        assert result["results"][0]["title"] == "Test Doc"
        assert result["results"][0]["content"] == "This is test content"
        
        mock_supermemory_client.documents.get.assert_called_once_with(id="doc-123")

    @pytest.mark.asyncio
    async def test_execute_get_document_aliases(self, executor, mock_supermemory_client):
        """Test argument aliases for document ID."""
        mock_doc = Mock()
        mock_doc.id = "doc-123"
        mock_supermemory_client.documents.get.return_value = mock_doc

        aliases = ["document_id", "doc_id", "uuid"]
        
        for alias in aliases:
            await executor.execute_tool_call(
                tool_name="supermemoryToolGetDocument",
                tool_args={alias: "doc-123"},
                user_id="test-user",
                tool_call_id="call_1"
            )
            mock_supermemory_client.documents.get.assert_called_with(id="doc-123")

    @pytest.mark.asyncio
    async def test_execute_get_document_missing_id(self, executor):
        """Test missing ID error handling."""
        result = await executor.execute_tool_call(
            tool_name="supermemoryToolGetDocument",
            tool_args={"wrong_param": "value"},
            user_id="test-user",
            tool_call_id="call_1"
        )

        assert "error" in result
        assert result["error"]["type"] == "missing_parameter"
        assert "wrong_param" in result["error"]["message"]

    @pytest.mark.asyncio
    async def test_execute_get_document_execution_error(self, executor, mock_supermemory_client):
        """Test handling of SDK errors."""
        mock_supermemory_client.documents.get.side_effect = Exception("Not found")

        result = await executor.execute_tool_call(
            tool_name="supermemoryToolGetDocument",
            tool_args={"id": "doc-123"},
            user_id="test-user",
            tool_call_id="call_1"
        )

        assert "error" in result
        assert result["error"]["type"] == "execution_error"
        assert "Not found" in result["error"]["message"]
