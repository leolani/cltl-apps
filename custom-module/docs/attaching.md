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

## Five things that go wrong the first time

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

**3. The chat UI is blank and stays blank**

Nothing has opened a scenario, and in this deployment nothing will: there is no
`cltl-context` in either half. `cltl-chat-ui` renders nothing and refuses to
publish until it has seen a `ScenarioStarted` on its own tenant's routing key.

So `connect.py` carries `start_scenario`/`stop_scenario`, and both the notebook
and `listen.py` call them. **This is not something an attached module normally
does** — it is a chore that falls to the custom side purely because the chat UI
runs inside a tenant and a tenant's scenario can only be opened on that tenant's
own bus. `docs/tenancy.md` is the long version; the short version is that it is
a tenancy tax, not a feature.

Those helpers are a deliberate copy of the platform's
`integration/src/cltl_integration/drivers/scenario.py` and a parallel of this
template's own `src/myorg/tenant/scenario.py`, rather than an import of either —
rung 1 has nothing installed, which is the point of rung 1.

**4. The first message never arrives**

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

### Two different questions, and `baseline=`

The default behaviour answers **"is *my* subscription live"**: snapshot the
counts, wait for them to rise by one.

Opening a scenario needs the other question — **"is *anyone* bound yet"** —
because the queue that has to exist belongs to the chat UI, not to you. Waiting
for a rise would be answered by your own subscription. Passing `baseline={}`, an
all-zero starting point, turns the increment check into a presence check:

```python
wait_until_bound(MANAGEMENT_URL, [TOPIC_SCENARIO], tenant=TENANT,
                 amqp_url=AMQP_URL, baseline={})
scenario = start_scenario(bus, TOPIC_SCENARIO)
```

Same trick, same reason, as `ComposeRunner.await_bindings(topics, {}, tenant)`
in the platform's own harness.

**Subscribe to everything you want, then wait once.** The snapshot is taken when
`wait_until_bound` is *called*, so a second call made after the first returned
would snapshot a world in which its own binding had already landed — its count
could never rise past its own baseline, and it times out. `listen.py` subscribes
to both its topics and then makes one call covering both; the notebook's
isolation cell does one bus at a time for the same reason. The arrangement that
looks tidier is the broken one, and it has already cost this repository once.

