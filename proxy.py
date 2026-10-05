import logging
from typing import Optional

import httpx
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from config import PROXY_TIMEOUT_SECONDS
from nodes import load_nodes

logger = logging.getLogger("discovery")

router = APIRouter()

PROXY_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]

# Headers that must not be forwarded by a proxy (RFC 7230 §6.1), plus ones
# httpx/Starlette recompute themselves.
HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
}

# httpx has already decompressed upstream.content, so the encoding header must
# not be passed on to the client. Request bodies are forwarded as-is and keep it.
RESPONSE_EXCLUDED_HEADERS = HOP_BY_HOP_HEADERS | {"content-encoding"}

http_client: Optional[httpx.AsyncClient] = None


def start_client() -> None:
    global http_client
    http_client = httpx.AsyncClient(timeout=PROXY_TIMEOUT_SECONDS)


async def close_client() -> None:
    if http_client is not None:
        await http_client.aclose()


@router.api_route("/proxy/{name}/{path:path}", methods=PROXY_METHODS)
async def proxy(name: str, path: str, request: Request):
    """Forwards the request to a registered node.

    GET /proxy/garden/api/status  ->  GET http://<node ip>:<port>/api/status
    """
    nodes = load_nodes()
    node = nodes.get(name)
    if node is None:
        return JSONResponse(
            status_code=404,
            content={"error": f'Unknown node: "{name}"', "available": list(nodes)},
        )

    target = f"http://{node['ip']}:{node['port']}"
    url = f"{target}/{path}"
    headers = {k: v for k, v in request.headers.items() if k.lower() not in HOP_BY_HOP_HEADERS}

    logger.info("[PROXY] %s %s -> %s", request.method, name, url)
    try:
        upstream = await http_client.request(
            request.method,
            url,
            params=request.query_params,
            headers=headers,
            content=await request.body(),
        )
    except httpx.TimeoutException as exc:
        logger.error("Proxy timeout for %s: %s", name, exc)
        return JSONResponse(
            status_code=504,
            content={"error": "Node timed out", "node": name, "target": target, "detail": str(exc)},
        )
    except httpx.RequestError as exc:
        logger.error("Proxy error for %s: %s", name, exc)
        return JSONResponse(
            status_code=502,
            content={"error": "Could not reach node", "node": name, "target": target, "detail": str(exc)},
        )

    response = Response(content=upstream.content, status_code=upstream.status_code)
    # multi_items() keeps repeated headers (e.g. several Set-Cookie) separate
    for k, v in upstream.headers.multi_items():
        if k.lower() not in RESPONSE_EXCLUDED_HEADERS:
            response.headers.append(k, v)
    return response


@router.api_route("/proxy/{name}", methods=PROXY_METHODS)
async def proxy_root(name: str, request: Request):
    """Forwards /proxy/{name} (no trailing slash) to the node's root."""
    return await proxy(name, "", request)
