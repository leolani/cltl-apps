# The deployment

The agent this template attaches *to*. None of it is this template, and none of
it needs the platform's source code — it is three published images, RabbitMQ,
and one configuration file.

```bash
docker compose -f deployment/deployment.compose.yml up
```

| | |
|---|---|
| Chat UI | <http://127.0.0.1:8000/chatui/static/chat.html> |
| Broker (AMQP) | `amqp://leolani:leolani@127.0.0.1:5672/` |
| RabbitMQ management | <http://127.0.0.1:15672> — `leolani` / `leolani` |

Those ports are **fixed**, deliberately. The platform's test harness randomises
its ports so concurrent runs cannot collide; a deployment meant to be driven by
a person following a document needs an address that can be written down. The
cost is that two copies of this stack collide — override `CLTL_CHATUI_PORT`,
`CLTL_AMQP_PORT` and `CLTL_MANAGEMENT_PORT` if you need a second.

## What is in it

Four services, the smallest set that makes a conversation happen:

| Service | Does |
|---|---|
| `rabbitmq` | The message bus every other service talks through |
| `cltl-chat-ui` | The web chat page, and the bridge between it and the bus |
| `cltl-eliza` | The dialogue logic — an ELIZA-style therapist |
| `cltl-context` | Opens the conversation and runs the consent handshake |

**No audio** — no microphone backend, no voice activity detection, no speech
recognition. Those need a sound device, a storage volume and a large model
download on first use, and none of it changes what attaching to the event bus
looks like. A module this deployment does not run has no section in its
configuration at all, rather than a disabled one.

The full platform deployment — every module, audio included — lives in the
`cltl-dev` repository. This file is a deliberate reduction of it, not a
replacement, and does not track it.

## Say "yes" first

The chat UI opens with *"Do you want to talk to me?"*.

Until you answer "yes", **`cltl-eliza` is silent.** The agent runs a
belief-desire-intention loop: `cltl-context` starts it in an `init` intention
and only promotes it to the `eliza` intention once consent is given. `cltl-eliza`
processes events only while that intention is active.

This template deliberately has no such gating (the reason is in
[`tenancy.md`](tenancy.md#why-there-is-no-intention-gating)), so it answers from
the very first message. **A first message that draws exactly one reply — this
module's — is the handshake working.** After "yes", every message draws two.

## The configuration

`deployment/config/default.config` is mounted read-only over each image's own
`config/` directory. That is not a nicety. Every platform image ships a
`config/` using **legacy** topic names intended for standalone single-process
runs; a deployment that lets those defaults stand comes up entirely healthy and
wired to nothing. The mounted file supplies the canonical `cltl.topic.*` names
that actually connect the modules to each other.

Two settings there are worth knowing:

- **`[cltl.context] start_scenario: true`** — the chat UI renders nothing until
  a conversation is open. The platform's test harness leaves this `false` and
  opens one from the test process; nothing here does that, so the context
  service opens one itself at startup. Set it `false` and you get a permanently
  blank chat UI.
- **`[cltl.event.kombu] tenant: $CLTL_TENANT`** — empty, i.e. single-tenant.
  Note that the compose file declares `CLTL_TENANT` even though it is empty:
  an *undefined* variable is passed through as the literal string
  `"$CLTL_TENANT"` with only a warning, and the bus would then bind a queue
  nothing ever routes to. See [`tenancy.md`](tenancy.md).

## Pinning a version

`CLTL_IMAGE_TAG` selects the image tag, defaulting to `latest`:

```bash
CLTL_IMAGE_TAG=<a published tag> docker compose -f deployment/deployment.compose.yml up
```

Worth doing for anything you intend to reproduce. `latest` moves.

## Shutting down

```bash
docker compose -f deployment/deployment.compose.yml down
```

Stop any attached listener *first*. A listener whose broker vanishes retries
forever and needs `kill -9` — see [`gotchas.md`](gotchas.md).

The conversation is not persisted: this deployment runs no storage service and
mounts no volume, so `down` takes the transcript with it.
