# Getting started

Rung 1 end to end: a running Leolani agent, and your code answering it from a
notebook. Fifteen minutes, most of it waiting for Docker to pull images.

You need **Docker** and **Python 3.10**. You do not need the platform's source.

If you have not read the picture at the top of the [README](../README.md), read
that first — this page assumes you know what a topic is.

## 1. Start a deployment

```bash
docker compose -f deployment/deployment.compose.yml up
```

The first run pulls three images from `ghcr.io/leolani` (chat UI, ELIZA,
context) plus RabbitMQ, which is a few hundred MB. They are public; no
`docker login`.

Wait until the logs settle — you are looking for lines like
`ScenarioStarted` and the chat UI reporting it is serving. Then:

| | |
|---|---|
| Chat UI | <http://127.0.0.1:8000/chatui/static/chat.html> |
| Broker (AMQP) | `amqp://leolani:leolani@127.0.0.1:5672/` |
| RabbitMQ management | <http://127.0.0.1:15672> — `leolani` / `leolani` |

Open the chat UI. It greets you with *"Do you want to talk to me?"* — **answer
"yes"**. Nothing else works properly until you do, and
[`deployment.md`](deployment.md) explains why.

Leave this terminal running. `Ctrl-C` stops the deployment.

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

What you should see, in order:

1. **A connection**, and a binding check that reports it confirmed your
   subscription against the management API in a fraction of a second. If it
   instead says it fell back to a flat sleep, something is wrong with the
   management URL — see [`gotchas.md`](gotchas.md).
2. **A live event.** Type something in the chat UI; a `TextSignalEvent` arrives
   on `cltl.topic.text_in` and the notebook prints it. This is the moment the
   whole template exists to reach: that is a real agent's real traffic, and you
   are reading it from a notebook that the agent knows nothing about.
3. **Your reply, in the chat UI.** Publish a `TextSignalEvent` on
   `cltl.topic.text_out` and it appears in the conversation.
4. **The two wired together** — the notebook answering automatically, alongside
   ELIZA. Two replies per message from here on; see the README.

The last cell closes the bus. Run it. A `KombuEventBus` left open keeps a
consumer thread retrying forever, and the notebook kernel will not exit
cleanly — [`gotchas.md`](gotchas.md) has the details.

## What you just did

You subscribed to a topic, received a real event, and published one that a
component you did not write acted on. Everything from here is about doing that
same thing more durably:

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

- **Nothing arrives in the notebook.** Almost always the subscribe/bind race —
  the deployment was fine, your queue just was not attached yet.
- **Only one reply, and it is not ELIZA's.** You have not answered "yes".
- **`TypeError: PAYLOAD is not a dataclass`.** The event types were not
  registered before something tried to deserialise. `attach/connect.py` does
  this for you; a new entry point of your own must too.
