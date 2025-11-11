#!/usr/bin/env python3
"""
PyCharm AI Chat Interceptor Proxy
Adds custom headers and injects instance identification into requests.
"""
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
import httpx
import os
import socket
import logging
import json

from starlette import status

from proxy.error_handlers import ErrorResponse

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

app = FastAPI(debug=True)

import os
from pathlib import Path
from .port_registry import PortRegistry

# Configuration
# If INTERCEPTOR_PORT is explicitly set, use it; otherwise use registry
EXPLICIT_PORT = os.getenv("INTERCEPTOR_PORT")
if EXPLICIT_PORT:
    INTERCEPTOR_PORT = int(EXPLICIT_PORT)
    logger.info(f"Using explicitly configured port: {INTERCEPTOR_PORT}")
else:
    # Get or allocate port from registry based on project path
    project_path = str(Path.cwd().resolve())
    registry = PortRegistry()
    INTERCEPTOR_PORT = registry.get_or_allocate_port(project_path)
    logger.info(f"Using registry-assigned port: {INTERCEPTOR_PORT} for project: {project_path}")
TARGET_LLM_URL = os.getenv("TARGET_LLM_URL", "http://localhost:8764")
INSTANCE_ID = (
    os.getenv("SUPERMEMORY_USERNAME")
    or f"pycharm-{Path(os.getcwd()).stem}"
)
INJECT_INTO_CONTENT = os.getenv("INJECT_INSTANCE_ID", "true").lower() == "true"

CUSTOM_HEADERS = {
    "x-memory-user-id": INSTANCE_ID,
    "x-pycharm-instance": INSTANCE_ID,
    "x-source": "pycharm-ai-chat",
}

logger.info(f"Instance ID: {INSTANCE_ID}")
logger.info(f"Target URL: {TARGET_LLM_URL}")
logger.info(f"Inject into content: {INJECT_INTO_CONTENT}")


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "instance_id": INSTANCE_ID,
        "target": TARGET_LLM_URL,
    }


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy_request(request: Request, path: str):
    """Forward requests with custom headers and instance identification."""
    target_url = f"{TARGET_LLM_URL}/{path}"

    # Copy headers and add custom ones
    headers = request.headers.mutablecopy()
    del headers["host"]
    headers.update(CUSTOM_HEADERS)
    
    if not "chat/completions" in path:
        # Standard response
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.request(
                method=request.method,
                url=target_url,
                headers=headers,
                content=await request.body(),
            )

            return JSONResponse(
                content=(
                    response.json()
                    if response.headers.get("content-type", "").startswith(
                        "application/json"
                    )
                    else {"response": response.text}
                ),
                status_code=response.status_code,
            )

    # Get request body
    try:
        body = await request.json()
    except Exception as e:
        logger.error(f"Failed to parse request body: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid JSON in request body: {e}",
        )

    logger.info(f"→ {request.method} {target_url}")
    logger.info(f"  Headers: {CUSTOM_HEADERS}")
    logger.info(f"BODY: {str(body)}")

    stream = body.get("stream", False)

    if stream:
        async def gen_chunks():
            async with httpx.AsyncClient(timeout=300.0) as client:
                # Check if streaming
                # Stream response
                async with client.stream(
                    method=request.method,
                    url=target_url,
                    headers=headers,
                    json=body,  # Use json parameter for dict
                ) as response:
                    async for chunk in response.aiter_bytes():
                        yield chunk

        return StreamingResponse(
            gen_chunks(),
            media_type="text/event-stream",
        )
    else:
        # Standard response
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.request(
                method=request.method,
                url=target_url,
                headers=headers,
                json=body,  # Use json parameter for dict
            )

            return JSONResponse(
                content=(
                    response.json()
                    if response.headers.get("content-type", "").startswith(
                        "application/json"
                    )
                    else {"response": response.text}
                ),
                status_code=response.status_code,
            )


if __name__ == "__main__":
    import uvicorn

    logger.info("=" * 60)
    logger.info("PyCharm AI Chat Interceptor")
    logger.info("=" * 60)
    logger.info(f"Instance ID: {INSTANCE_ID}")
    logger.info(f"Listening on: http://0.0.0.0:{INTERCEPTOR_PORT}")
    logger.info(f"Forwarding to: {TARGET_LLM_URL}")
    logger.info(f"Custom headers: {CUSTOM_HEADERS}")
    logger.info("=" * 60)

    uvicorn.run(app, host="0.0.0.0", port=INTERCEPTOR_PORT)
