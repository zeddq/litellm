"""
LiteLLM Proxy Wrapper
Adds custom authentication headers to requests forwarded to LiteLLM.
"""

import json
import logging
import os
import uuid
from typing import Optional
from unittest import case

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, Response
from litellm.types.llms.anthropic import AnthropicThinkingParam
from pydantic.v1 import NumberNotGeError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(filename)s:%(lineno)d:%(funcName)s() | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="LiteLLM Auth Proxy")

# Configuration
LITELLM_URL = "http://localhost:4000"
CUSTOM_HEADERS = {
    "Authorization": f"Bearer {os.environ.get('LITELLM_VIRTUAL_KEY', '')}",
}


def round_thinking(th: int):
    match th:
        case n if n < 100:
            return 0
        case n if n < 1500:
            return 1024
        case n if n < 2400:
            return 2048
        case _:
            return 4096

@app.api_route(
    "/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"]
)
async def proxy(request: Request, path: str):
    """
    Proxy all requests to LiteLLM with custom authentication headers.
    """
    rid = str(uuid.uuid4())[:4]

    try:
        # Build the target URL
        url = f"{LITELLM_URL}/{path}"
        if request.query_params:
            url = f"{url}?{request.query_params}"

        request_body = await request.body()
        logger.info(f"{rid} REQUEST: {request.method.upper()} {url}")
        if request_body:
            logger.info(
                f"{rid} BODY: {request_body.decode()[:200]}..."
            )  # Log first 200 chars

        # Prepare headers
        headers = request.headers.mutablecopy()
        del headers["host"]
        for k, v in CUSTOM_HEADERS.items():
            headers[k] = v
        logger.info(f"{rid} HEADERS: {headers}")

        # Check if this is a streaming request
        is_stream_request = False
        changed = False
        if request_body:
            new_body = _adapt_llm_req_params(rid, request_body)
            
            logger.info(f"{rid} Stream request: {is_stream_request}")
            request_body = json.dumps(new_body)
            
        if is_stream_request:
            return _streaming_response(rid, url, request.method, headers, request_body)
        else:
            # Non-streaming response
            return await _standard_response(rid, url, request.method, headers, request_body)

    except httpx.RequestError as e:
        logger.error(f"{rid} Proxy error: {e}")
        return Response(content=f"Proxy error: {str(e)}", status_code=502)
    except Exception as e:
        logger.error(f"{rid} Unexpected error: {e}", exc_info=True)
        return Response(content=f"Internal error: {str(e)}", status_code=500)

def _adapt_llm_req_params(rid:str, body: bytes) -> Optional[dict]:
    try:
        body_data = json.loads(body.decode("utf-8"))
        is_stream_request = body_data.get("stream", False)
        logger.info(f"{rid} Stream request: {is_stream_request}")

        # round thinking to the values that littlellm is able to translate to openai format
        if "thinking" in body_data:
            anthropic_thinking = AnthropicThinkingParam(body_data["thinking"])
            anthropic_thinking["budget_tokens"] = round_thinking(
                anthropic_thinking.get("budget_tokens", 0)
            )
            body_data["thinking"] = anthropic_thinking
        # pop temperature (not supported)
        if "temperature" in body_data:
            del body_data["temperature"]
            
        return body_data
    except json.JSONDecodeError:
        return None

def _streaming_response(request_id: str, url: str, method: str, headers: dict, request_body: httpx._types.RequestContent) -> StreamingResponse:
    logger.info(f"{request_id} Handling as streaming response")
    
    async def stream_generator():
        """
        Generator that yields chunks from the upstream response.
        IMPORTANT: Create the httpx client INSIDE the generator
        so it stays alive while streaming.
        """
        # Create client inside the generator
        async with httpx.AsyncClient(timeout=300.0) as client:
            try:
                async with client.stream(
                        method=method,
                        url=url,
                        headers=headers,
                        content=request_body,
                ) as resp:
                    logger.info(f"{request_id} Stream status: {resp.status_code}")
                    
                    # Stream chunks as they arrive
                    async for chunk in resp.aiter_raw():
                        if chunk:
                            logger.debug(f"{request_id} Chunk: {len(chunk)} bytes")
                            yield chunk
                
                logger.info(f"{request_id} Stream completed successfully")
            
            except Exception as e:
                logger.error(f"{request_id} Stream error: {e}", exc_info=True)
                # Send error as SSE
                error_msg = f"data: {json.dumps({'error': str(e)})}\n\n"
                yield error_msg.encode()
    
    # Return StreamingResponse
    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


async def _standard_response(rid: str, url: str, method: str,  headers: dict, request_body: httpx._types.RequestContent) -> StreamingResponse:
    logger.info(f"{rid} Handling as non-streaming response")
    
    async with httpx.AsyncClient(timeout=300.0) as client:
        try:
            response = await client.request(
                method=method,
                url=url,
                headers=headers,
                content=request_body,
            )
            
            logger.info(f"{rid} Stream completed successfully")
        
        except Exception as e:
            logger.error(f"{rid} Stream error: {e}", exc_info=True)
            raise
        
        return Response(
            content=response.content,
            status_code=response.status_code,
            headers=dict(response.headers),
        )

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "proxy_target": LITELLM_URL}


if __name__ == "__main__":
    import uvicorn

    logger.info("Starting LiteLLM proxy on port 8764")
    logger.info(f"Forwarding to: {LITELLM_URL}")

    uvicorn.run(app, host="127.0.0.1", port=8764, log_level="info")
