# The component (rung 3)

Turning the attached script into a real module: packaged, unit-tested, and
composable into a deployment rather than talking to one from outside.

This is the first rung that needs a `cltl-dev` checkout, with this repository
inside it, because it *builds* the template:

```bash
make build      # twice, the first time — see gotchas.md
make test
```

## The four files

Every Leolani component is four files — an ABC, an implementation, a service and
a container. This one has five, because it has two modalities; the count that
matters is that there is still exactly **one** service and **one** container:

```
src/myorg/example/
  api.py         # the ABCs — what your module does, as pure logic
  echo.py        # the text placeholder to replace
  imagesize.py   # the image placeholder to replace
  service.py     # the bus wiring: subscribe, process, publish
  container.py   # dependency-injection wiring
```

Five, because there are two modalities — but still **one** `service.py` and one
`container.py`. `api.py` declares two ABCs, `Example` (a string in, a string or
`None` out) and `ImageExample` (a numpy array in, a string or `None` out), and
each has its own placeholder file. They are separate interfaces rather than two
methods on one, because they are replaced independently: answering text and
looking at pictures are different jobs, and a module that does only one should
not have to stub the other.

The split that matters is the first one. **`api.py`, `echo.py` and
`imagesize.py` must never import anything from the platform's infrastructure** —
no event bus, no worker, no configuration, and no `cltl.backend`.
`tests/test_layering.py` enforces it by parsing the imports.

`cltl.backend` is on that list for a specific reason. `ImageExample.describe`
receives the pixels as a plain `np.ndarray`, not the
`cltl.backend.api.camera.Image` the platform's storage client actually returns,
precisely so that an implementation cannot know the picture arrived over HTTP
from anywhere in particular. numpy itself is fine: it is a data type, not a
service. Resolving the reference is `service.py`'s job and nobody else's.

That boundary is what makes `tests/test_echo.py` and `tests/test_imagesize.py`
four assertions each with no scaffolding: your actual logic can be tested with no
bus, no config, no container — and, for the image half, no HTTP server.
Everything that needs those lives in `service.py`, which is written once and
rarely changes.

### The second package, which has three files and is not yours

`src/myorg/tenant/` sits beside it, and is deliberately **not** an example of
the pattern above:

```
src/myorg/tenant/
  scenario.py    # builds a Scenario — pure construction, no bus
  service.py     # publishes ScenarioStarted on start, ScenarioStopped on stop
  container.py   # dependency-injection wiring
```

There is **no `api.py`**, and the absence is the design statement.
`myorg/example/api.py` exists because `EchoExample` is meant to be replaced;
nothing in `myorg.tenant` is. A scenario is built exactly one way, and the whole
package is meant to be **deleted** the day your deployment runs a `cltl-context`
per tenant — an ABC would advertise a choice that does not exist.
`tests/test_packaging.py` pins the absence so nobody "completes the pattern".

