# DripDrop Discovery

Device-discovery service for the irrigation system (bevattningssystemet).

It listens for UDP broadcast heartbeats from the ESP32 devices on the local
network and exposes a small REST API so the app can query the list of live
devices directly — instead of every ESP32 needing a fixed IP (or vice versa).

## How it works

- Each ESP32 broadcasts a heartbeat on **UDP port 4210**.
- The service tracks the latest info per device (keyed by MAC address) and
  drops any device not heard from within `DEVICE_TIMEOUT_SECONDS` (30s).
- The app queries the **REST API on port 8000** to get the current device list.

## API

| Method   | Path               | Description                                                     |
| -------- | ------------------ | --------------------------------------------------------------- |
| `GET`    | `/devices`         | List devices seen in the last 30 seconds.                       |
| `POST`   | `/devices/scan`    | Broadcast a `DISCOVER` so devices reply now instead of waiting. |
| `DELETE` | `/devices/{mac}`   | Forget a device manually (e.g. permanently disconnected).       |

### Proxy

Separate from discovery, the service can act as a reverse proxy to nodes you
register manually, so the app only needs to reach this service (e.g. over
Tailscale) — not the nodes' local IPs. Registered nodes are stored in
`data/nodes.json` (override with the `NODES_FILE` env var) and stay until
they're deleted.

| Method   | Path                   | Description                                                   |
| -------- | ---------------------- | ------------------------------------------------------------- |
| `GET`    | `/nodes`               | List registered nodes.                                        |
| `POST`   | `/nodes`               | Register a node. `409 Conflict` if the name or IP is taken.   |
| `PUT`    | `/nodes/{name}`        | Replace a node's `ip`, `port`, `description`. `404` if unknown, `409` if the IP belongs to another node. |
| `DELETE` | `/nodes/{name}`        | Remove a node (`404` if unknown).                             |
| `*`      | `/proxy/{name}/{path}` | Forward a request (method, query, headers, body) to the node. |

```bash
# Register a node (port defaults to 80)
curl -X POST http://localhost:8000/nodes \
     -H 'Content-Type: application/json' \
     -d '{"name":"garden","ip":"192.168.1.101","port":80,"description":"Garden"}'

# Change its IP (the name comes from the URL; omitted fields reset to defaults)
curl -X PUT http://localhost:8000/nodes/garden \
     -H 'Content-Type: application/json' \
     -d '{"ip":"192.168.1.120","description":"Garden"}'

# Call it through the proxy: → GET http://192.168.1.101:80/api/status
curl http://localhost:8000/proxy/garden/api/status
```

Node names must be slugs: lowercase `a-z`, digits and single hyphens, not
starting or ending with a hyphen (e.g. `garden`, `greenhouse-2`). Anything
else is rejected with `422`. Proxy responses: `404` for an
unknown node (with a list of available ones), `502` if it can't be reached,
`504` on timeout (10s).

## Running locally

Requires Python 3.10+.

Create and activate a virtual environment, then install the dependencies:

```bash
# Create the virtual environment (once)
python3 -m venv .venv

# Activate it
source .venv/bin/activate        # macOS/Linux
# .venv\Scripts\activate         # Windows (PowerShell/cmd)

# Install dependencies into the venv
pip install -r requirements.txt
```

Run the service (with the venv activated):

```bash
uvicorn app:app --host 0.0.0.0 --port 8000
```

When you're done, run `deactivate` to leave the virtual environment.

## Running with Docker

```bash
docker build -t dripdrop-discovery .
docker run --network host -v dripdrop-data:/app/data dripdrop-discovery
```

The volume keeps the registered proxy nodes across container restarts.

> **Use `--network host`.** The service relies on UDP broadcast
> (`255.255.255.255:4210`), which Docker's default bridge network does not
> forward. Host networking is Linux-only — on Docker Desktop (macOS/Windows)
> broadcast discovery will not work from inside a container.

The REST API is then available at `http://localhost:8000` (see `/docs` for the
interactive Swagger UI).
