import json
import logging
from ipaddress import IPv4Address

from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from config import NODES_FILE, PROXY_DEFAULT_PORT

logger = logging.getLogger("discovery")

router = APIRouter()


class ProxyNodeConfig(BaseModel):
    ip: IPv4Address
    port: int = Field(default=PROXY_DEFAULT_PORT, ge=1, le=65535)
    description: str = ""


class ProxyNode(ProxyNodeConfig):
    name: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$", description="Used in the proxy URL: /proxy/{name}/...")


def load_nodes() -> dict[str, dict]:
    if not NODES_FILE.exists():
        return {}
    return json.loads(NODES_FILE.read_text(encoding="utf-8"))


def save_nodes(nodes: dict[str, dict]) -> None:
    NODES_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = NODES_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(nodes, indent=2), encoding="utf-8")
    tmp.replace(NODES_FILE)


def conflict_response(field: str, existing: dict) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={
            "error": f"A node with this {field} is already registered",
            "field": field,
            "existing": existing,
        },
    )


@router.get("/nodes", response_model=list[ProxyNode])
async def list_nodes():
    """Lists all registered proxy nodes."""
    return list(load_nodes().values())


@router.post("/nodes", response_model=ProxyNode, status_code=201)
async def register_node(node: ProxyNode):
    """Registers a proxy node. Returns 409 if the name or IP is already registered."""
    nodes = load_nodes()
    ip = str(node.ip)
    conflict = next(
        (n for n in nodes.values() if n["name"] == node.name or n["ip"] == ip),
        None,
    )
    if conflict is not None:
        field = "name" if conflict["name"] == node.name else "ip"
        return conflict_response(field, conflict)

    nodes[node.name] = node.model_dump(mode="json")
    save_nodes(nodes)
    logger.info("Registered proxy node %s -> %s:%d", node.name, ip, node.port)
    return node


@router.put("/nodes/{name}", response_model=ProxyNode)
async def update_node(name: str, config: ProxyNodeConfig):
    """Replaces a registered node's ip, port and description.

    Returns 404 if the node doesn't exist, 409 if the IP belongs to another node.
    """
    nodes = load_nodes()
    if name not in nodes:
        return JSONResponse(status_code=404, content={"error": f'Unknown node: "{name}"'})

    ip = str(config.ip)
    conflict = next((n for n in nodes.values() if n["name"] != name and n["ip"] == ip), None)
    if conflict is not None:
        return conflict_response("ip", conflict)

    node = ProxyNode(name=name, **config.model_dump())
    nodes[name] = node.model_dump(mode="json")
    save_nodes(nodes)
    logger.info("Updated proxy node %s -> %s:%d", name, ip, node.port)
    return node


@router.delete("/nodes/{name}", status_code=204)
async def delete_node(name: str):
    """Removes a registered proxy node."""
    nodes = load_nodes()
    if name not in nodes:
        return JSONResponse(status_code=404, content={"error": f'Unknown node: "{name}"'})
    del nodes[name]
    save_nodes(nodes)
    logger.info("Removed proxy node %s", name)
    return Response(status_code=204)