It exists only because tenant separation requires it. See
[`tenancy.md`](tenancy.md#why-this-module-opens-a-scenario-and-why-that-is-not-a-feature).

### A service that publishes but never listens needs no `TopicWorker`

`TenantService` has none, and that is correct rather than an oversight.
`TopicWorker` is a subscribe-and-dispatch loop; a service that subscribes to
nothing would gain a thread and — under kombu, where it publishes on
`<topic_scenario>.<tenant>` — a queue bound to the very key it publishes on, so
it would receive its own `ScenarioStarted` straight back.

`InfraContainer` asks nothing more of a service than `start()` and `stop()`:
`DIContainer.start`/`stop` are no-ops that `__enter__`/`__exit__` call, and
there is no worker registry to register with. If your own module only ever
publishes — on a timer, or from an HTTP endpoint — it does not need one either.

### One worker, two topics

`ExampleService.start` hands its `TopicWorker` a *list*: `topic_input`, plus
`topic_image` when that is configured. `_process` then dispatches on
`event.metadata.topic`:

```python
if self._image_topic and event.metadata.topic == self._image_topic:
    response = self._describe_image(event)
else:
    response = self._example.process(event.payload.signal.text)
```

Dispatching on the **topic** rather than on the payload type is the deliberate
part. Both are available, but the topic is the one a deployment can rewire from
configuration — which is the whole reason topic names are read from config in
the first place. It is also why `topic` is metadata stamped by the bus on
delivery rather than something a publisher sets: it tells a subscriber which of
*its own* subscriptions an event arrived on. `cltl-monitoring` is the same shape
with six topics.

Two details that are easy to get wrong, and both are in the source with the
reasoning attached:

- **An empty `topic_image` has to be filtered out, not passed through.**
  `TopicWorker` would subscribe to the empty string, which under kombu means a
  real queue bound to the routing key `.<tenant>` and a consumer thread that can
  never receive anything. `ExampleService.topics` is the one line that does the
  filtering.
- **`buffer_size` is raised from the default of 1.** The default rejection
  strategy is `OVERWRITE`, which discards a queued event when the next one
  arrives — so with an HTTP round trip on one of the two topics, an utterance
  published while a fetch was in flight would simply vanish. `cltl-chat-ui` uses
  256 for the same reason.

### The injected image loader

`ExampleService` does not construct its own storage client. `from_config` builds
one and passes it in, as a `Callable[[str], np.ndarray]` — "pixels for this
url":

```python
def load(file_url):
    with ClientImageSource(file_url, storage_url) as source:
        return source.capture().image
```

`cltl-monitoring` injects a `Callable[[str], ImageSource]` instead; narrowing it
to the array is worth the deviation twice over. `capture()` raises outside a
`with` block, so the context manager gets written once, in the one place it
cannot be forgotten — and a test or `attach/inprocess.py` substitutes
`lambda url: array`, with no fake HTTP server and no storage service anywhere.
That seam is the only reason the image half is testable at rung 3 at all.

The `cltl.backend` import lives inside that method, after the configuration
checks. A deployment with `topic_image` empty never pays for it, and a
misconfigured address is reported as a misconfigured address rather than as an
`ImportError`.

## `service.py`

Three responsibilities, and they are worth reading in the source alongside this.

**`from_config`** — every service has this classmethod, and nothing ever calls
`__init__` directly. It reads `[myorg.example]` for the topics, and reads the
event-bus sections only to decide whether the tenancy warning applies.

**`start()`** builds a `TopicWorker` — the platform's subscribe-and-dispatch
loop — and waits for it to actually be running:

```python
self._topic_worker = TopicWorker([self._input_topic], self._event_bus,
                                 provides=[self._output_topic],
                                 resource_manager=self._resource_manager,
                                 processor=self._process,
                                 name=self.__class__.__name__)
self._topic_worker.start().wait()
```

Three things to know before changing that call:

- **`buffer_size` defaults to 1, with an overwrite policy** — the newest event
  wins and older unprocessed ones are dropped silently. Correct for a chat
  reply, wrong if your module must not lose events. Pass a larger
  `buffer_size` if that is you.
- **Never subscribe to an empty topic string.** It binds a real queue that can
  never receive anything. This service treats an empty topic as a
  misconfiguration and raises at construction rather than starting up looking
  healthy and hearing nothing.
- **No intention gating.** `TopicWorker` can gate a module to a conversational
  state, and this one deliberately does not — see
  [`tenancy.md`](tenancy.md#why-there-is-no-intention-gating) before adding it.

**`_process`** transforms and republishes, always with `source=event`. That is
the rule from [`concepts.md`](concepts.md#the-one-rule-always-pass-source), and
it is the one thing in this file you must not lose while editing.

### `stop()`

```python
def stop(self):
    if not self._topic_worker:
        return
    ...
```

`return`, not `pass`. Two shipped platform components write `pass` here, which
falls straight through into a method call on `None` and aborts the container's
whole shutdown chain. `tests/test_service.py` pins the correct behaviour.

### `app`

Returns `None` — this module has no HTTP surface, and a deployment mounts only
the services whose `app` is not `None`. To add one, return a memoized Flask
app; `cltl-monitoring` in the platform is the worked example.

## `container.py`

```python
class ExampleContainer(InfraContainer):
    @property
    @singleton
    def example(self) -> Example: ...

    @property
    @singleton
    def example_service(self) -> ExampleService: ...

    def start(self):
        super().start()
        self.example_service.start()

    def stop(self):
        self.example_service.stop()
        super().stop()
```

Two rules bite here if you do not know them:

- **`@singleton` caches by the bare method name, across the whole process** —
  not per class. An accessor called `service` would collide the instant this
  container is mixed into a deployment alongside any other component that also
  has one. Every accessor here is prefixed; `tests/test_container.py` pins it.
- **`@singleton` raises if the factory returns `None`.** `None` means "the
  factory failed". For a genuinely optional service return `False` and guard
  callers with `if self.thing:`.

And the ordering: `start()` calls `super().start()` **first**, `stop()` stops
the service **first**. Under a deployment's multiple-inheritance chain, that is
what makes everything start bottom-up and stop top-down.

## Running it

**Composed in one process, no broker** — `attach/inprocess.py`, runnable with
`venv/bin/python attach/inprocess.py` after `make build`. It builds an
application container from this one component and round-trips an event through
it. Note that it composes `ExampleContainer` **alone**, without
`TenantContainer`: nothing in `myorg.example` knows what a scenario is, so
nothing there needs one opened.

`src/main.py` composes both, and the order is load-bearing:

```python
class ApplicationContainer(TenantContainer, ExampleContainer):
```

Start order is the **reverse** of the bases tuple, so this runs
`ExampleContainer.start()` — and therefore `example_service.start()` — before
`tenant_service.start()`, and the scenario is announced last, once this
process's own subscriber is up. `stop()` mirrors it: the scenario closes first,
while the bus is still alive. Swap the bases and the scenario is announced to a
component that has not yet subscribed. `tests/test_container.py` asserts this
directly, by recording what was subscribed at the moment each scenario event
arrived.

The separate rule that **the event-bus override must be the first base** applies
to a container synthesised with an *empty* class body — see
`HarnessInfraContainer` in
`integration/src/cltl_integration/runner/inprocess.py`, which explains why
(`KombuEventBusContainer.event_bus` is a plain, non-`@singleton` property, so
whichever base reaches it first through the MRO decides). `ApplicationContainer`
defines `event_bus` in its own body, so it wins regardless of base order.

One more process-global to know about: `@singleton` caches by the **bare method
name** on `DIContainer` itself, for the whole process. That is why every
accessor here is prefixed (`example_service`, `tenant_service`, never
`service`), and why `tests/test_container.py` calls `DIContainer._reset()`
between tests — without it, a second container gets the first one's services,
still bound to the first one's bus.

**Standalone against a real broker** — `python src/main.py`, with a
`config/custom.config` pointing `[cltl.event]` at `kombu` and your deployment's
broker. Serves `/health` on port 8000. Delete that `custom.config` when you are
done; it is gitignored and easy to leave behind pointing at a broker that no
longer exists ([`gotchas.md`](gotchas.md)).

## Packaging

`setup.py` uses `find_namespace_packages(include=['myorg.*'])` — `myorg.*`,
never bare `myorg`. That leaves `myorg` a PEP 420 namespace package, so a
second distribution of yours (`myorg.other_module`) can share the top-level
namespace without either shadowing the other. The `.*` is also why
`myorg.tenant` is picked up with no change to `setup.py`: **one distribution,
two packages**, which is unusual enough to be worth noticing but entirely
normal. Get this wrong and nothing breaks
until that second distribution exists, at which point the failure is very hard
to read — so `tests/test_packaging.py` pins it both ways.

`src/main.py` sits **outside** `src/myorg/` deliberately, so it is never part of
the installed distribution. Only the container image or a developer running it
directly ever executes it, which is what lets it import things the distribution
itself must not depend on.
