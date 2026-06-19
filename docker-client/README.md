# Eliza App — Client

This stack runs the user-facing components: the backend service that captures audio from the host
machine and uploads it to the server, the context service, and the web chat UI.

The client connects to the server stack (`../docker-server/`) through two ports on the server
host: RabbitMQ on 5672 and the storage API on 8001. **Start the server stack first.**

The `eliza-app` orchestration container is **built locally** from the `src/` and `app.py` files
in this directory — it is not pulled from a registry. This makes it the natural place to
customise the client application (see [Customisation](#customisation)).

## Prerequisites

| Requirement | Minimum version | Notes |
|---|---|---|
| Docker | 23.0 | |
| Docker Compose | 2.10 | |
| Python | 3.8+ | For the host backend server (audio capture) |
| PortAudio | — | `portaudio19-dev` on Debian/Ubuntu; `portaudio` via Homebrew on macOS |

## Quick Start

### 1. Build the client image

```bash
docker compose build
```

This builds the `eliza-app` container from the local `Dockerfile`. All other images are pulled
from the registry. Re-run this command whenever you change `app.py` or anything under `src/`.

### 2. Start the host backend server

The client stack needs a small Python service running **directly on your machine** (not in Docker)
to access the microphone. Install it once:

```bash
python -m venv venv-backend
source venv-backend/bin/activate          # Windows: venv-backend\Scripts\activate
pip install cltl-backend
```

Then start it (leave this terminal open):

```bash
python -m cltl.backend.server \
  --rate 16000 \
  --channels 1 \
  --frame_duration 30 \
  --port 8000
```

### 3. Start the client stack

```bash
docker compose up -d --wait
```

### 4. Open the chat UI

```
http://localhost:8003/chatui/static/chat.html
```

## Configuration

Edit `config/custom.config` to override any setting from `config/default.config`.

### Connecting to the server

By default the client connects to a server running on the **same machine** via
`host.docker.internal`. No changes are needed for same-machine setups.

For a server on a **different machine**, replace `host.docker.internal` in `config/custom.config`
with the server's IP address or hostname:

```ini
[cltl.event.kombu]
server: amqp://eliza:eliza123@<SERVER_IP>:5672/

[cltl.backend.remote_storage]
storage_url: http://<SERVER_IP>:8001/storage
```

Ensure TCP ports 5672 and 8001 are reachable from the client machine (check the server's firewall).

## Customisation

The `eliza-app` container is built from the files in this directory, so you can modify them
freely without touching any shared repository code.

### Entry point: `app.py`

`app.py` wires the application together. `ApplicationContainer` inherits from `InfraContainer`
and adds `ContextService` and the event-log writer. To add further services (e.g. a custom
response processor), extend `ApplicationContainer` here:

```python
@property
@singleton
def my_service(self):
    return MyService(self.event_bus, self.config_manager)

def start(self):
    super().start()
    self.my_service.start()

def stop(self):
    self.my_service.stop()
    super().stop()
```

### Context service: `src/eliza_app_service/context/service.py`

`ContextService` creates the conversation scenario when the `init` intention fires. Common
things to customise:

- **Agent and speaker identity** — change the `AGENT` and `SPEAKER` module-level constants at the
  top of the file.
- **Location** — `_get_location()` currently calls `https://ipinfo.io`. Replace with a fixed
  location or a different source.
- **Scenario signals** — `_create_scenario()` registers image, text, and audio signal files.
  Add or remove modalities here.

### Template classes: `src/eliza_app/template/`

`api.py` defines the `DemoProcessor` abstract class. `dummy_demo.py` provides a
`HelloWorldProcessor` stub. These are the starting point for adding custom response logic beyond
the built-in ELIZA module.

### Adding dependencies

If your custom code requires additional Python packages, add them to `requirements.txt`. They
will be installed into the container image on the next build.

### Rebuild after changes

Any change to `app.py`, `src/`, or `requirements.txt` requires a rebuild before it takes effect:

```bash
docker compose build eliza-app
docker compose up -d --wait
```

## Host backend server

The host backend server captures audio from your microphone and exposes it over HTTP so the
Docker containers can read audio signals without direct hardware access.

| Flag | Description |
|---|---|
| `--rate` | Sample rate in Hz — must match `[cltl.audio] sampling_rate` (default: 16000) |
| `--channels` | Number of audio channels (1 = mono) |
| `--frame_duration` | Audio frame duration in milliseconds |
| `--port` | HTTP port — must be 8000 to match the default client config |

## Endpoints

| Service | URL |
|---|---|
| Chat UI | http://localhost:8003/chatui/static/chat.html |
| Client backend API | http://localhost:9001 |

## Stopping and cleaning up

```bash
docker compose down
```

Persistent data is written to `./storage/`. To remove it:

```bash
rm -rf storage/
```
