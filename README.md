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
docker run --network host dripdrop-discovery
```

> **Use `--network host`.** The service relies on UDP broadcast
> (`255.255.255.255:4210`), which Docker's default bridge network does not
> forward. Host networking is Linux-only — on Docker Desktop (macOS/Windows)
> broadcast discovery will not work from inside a container.

The REST API is then available at `http://localhost:8000` (see `/docs` for the
interactive Swagger UI).
