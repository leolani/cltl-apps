# Eliza App — Server

This stack runs the processing pipeline: RabbitMQ message bus, Voice Activity Detection (VAD),
Automatic Speech Recognition (ASR), the ELIZA conversational module, and persistent EMISSOR
storage. It exposes two ports for the client to connect to:

| Port | Purpose |
|---|---|
| 5672 | RabbitMQ AMQP |
| 8001 | Storage REST API |

Start this stack **before** the client stack. See `../docker-client/` for the client setup.

## Prerequisites

| Tool | Minimum version |
|---|---|
| Docker | 23.0 |
| Docker Compose | 2.10 |

## Quick Start

```bash
docker compose up -d --wait
```

Docker pulls all images on first run. The `--wait` flag blocks until all services are healthy.
On first start the ASR module downloads the Whisper `base` model, which can take a few minutes.

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

## Endpoints

| Service | URL |
|---|---|
| Storage REST API | http://localhost:8001 |
| EMISSOR data API | http://localhost:8002/emissor |
| RabbitMQ management UI | http://localhost:15672 (user: `eliza`, password: `eliza123`) |

## Stopping and cleaning up

```bash
docker compose down
```

Persistent data is written to `./storage/`. It is not removed by `docker compose down`.
To start with a clean slate:

```bash
rm -rf storage/audio storage/image storage/emissor storage/event_log storage/rabbitmq
```
