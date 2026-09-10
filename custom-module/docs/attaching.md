# Attaching to a live bus (rungs 1–2)

How the notebook and `attach/listen.py` join a running deployment without
installing anything, and the three things that go wrong the first time.

Read this before modifying `attach/connect.py`, which both rungs share.

## Why this is safe to do

The bus is a single RabbitMQ **topic exchange** named `cltl.combot`. When you
subscribe, you get your **own private queue** — server-named, exclusive,
auto-deleting — bound to the topics you asked for.

That property is what makes rung 1 safe against a live deployment: attaching a
listener is a *fan-out*. Your queue receives copies. You never intercept, delay
or steal a message from the modules already running, and when your notebook
kernel dies the queue disappears with it. You can attach to a deployment
someone else is using and they will not notice.

## A bus without a container

The platform wires components with a dependency-injection container that reads
configuration files. Rungs 1–2 skip all of it: `KombuEventBus` asks its
configuration manager exactly one question — `get_config("cltl.event.kombu")`
— and needs the answer to support `.get(key)` and `in`.

So `attach/connect.py` hands it a plain dict wearing that interface. That is
the whole trick, and it is why attaching needs no config files, no container
and no install of this template. The platform's own test harness solves this
problem the same way.

## Three things that go wrong the first time

**1. `TypeError: PAYLOAD is not a dataclass and cannot be turned into one`**

Emissor's serialisation needs its generic type variables registered before
anything marshals an `Event`. `connect.register_event_types()` does it once,
idempotently, and every function in `connect.py` that touches the bus calls it
first. Write your own entry point and you must do the same.

**2. `SerializerNotInstalled`, deep inside kombu**

`KombuEventBus` takes a serializer *name* and looks it up in kombu's global
registry. If nothing ever registered that name the failure surfaces a long way
from the cause. `connect.register()` registers `'cltl-json'` before any bus is
constructed — and `connect.event_bus()` calls it for you, so simply using that
factory is enough.

**3. The first message never arrives**

This one is worth understanding properly, because the symptom is
*intermittent*.

`KombuEventBus.subscribe` starts a background consumer thread and returns
immediately. The queue is declared and bound to the exchange somewhere in that
thread's near future — **not** before `subscribe()` returns. Anything published
in that window is routed to no queue at all and dropped, because that is what a
topic exchange does with a message matching no binding. No error, on either
side.

`connect.wait_until_bound()` closes the window: it polls RabbitMQ's management
API and waits for the number of queues bound to your topic to actually rise.

**Why counting, and not just checking?** The deployment's own modules are
already subscribed to `cltl.topic.text_in` before you arrive. "Is anything
bound to this topic" is answered *yes* by somebody else's queue. So
`wait_until_bound` records the count *before* you subscribe and waits for it to
rise — that is what makes the check about **your** subscription rather than
about the deployment being up.

### The management API needs its own credentials

RabbitMQ's HTTP management API authenticates separately from AMQP. Pass
`amqp_url=` and `wait_until_bound` takes the credentials from there — the
notebook and `listen.py` both do.

Omit it and it falls back to a pair that is right for the platform's test
harness and wrong for every other broker. The mismatch returns 401, and **a 401
degrades to a flat two-second sleep rather than raising**. That is deliberate —
the management plugin may genuinely be absent — but it means a credentials
mistake is quiet, and reintroduces exactly the race this function exists to
close. The symptom is an occasional dropped first message, never an error
message.

When it works, it says so, and it takes a fraction of a second. If you see it
report a fallback sleep, check the management URL and credentials before
believing anything else on this page.

## Closing the bus

Always call `bus.close()` when you are done. `listen.py` does it in a `finally`;
the notebook has a dedicated last cell.

`KombuEventBus`'s consumer threads retry a lost connection **forever** by
design. A bus left open keeps trying for the life of the process, which is why
a notebook kernel will not shut down cleanly and why stopping the deployment
before the listener leaves you needing `kill -9`. See
[`gotchas.md`](gotchas.md).

## Rung 2: the script

`attach/listen.py` is the notebook made durable — same `connect.py`, same
transform imported from `myorg.example.echo`, so rungs 2 and 3 demonstrably run
identical logic.

```bash
python attach/listen.py --amqp-url amqp://leolani:leolani@127.0.0.1:5672/
```

`--help` lists the rest: management URL, tenant, and the input and output
topics. It runs until `Ctrl-C`.
