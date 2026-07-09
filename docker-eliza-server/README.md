# Eliza App — Server

This stack runs the processing pipeline: RabbitMQ message bus, Voice Activity Detection (VAD),
Automatic Speech Recognition (ASR), the ELIZA conversational module, and persistent EMISSOR
storage. It exposes two ports for the client to connect to:

| Port | Purpose |
|---|---|
| 5672 | RabbitMQ AMQP |
| 8001 | Storage REST API |

Start this stack **before** the client stack. See `../docker-client/` for the client setup.

**All services in this stack are pulled directly from the CLTL container registry
(`ghcr.io/leolani`).** No local build or Python environment is required — Docker is the only
prerequisite.

## Prerequisites

| Tool | Minimum version |
|---|---|
| Docker | 23.0 |
| Docker Compose | 2.10 |

## Architecture

Each CLTL component runs as its own container. Containers communicate exclusively through
RabbitMQ using the Kombu event bus — there is no direct HTTP traffic between pipeline stages.

```
Containers (eliza-network)
┌─────────────────────────────────────────────────────────────────────┐
│  rabbitmq          (:5672, :15672) — AMQP message broker            │
│  eliza-backend     (:8001)         — storage REST API               │
│  eliza-vad                         — voice activity detection        │
│  eliza-asr                         — automatic speech recognition    │
│  eliza-eliza                       — ELIZA conversational logic      │
│  eliza-emissor     (:8002)         — EMISSOR data API               │
└─────────────────────────────────────────────────────────────────────┘
                  ▲ RabbitMQ :5672 · Storage API :8001
                  │
          docker-client (separate host or same machine)
```

### Event flow

```
client → RabbitMQ (cltl.topic.microphone)
       → VAD     (cltl.topic.vad)
       → ASR     (cltl.topic.text_in)
       → ELIZA   (cltl.topic.text_out)
       → client chat UI
       → EMISSOR stores all signals and annotations
```

Each container subscribes to its upstream topic and publishes to its downstream topic. Adding
or replacing a processing stage is a matter of swapping one image and updating its config.

## Quick Start

```bash
docker compose up -d --wait
```

Docker pulls all images on first run. The `--wait` flag blocks until all services are healthy.
On first start the ASR module downloads the Whisper `base` model (~150 MB), which can take a
few minutes depending on your connection. The model is cached in `./storage/` and is not
re-downloaded on subsequent starts.

## Configuration

Edit `config/custom.config` to override any setting from `config/default.config`.
Only add the sections and keys you want to change.

### Common overrides

**Change the Whisper model size** (larger = more accurate, slower):

```ini
[cltl.asr.whisper]
model: small
language: en
```

Available sizes: `tiny`, `base`, `small`, `medium`, `large`.

**Switch ASR to Google Cloud Speech** (requires a service-account key placed at
`config/google_cloud_key.json`):

```ini
[cltl.asr]
implementation: google

[cltl.asr.google]
language: en-US
```

**Tune Voice Activity Detection sensitivity** (lower threshold = more sensitive):

```ini
[cltl.vad.webrtc]
activity_threshold: 0.6
```

### Updating images

Images are pinned to the tag set by the `VERSION` variable (default: `latest`). To pull a specific
release:

```bash
VERSION=1.2.3 docker compose pull
VERSION=1.2.3 docker compose up -d --wait
```

Or set `VERSION` in a `.env` file in this directory.

## Endpoints

| Service | URL |
|---|---|
| Storage REST API | http://localhost:8001 |
| EMISSOR data API | http://localhost:8002/emissor |
| RabbitMQ management UI | http://localhost:15672 (user: `eliza`, password: `eliza123`) |

### Storage API

The storage API (port 8001) accepts audio and image uploads from remote clients and is the
primary integration point for the client stack:

| Method | Path | Description |
|---|---|---|
| `POST` | `/storage/audio` | Upload an audio segment |
| `GET` | `/storage/audio/{id}` | Retrieve a stored audio segment |
| `GET` | `/health` | Health check |

### EMISSOR data API

The EMISSOR API (port 8002) provides access to structured conversation records:

| Method | Path | Description |
|---|---|---|
| `GET` | `/emissor/scenarios` | List all scenarios |
| `GET` | `/emissor/scenarios/{id}` | Get scenario metadata |
| `GET` | `/emissor/scenarios/{id}/signals/{modality}` | Get signals for a modality |

## EMISSOR Data

Interaction data is persisted in `./storage/emissor/`. Each conversation session is stored as
a scenario folder:

```
storage/emissor/
└── <scenario-id>/
    ├── <scenario-id>.json   # metadata (participants, timestamps, location)
    ├── audio.json           # audio signal metadata and VAD annotations
    ├── text.json            # text signal metadata (transcriptions, responses)
    ├── audio/               # raw audio files (.wav)
    └── text/                # text files (.csv)
```

For details on the EMISSOR data model, see the
[EMISSOR documentation](https://github.com/leolani/emissor).

## Stopping and cleaning up

```bash
docker compose down
```

Persistent data is written to `./storage/`. It is not removed by `docker compose down`.
To start with a clean slate:

```bash
rm -rf storage/audio storage/image storage/emissor storage/event_log storage/rabbitmq
```

## Troubleshooting

**Problem:** ASR container exits immediately on first start

The ASR container downloads the Whisper model on first boot. If the download is interrupted the
model file may be corrupt. Remove the cached model and restart:

```bash
docker compose down
rm -rf storage/   # or remove only the model cache if you know its path
docker compose up -d --wait
```

**Problem:** Client cannot reach RabbitMQ (connection refused on port 5672)

- Confirm the server is up: `docker compose ps` — all containers should be `healthy` or `running`.
- Check that no host firewall blocks inbound TCP 5672.
- If the client is on a different machine, ensure `config/custom.config` on the client side
  points to this machine's IP, not `host.docker.internal`.

**Problem:** No response from ELIZA (client sends text, nothing comes back)

- Open the RabbitMQ management UI (port 15672) and check whether messages appear on the
  `cltl.combot` exchange under topics `cltl.topic.text_in` and `cltl.topic.text_out`.
- Check container logs: `docker compose logs eliza-eliza`.

**Problem:** VAD never fires (audio arrives but no transcriptions)

- Lower `activity_threshold` in `config/custom.config` (try `0.5` or lower).
- Check `docker compose logs eliza-vad` for errors.

## Related

- [docker-client](../docker-client/) — the matching client stack
- [CLTL Combot Framework](https://github.com/leolani/cltl-combot)
- [EMISSOR Framework](https://github.com/leolani/emissor)
- [Leolani Platform](https://github.com/leolani)

## Authors

- [Taewoon Kim](https://tae898.github.io/)
- [Thomas Baier](https://www.linkedin.com/in/thomas-baier-05519030/)
- [Selene Báez Santamaría](https://selbaez.github.io/)
- [Piek Vossen](https://github.com/piekvossen)
