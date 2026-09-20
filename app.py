import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("discovery")

UDP_PORT = 4210
BROADCAST_ADDR = "255.255.255.255"
DEVICE_TIMEOUT_SECONDS = 30
CLEANUP_INTERVAL_SECONDS = 10

# mac -> latest known info about the device
devices: dict[str, dict] = {}


class DeviceInfo(BaseModel):
    mac: str
    ip: str
    hostname: str
    name: Optional[str] = None
    last_seen: float


class DiscoveryProtocol(asyncio.DatagramProtocol):
    """Receives heartbeat/reply packets from the ESP32 devices and can send DISCOVER."""

    transport: asyncio.DatagramTransport

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:
        self.transport = transport

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        try:
            payload = json.loads(data.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            logger.warning("Invalid packet from %s: %r", addr, data)
            return

        mac = payload.get("mac")
        if not mac:
            # This is likely our own DISCOVER packet echoing back, or noise
            return

        payload["ip"] = addr[0]
        payload["last_seen"] = time.time()
        is_new = mac not in devices
        devices[mac] = payload

        if is_new:
            logger.info(
                "New device discovered: %s (%s) @ %s",
                payload.get("hostname", "?"),
                mac,
                addr[0],
            )

    def send_discover_broadcast(self) -> None:
        message = json.dumps({"type": "DISCOVER"}).encode("utf-8")
        self.transport.sendto(message, (BROADCAST_ADDR, UDP_PORT))
        logger.info("Sent DISCOVER broadcast")


protocol_instance: Optional[DiscoveryProtocol] = None


async def cleanup_stale_devices() -> None:
    """Removes devices not heard from for DEVICE_TIMEOUT_SECONDS seconds."""
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
        now = time.time()
        stale = [mac for mac, d in devices.items() if now - d["last_seen"] > DEVICE_TIMEOUT_SECONDS]
        for mac in stale:
            logger.info("Device %s (%s) dropped (timeout)", devices[mac].get("hostname", "?"), mac)
            del devices[mac]


@asynccontextmanager
async def lifespan(app: FastAPI):
    global protocol_instance
    loop = asyncio.get_event_loop()

    transport, protocol = await loop.create_datagram_endpoint(
        DiscoveryProtocol,
        local_addr=("0.0.0.0", UDP_PORT),
        allow_broadcast=True,
        reuse_port=True,
    )
    protocol_instance = protocol
    cleanup_task = asyncio.create_task(cleanup_stale_devices())

    logger.info("UDP listener started on port %d", UDP_PORT)
    yield

    cleanup_task.cancel()
    transport.close()


app = FastAPI(title="Bevattningssystem - Discovery", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # restrict to the React app's origin in production
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)


@app.get("/devices", response_model=list[DeviceInfo])
async def list_devices():
    """Returns all devices heard from within the last DEVICE_TIMEOUT_SECONDS seconds."""
    now = time.time()
    return [d for d in devices.values() if now - d["last_seen"] <= DEVICE_TIMEOUT_SECONDS]


@app.post("/devices/scan")
async def trigger_scan():
    """Asks all devices to reply immediately instead of waiting for the next heartbeat."""
    if protocol_instance is None:
        return {"status": "error", "detail": "UDP listener not ready yet"}
    protocol_instance.send_discover_broadcast()
    return {"status": "ok", "detail": "DISCOVER broadcast sent"}


@app.delete("/devices/{mac}")
async def forget_device(mac: str):
    """Manually removes a device from the list, e.g. if it has been permanently disconnected."""
    devices.pop(mac, None)
    return {"status": "ok"}