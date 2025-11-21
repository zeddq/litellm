import json
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from proxy.litellm_proxy_sdk import app

# Create test client
client = TestClient(app)


@pytest.fixture
def valid_auth_header():
    return {"Authorization": "Bearer sk-1234"}


@pytest.fixture
def mock_litellm_acompletion():
    with patch("litellm.acompletion") as mock:
        mock.return_value = MagicMock()
        mock.return_value.model_dump.return_value = {
            "choices": [{"message": {"content": "Hello", "role": "assistant"}}]
        }
        yield mock


def test_content_length_match(valid_auth_header, mock_litellm_acompletion):
    """Test request with matching Content-Length."""
    payload = {"model": "gpt-4", "messages": [{"role": "user", "content": "Hello"}]}

    # TestClient automatically calculates correct Content-Length
    response = client.post(
        "/v1/chat/completions", json=payload, headers=valid_auth_header
    )

    assert response.status_code == 200


def test_content_length_mismatch_too_short(valid_auth_header):
    """Test request where Content-Length < Actual Body."""
    payload = {"model": "gpt-4", "messages": [{"role": "user", "content": "Hello"}]}
    body = json.dumps(payload).encode()

    # Manually construct request with wrong Content-Length
    # We claim it's shorter than it is
    headers = valid_auth_header.copy()
    headers["Content-Length"] = str(len(body) - 5)

    # Note: TestClient might recalculate unless we are careful.
    # But usually it respects provided headers.
    response = client.post("/v1/chat/completions", content=body, headers=headers)

    # Expect 400 Bad Request from our middleware
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "content_length_mismatch"


def test_content_length_mismatch_too_long(valid_auth_header):
    """Test request where Content-Length > Actual Body."""
    payload = {"model": "gpt-4", "messages": [{"role": "user", "content": "Hello"}]}
    body = json.dumps(payload).encode()

    # We claim it's longer than it is
    headers = valid_auth_header.copy()
    headers["Content-Length"] = str(len(body) + 5)

    response = client.post("/v1/chat/completions", content=body, headers=headers)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "content_length_mismatch"


def test_pydantic_validation_missing_model(valid_auth_header):
    """Test Pydantic validation for missing required field."""
    payload = {
        # "model": "gpt-4",  # Missing model
        "messages": [{"role": "user", "content": "Hello"}]
    }

    response = client.post(
        "/v1/chat/completions", json=payload, headers=valid_auth_header
    )

    # FastAPI returns 422 for validation errors
    assert response.status_code == 422


def test_pydantic_validation_extra_fields(valid_auth_header, mock_litellm_acompletion):
    """Test Pydantic validation allows extra fields."""
    payload = {
        "model": "gpt-4",
        "messages": [{"role": "user", "content": "Hello"}],
        "temperature": 0.7,
        "custom_param": "allowed",
    }

    response = client.post(
        "/v1/chat/completions", json=payload, headers=valid_auth_header
    )

    assert response.status_code == 200
