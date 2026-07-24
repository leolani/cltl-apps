# Eliza App — Client

This stack runs the user-facing components: the backend service that captures audio from the host
machine and uploads it to the server, the context service, and the web chat UI.

The client connects to the server stack (`../docker-eliza-server/`) through two ports on the server
host: RabbitMQ on 5672 and the storage API on 8001. **Start the server stack first.**

Unlike the other apps in this repository that mix a locally built container with registry images,
**every service in this stack is pulled directly from the CLTL container registry
(`ghcr.io/leolani`).** No local build step is required. The one exception is `eliza-app`, which
is still built locally from the `src/` and `app.py` files in this directory — it is the natural
place to customise the client application (see [Customisation](#customisation)).

## Prerequisites

| Requirement | Minimum version | Notes |
|---|---|---|
| Docker | 23.0 | |
| Docker Compose | 2.10 | |
| Python | 3.8+ | For the host backend server (audio capture) |
| PortAudio | — | `portaudio19-dev` on Debian/Ubuntu; `portaudio` via Homebrew on macOS |

## Architecture

The client stack is composed of four containers that together provide the user-facing side of the
pipeline:

```
Host machine
┌─────────────────────────────────────────────────────────────────────┐
│  Host backend server (Python, not in Docker)                        │
│  Captures microphone audio and exposes it over HTTP on port 8000    │
└──────────────────────────┬──────────────────────────────────────────┘
                           │ http://host.docker.internal:8000
                           ▼
Docker client network (eliza-client-network)
┌─────────────────────────────────────────────────────────────────────┐
│  eliza-backend   (:9001)  — fetches audio from host, proxies        │
│                             storage to the server                    │
│  eliza-context            — manages conversation scenarios          │
│  eliza-chatui    (:8003)  — web chat UI served to the browser       │
│  eliza-app                — wires components together, owns         │
│                             BDI / keyword / event-log logic         │
└────────────────────────────────┬────────────────────────────────────┘
                                 │ RabbitMQ :5672 · Storage API :8001
                                 ▼
                    docker-eliza-server (separate host or same machine)
```

All four client containers share the same `./config/` and `./storage/` mounts, so configuration
and persisted data are managed in one place.

## Quick Start

### 1. Start the server stack first

```bash
cd ../docker-eliza-server
docker compose up -d --wait
```

### 2. Start the host backend server

The client stack needs a small Python service running **directly on your machine** (not in Docker)
to access the microphone. A helper script is provided that creates a virtual environment and
installs the backend automatically:

```bash
./run_host_server.sh
```

Leave this terminal open while the client is running. To start it manually instead:

```bash
python -m venv venv-backend
source venv-backend/bin/activate          # Windows: venv-backend\Scripts\activate
pip install 'cltl-backend[host]'
leoserv --rate 16000 --channels 1 --frame_duration 30 --port 8000
```

### 3. Start the client stack

```bash
docker compose up -d --wait
```

All images are pulled from `ghcr.io/leolani` on first run. The `--wait` flag blocks until
all services pass their health checks.

### 4. Open the chat UI

```
http://localhost:8003/chatui/static/chat.html
```

## Configuration

Edit `config/custom.config` to override any setting from `config/default.config`.
Only add the sections and keys you want to change — everything else falls through to the defaults.

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

### Disabling the microphone (text-only mode)

To run without audio capture, set the microphone topic to empty in `config/custom.config`:

```ini
[cltl.backend.mic]
topic:
```

In this mode the chat UI is the sole input channel and no host backend server is required.

### Updating images

Images are pinned to the tag set by the `VERSION` variable (default: `latest`). To pull a specific
release:

```bash
VERSION=1.2.3 docker compose pull
VERSION=1.2.3 docker compose up -d --wait
```

Or set `VERSION` in a `.env` file in this directory.

## Customisation

The `eliza-app` container is the only one built locally, making it the natural extension point.
The other containers (`eliza-backend`, `eliza-context`, `eliza-chatui`) are standard registry
images configured entirely through `config/custom.config`.

### Entry point: `app.py`

**TODO**

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

Changes to `config/custom.config` take effect on a plain `docker compose restart` — no rebuild
needed.

## Host backend server

The host backend server captures audio from your microphone and exposes it over HTTP so the
Docker containers can read audio signals without direct hardware access.

| Flag | Description |
|---|---|
| `--rate` | Sample rate in Hz — must match `[cltl.audio] sampling_rate` (default: 16000) |
| `--channels` | Number of audio channels (1 = mono) |
| `--frame_duration` | Audio frame duration in milliseconds |
| `--port` | HTTP port — must be 8000 to match the default client config |

The `run_host_server.sh` script encapsulates these flags and manages the virtual environment
automatically. Run it once and leave it open while using the client stack.

## Endpoints

| Service | URL |
|---|---|
| Chat UI | http://localhost:8003/chatui/static/chat.html |
| Client backend API | http://localhost:9001 |

## Data Flow

A typical voice-input conversation flows through the following stages:

```
1. User speaks
2. Host backend (port 8000) → captures audio, serves it over HTTP
3. eliza-backend → fetches audio from host, uploads to server storage (port 8001)
4. Server: VAD → detects speech segments
5. Server: ASR → transcribes audio to text
6. Server: ELIZA → generates response text
7. Chat UI (port 8003) → displays response
8. Server: EMISSOR → logs all events and signals
```

For text-only input the host backend is not involved — the chat UI publishes text directly to
RabbitMQ and the server pipeline picks it up from step 6.

## EMISSOR Data

Interaction data is stored on the **server** side in `../docker-eliza-server/storage/emissor/`.
The client's `./storage/` directory holds audio buffers and event logs local to the client
containers.

For details on the EMISSOR data format and its REST API, see the
[EMISSOR documentation](https://github.com/leolani/emissor).

## Stopping and cleaning up

```bash
docker compose down
```

Persistent data is written to `./storage/`. To remove it:

```bash
rm -rf storage/
```

## Troubleshooting

**Problem:** Chat UI shows no responses

- Verify the server stack is running: `docker compose -f ../docker-eliza-server/docker-compose.yml ps`
- Check RabbitMQ connectivity: open http://localhost:15672 on the server host
  (user `eliza`, password `eliza123`) and confirm messages flow on the `cltl.combot` exchange.
- Confirm `config/custom.config` points to the correct server IP / hostname.

**Problem:** No voice detection (microphone silent)

- Confirm the host backend server is running (`run_host_server.sh` or `leoserv`).
- Verify `[cltl.backend.mic] topic: cltl.topic.microphone` is set in `config/custom.config`.
- Check that port 8000 on the host is not blocked: `curl http://localhost:8000/health`.

**Problem:** `docker compose build` fails

- Ensure Docker is running and you have network access to pull the base image from
  `ghcr.io/leolani`.
- Check that `requirements.txt` lists valid package specifications.

**Problem:** Port conflict on 9001 or 8003

- Another process is using that port. Either stop it or change the host port in
  `docker-compose.yml` (e.g. `"9901:8000"` instead of `"9001:8000"`).

## Related

- [docker-eliza-server](../docker-eliza-server/) — the matching server stack
- [CLTL Combot Framework](https://github.com/leolani/cltl-combot)
- [EMISSOR Framework](https://github.com/leolani/emissor)
- [Leolani Platform](https://github.com/leolani)

## Authors

- [Taewoon Kim](https://tae898.github.io/)
- [Thomas Baier](https://www.linkedin.com/in/thomas-baier-05519030/)
- [Selene Báez Santamaría](https://selbaez.github.io/)
- [Piek Vossen](https://github.com/piekvossen)