**And only wait for a topic this bus has not subscribed to before.**
`KombuEventBus` keeps one consumer per topic — one queue, one binding — so a
second `subscribe` to a topic it is already consuming appends your handler to
that consumer's list and creates no new queue
([`kombu.py`](https://github.com/leolani/cltl-combot)'s `subscribe`). The count
therefore cannot rise, and the call does not merely return early: it hangs for
the whole timeout and then raises. The second handler is live as soon as
`subscribe` returns.

That is why the notebook's wire-up cell subscribes `respond` to two topics that
`show` and `show_image` already bound, and then waits for *nothing*. Getting
this wrong is a 30-second hang followed by a `TimeoutError` naming routing keys
that are, in fact, bound — which reads like a broker problem and is not one.

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

**5. `ModuleNotFoundError` for a package the venv demonstrably has**

The notebook is running on a different interpreter than the one you installed
into, and nothing says so.

A venv's stock kernel is called `python3` and its `kernel.json` launches a
**bare `python`**, resolved through `PATH` when the kernel starts rather than
pinned to the venv:

```json
["python", "-m", "ipykernel_launcher", "-f", "{connection_file}"]
```

`example.ipynb` asks for that generic `python3` by name, so whichever Jupyter
opens it supplies its own. Ask the kernel what it is — `import sys;
print(sys.executable)` — and give the venv a kernel of its own, which records an
absolute path:

```bash
python -m ipykernel install --user --name cltl-example \
    --display-name "cltl-example (.venv)"
```

In VS Code, the equivalent is the kernel picker at the top right. Full symptom
and cure in [`gotchas.md`](gotchas.md#modulenotfounderror-no-module-named-cltlbackend-but-the-venv-has-it).

## Getting the pixels of an image

`connect.load_image` is the fifth helper, and it exists because the surprise is
worth meeting once at rung 1: an image signal does not contain an image.

```python
image = load_image(signal.files[0], DEFAULT_STORAGE_URL)
height, width = image.shape[:2]          # numpy is (rows, cols)
```

`signal.files[0]` is `cltl-storage:image/<id>` — a scheme, not a URL.
`ClientImageSource` resolves it against the storage address and decodes what
comes back, which is JSON with the pixels base64-encoded rather than PNG bytes.
Three details it saves you from:

- It must be used as a **context manager**; `capture()` raises outside one.
- `storage_url` **must end in a slash**. The reference is resolved with
  `urljoin()`, which drops the last path segment of a base without one, so
  `…:8002/storage` looks for `…:8002/image/<id>`. The packaged module appends
  the slash and warns; `load_image` does not, on purpose — this is the rung where
  you are meant to see the trap.
- The fetch **can legitimately fail**. The chat UI's upload of the pixels is
  best-effort and needs `cv2`, and it publishes the reference either way — so
  wrap the call and carry on, as `listen.py` does. An unstored id answers HTTP
  500 with a `KeyError`, not 404.

`cltl.backend[impl]` is the third line of `requirements.notebook.txt` and the
only one the text half does not need; the import is inside the function so the
text cells keep working without it.

**Which is also how you learn your notebook is not running in the venv.** See
the fifth item above: `load_image` is usually the first cell that needs anything
the *other* environment does not already have, so a kernel on the wrong
interpreter fails precisely here and nowhere earlier.

## Checking the isolation from a notebook

The last section of `attach/example.ipynb` attaches two extra observers and
tallies what each one receives: a tenanted bus for a *different* tenant, and an
untenanted one that binds `<topic>.#` and therefore sees everybody.

Two points of technique there, both reusable:

- **No second stack is needed.** `event_bus(AMQP_URL, tenant="tenant-b")`
  subscribes on `<topic>.tenant-b` whether or not any container is running for
  tenant-b. Bindings do not care whether the tenant "exists"; a tenant is a word
  in a routing key.
- **The untenanted observer is a control, not decoration.** Subscribing as
  another tenant and receiving nothing is exactly what you would also see with
  the broker down, the chat UI unplugged, or nobody typing. The result worth
  reporting is that the untenanted observer *did* see the conversation and the
  other tenant did not. Same reasoning as `wait_until_bound` counting bindings
  rather than checking for them.
- **It covers the image topic too**, so the claim is about both modalities. Note
  what it does *not* cover: the pixels themselves. Those live in a shared,
  untenanted store, and the routing key has no say over who can `GET` them —
  see [`tenancy.md`](tenancy.md#anything-that-reads-the-bus-is-tenanted-storage-does-not).

Both extra buses have to be closed along with the main one — see below.

## Closing the bus

Close the scenario **first**, then the bus: closing a scenario is a publish, so
the bus has to still be open for it. `listen.py` does both in a `finally`; the
notebook has a dedicated last cell for both, and closes **every** bus it opened
— the two isolation observers included, since each one holds consumer threads of
its own.

Closing the scenario also clears the chat UI's transcript, which is a convenient
way to see it land rather than taking it on faith.

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
python attach/listen.py --tenant tenant-a \
    --amqp-url amqp://leolani:leolani@127.0.0.1:5672/ \
    --management-url http://127.0.0.1:15672
```

`--tenant` is **required and has no default**. There is no untenanted
conversation to join, and a default would pick a tenant on your behalf. Passing
`--tenant ''` attaches as a read-only observer of every tenant on the exchange,
and is refused unless you also pass `--no-scenario` — an untenanted
`ScenarioStarted` lands on the bare key and reaches nobody.

`--no-scenario` is for when something else already opened this tenant's
conversation: its own module container, or another listener. Two openers for one
tenant leaves the chat UI on whichever arrived last.

`--help` lists the rest: management URL, and the input, output and scenario
topics. It runs until `Ctrl-C`, then closes the scenario before the bus — in a
`finally`, so a crash does the same.
