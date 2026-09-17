# Getting started

Rung 1 end to end: a running Leolani agent, and your code answering it from a
notebook. Fifteen minutes, most of it waiting for Docker to pull images.

You need **Docker** and **Python 3.10**. You do not need the platform's source.

If you have not read the picture at the top of the [README](../README.md), read
that first — this page assumes you know what a topic is.

## 1. Start a deployment

The deployment is multi-tenant, so it comes in two halves: one shared server,
and one stack per tenant. Start the server first.

```bash
docker compose -f deployment/server.compose.yml up -d

CLTL_TENANT=tenant-a CLTL_CHATUI_PORT=8000 \
    docker compose -f deployment/tenant.compose.yml up -d
```

The first run pulls two images from `ghcr.io/leolani` (ELIZA and the chat UI)
plus RabbitMQ, which is a few hundred MB. They are public; no `docker login`.

| | |
|---|---|
| tenant-a chat UI | <http://127.0.0.1:8000/chatui/static/chat.html> |
| Broker (AMQP) | `amqp://leolani:leolani@127.0.0.1:5672/` |
| RabbitMQ management | <http://127.0.0.1:15672> — `leolani` / `leolani` |

**Open the chat UI now, and notice that it is blank.** Nothing is broken, and
there is nothing to wait for. A chat UI renders nothing until a conversation —
a *scenario* — has been opened for it, and this deployment contains nothing that
opens one. Your notebook will, in step 3, and the page comes alive at that
moment.

[`deployment.md`](deployment.md) explains both halves;
[`tenancy.md`](tenancy.md) explains why opening that scenario ends up being your
job and why it is the one part of this template that is not an example of
custom functionality.

## 2. Install a notebook environment

In a second terminal, from this repository:

```bash
python3.10 -m venv .venv && source .venv/bin/activate
pip install -r requirements.notebook.txt jupyterlab
```

This installs just two platform libraries — `cltl.combot` (the event bus) and
`emissor` (the data representation). It does **not** install this template:
rungs 1–2 attach from outside and need none of it.

## 3. Run the notebook

```bash
jupyter lab attach/example.ipynb
```

Run the cells top to bottom. The URLs in the first code cell already match the
deployment from step 1, so there is nothing to paste unless you changed a port.
`TENANT` is set to `tenant-a` and must match what you started the tenant stack
with.

What you should see, in order:

0. **A blank chat UI**, from step 1. Correct, not broken.
1. **A connection**, and a binding check that reports it confirmed your
   subscription against the management API in a fraction of a second. If it
   instead says it fell back to a flat sleep, something is wrong with the
   management URL — see [`gotchas.md`](gotchas.md).
2. **The chat UI coming alive**, the moment the `start_scenario` cell runs. Go
   and look at the browser tab; the agent's side of the conversation appears.
3. **A live event.** Type something in the chat UI; a `TextSignalEvent` arrives
   on `cltl.topic.text_in` and the notebook prints it, with
   `tenant='tenant-a'` on it. This is the moment the whole template exists to
   reach: that is a real agent's real traffic, and you are reading it from a
   notebook that the agent knows nothing about.
4. **Your reply, in the chat UI.** Publish a `TextSignalEvent` on
   `cltl.topic.text_out` and it appears in the conversation.
5. **The two wired together** — the notebook answering automatically, alongside
   ELIZA. Two replies per message from here on; see the README.
6. **The isolation, checked rather than asserted.** The notebook's last section
   attaches two more observers — one as `tenant-b`, one untenanted — and tallies
   what each receives while you type in tenant-a's chat UI. The untenanted one
   sees the whole conversation; tenant-b sees nothing, on the same broker, the
   same exchange, the same network and the same credentials.

   Two things about that check are worth noticing. It starts **no** second
   compose stack and opens no second chat UI — a tenanted subscriber binds
   `<topic>.tenant-b` whether or not anything is running for tenant-b, because a
   tenant is a word in a routing key rather than a thing that has to exist. And
   the untenanted observer is a **control**: "tenant-b saw nothing" would be
   equally true with the broker down or with you not typing, so the result that
   means something is the pair.

The last cell closes the scenario and then the bus. Run it. Closing the scenario
clears the chat UI's transcript, which is how you see it land; and a
`KombuEventBus` left open keeps a consumer thread retrying forever, so the
notebook kernel will not exit cleanly — [`gotchas.md`](gotchas.md) has the
details.

## What you just did

You joined one tenant of a shared deployment, opened its conversation,
subscribed to a topic, received a real event, and published one that a component
you did not write acted on. Everything from here is about doing that same thing
more durably:

- **Rung 2** — [`attach/listen.py`](../attach/listen.py) is this notebook as a
  script you can leave running. Same code, no kernel. See
  [`attaching.md`](attaching.md).
- **Rung 3** — a real module: packaged, unit-tested, and composable into a
  deployment rather than attached from outside. This one needs a `cltl-dev`
  checkout, because it *builds* the template instead of talking to a
  deployment. See [`component.md`](component.md).
- **Replace the logic** — `src/myorg/example/echo.py` is one function. Change
  what it returns and rerun; rungs 1 and 2 both use it.

## If something goes wrong

[`gotchas.md`](gotchas.md) is symptom-first and covers every failure seen while
writing this template. The three most likely right now:

- **The chat UI is blank.** Expected until the scenario cell runs. If it is
  still blank afterwards, the scenario went to the wrong routing key — check
  that `TENANT` matches the `CLTL_TENANT` you started the tenant stack with.
- **Nothing arrives in the notebook.** Almost always the subscribe/bind race —
  the deployment was fine, your queue just was not attached yet.
- **`TypeError: PAYLOAD is not a dataclass`.** The event types were not
  registered before something tried to deserialise. `attach/connect.py` does
  this for you; a new entry point of your own must too.
