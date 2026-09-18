# Adding the image modality

*The implementation plan for the second modality, as executed.* Follows
[`tenant-isolation.md`](tenant-isolation.md), which produced the two-half
deployment this builds on.

---

## 1. Context

The template demonstrated exactly one modality. `myorg.example` subscribed to
`cltl.topic.text_in`, uppercased the utterance, and published to
`cltl.topic.text_out` — a platform whose entire point is *multimodal* signals,
taught through its least interesting one.

The goal: the same module also listens to **image** signals, fetches the pixels
the signal refers to out of the platform's storage service, works out the
dimensions from what came back, and answers on `text_out` with
`The image you uploaded is 700x640`. A person drives it from the chat UI's Image
panel. All four rungs, verified end to end.

Two findings made it much smaller than it sounds, both read out of the platform
source rather than assumed:

- **`cltl-chat-ui` already does image upload and region annotation** (submodule
  commit `1a9e02e`), and already has a Monitoring tab. Both were off **by
  config** here: `image_upload: False`, `topic_image:` empty, `monitoring_url:`
  empty. No `cltl-chat-ui` change was needed — which is just as well, since it
  is a different repository and out of scope.
- **Submitting an image publishes one `ImageSignalEvent` and nothing on the
  utterance topic** (`chatui/service.py:364-375`), so `cltl-eliza` never sees a
  picture. An image draws **one** reply where text draws two. That contrast was
  free, and it turned out to be the clearest single demonstration of
  "subscribe to what you care about" in the template.

What the deployment was missing was the store the pixels live in. The signal
carries no pixels at all: `ImageSignal.for_scenario` hardcodes `array=None`
(`emissor/representation/scenario.py:84`) and puts a `cltl-storage:image/<id>`
reference in `signal.files`.

### Decisions taken with the user

| | |
|---|---|
| **Fetching the pixels** | `ClientImageSource` — the platform's own client, as used by `cltl-monitoring` and `cltl-emissor-data`. Free `cltl-storage:` scheme resolution and a numpy array out, at the cost of a `cltl.backend[impl]` dependency. The rejected alternative was hand-decoding the base64/JSON with stdlib only, which would have added no dependency but would have put a wire format in the template's own source |
| **Monitoring** | One `cltl-monitoring` **per tenant** — it subscribes, so one shared instance would aggregate every tenant's conversation behind one URL |
| **Storage** | One `cltl-backend` (storage only) **shared on the server**, published so rungs 1–2 can reach it from outside Docker |
| **Module shape** | A second ABC beside `Example`, a second placeholder beside `echo.py`, and **one** service whose `TopicWorker` takes both topics and dispatches on `event.metadata.topic` |

---

## 2. The design

### 2.1 Two interfaces, one service

`api.py` grew `ImageExample.describe(image: np.ndarray) -> Optional[str]`
alongside the untouched `Example`. Separate interfaces rather than a second
method, because they are replaced independently — and `Example`'s own docstring
promises "a string in, a string or None out".

`describe` takes a **numpy array**, not the `cltl.backend.api.camera.Image` the
storage client actually returns. That is the one boundary this change creates,
and `tests/test_layering.py` enforces it by adding `cltl.backend` to the
forbidden-import list for `api.py` and `imagesize.py`: an implementation must
not be able to know the picture arrived over HTTP from anywhere in particular.
numpy is fine — a data type, not a service.

`ExampleService` handles both. `start()` passes its `TopicWorker` a list;
`_process` dispatches on `event.metadata.topic` rather than on the payload type,
because the topic is the half a deployment can rewire from configuration.
`cltl-monitoring` is the same shape with six topics.

Two non-obvious details:

- **An empty `topic_image` is filtered out, not passed through.** `TopicWorker`
  would subscribe to the empty string, which under kombu is a real queue bound
  to `.<tenant>` and a consumer thread that can never receive anything.
- **`buffer_size` went from the default 1 to 8.** The default rejection strategy
  is `OVERWRITE`, so with an HTTP round trip on one topic, an utterance
  published during a fetch would be silently discarded.

### 2.2 The injected loader — the decision everything else rests on

`ExampleService` does not construct its own storage client; `from_config` builds
one and passes it in as `Callable[[str], np.ndarray]`.

`cltl-monitoring` injects `Callable[[str], ImageSource]` instead. Narrowing it to
the array paid twice: `ClientImageSource.capture()` raises outside a `with`
block, so the context manager is written once where it cannot be forgotten; and
the test double became `lambda url: array`, with **no fake HTTP server** — which
is the only reason the image path is exercisable at rung 3, in
`attach/inprocess.py`, with no broker and no storage anywhere.

The `cltl.backend` import sits inside that method and *after* the configuration
checks, so a text-only deployment never pays for it and a bad address is
reported as a bad address rather than as an `ImportError`.

### 2.3 `image_storage_url`: refuse two things, repair one

Mirrors `myorg.tenant`'s strict tenant check, and reachable only when
`topic_image` is set:

| Value | Result |
|---|---|
| empty | `ValueError` |
| `$CLTL_STORAGE_URL` | `ValueError` — an unexpanded variable; `EnvInterpolation` passes an undefined one through verbatim with only a warning |
| `…/storage` | **normalised**, with a warning |

The asymmetry is the interesting part. The reference is resolved with
`urljoin(storage_url, "image/<id>")`, and `urljoin` drops the last path segment
of a base without a trailing slash — so a missing slash is a real bug. But
`cltl-apps/eliza-server`'s own `custom.config` ships it that way, so refusing
would make this module unusable against a stock deployment config. Refuse a
*missing* address; repair a *malformed* one.

### 2.4 Deployment

`storage` joined the server half, running `src/storage_main.py` rather than
`src/main.py`. That is `StorageContainer` alone, and it is also the only entry
point that is safe on a shared bus: `BackendContainer` constructs an
`EventLogService` that subscribes to `event_bus.topics`, and `KombuEventBus.topics`
unions consumed topics with the tenant-suffixed keys it has *published* on — so
on the server half it would subscribe to `cltl.topic.text_out.tenant-a` as
though that were a topic name. `multitenant_server.config` records the same
reasoning for leaving cltl-backend out of the platform's own shared half
altogether.

`deployment/storage/image/` and `audio/` are **committed**, with a `.gitkeep`
each carrying the reason: `CachedImageStorage.__init__` calls
`os.makedirs(os.path.dirname(storage_path))`, creating the directory's *parent*
rather than the directory, and `cv2.imwrite` into a missing directory returns
`False` instead of raising. The failure is a `204 No Content` on the PUT and a
`KeyError` on the GET, with nothing anywhere mentioning a directory.

One `$CLTL_STORAGE_URL` is read by the chat UI (via its documented fallback to
`[cltl.backend] storage_url`), by cltl-monitoring, and by the rung-4 module — so
the address of the store cannot drift between the three.

### 2.5 Storage is untenanted, and that is stated rather than implied

`StorageContainer` subscribes to no topic, so it has no tenant dimension to get
right: it is shared infrastructure like the broker. The rule the deployment now
follows out loud is **"anything that reads the bus is tenanted"** — which is why
monitoring is per tenant and storage is not.

The cost is real and is written down in `tenancy.md` rather than left to be
inferred: two tenants' pixels sit in one store, and the only thing between
tenant-a and tenant-b's picture is the uuid it is filed under.
`GET /storage/image/<id>` asks for no tenant and checks none. A uuid is
unguessable, which is not the same as protected, and it travels in the
`signal.files` of every event on that tenant's image topic.

---

## 3. Verified against a live deployment

Run in full, then torn down. Unit tests first: **90 passed, 10 subtests** (up
from 67), with `cltl.backend[impl]` installing cleanly from `ref_scenarios` —
which settled the plan's third risk.

| Check | Result |
|---|---|
| The published chat-ui image carries the feature | `GET /chatui/config` → `{"image_upload":true,…}` |
| Both UIs blank before anything attaches | `{"scenario_id":null}` on `:8000` and `:8001` |
| Pixels reach the shared store | `GET /storage/image/<id>` → `shape [640,700,3]`, `dtype uint8`, `view [0,700,0,640]`, `depth null` |
| On disk | `deployment/storage/image/<id>.png` + `<id>_meta.json` |
| The module answers, once | `The image you uploaded is 700x640 (via attach/listen.py)` and **no** ELIZA reply |
| Text still draws two | `YOU SAID: I AM WORRIED ABOUT ROUTING KEYS …` **and** `Did you come to me because you are worried about routing keys?` |
| Bindings | `image.tenant-a`, `text_in.#`, `text_in.tenant-a` ×2, `text_in.tenant-b`, `text_out.{a,b}`, `scenario.{a,b}` — and **no** bare `cltl.topic.image`, no `image.#` |
| Isolation, with control | untenanted observer: 5 events, all `tenant-a` (`text_in` 1, `text_out` 3, `image` 1). `tenant-b` observer: **0** |
| An unstored id | HTTP **500** with `KeyError: No image with id … found in the storage` — not a 404 |
| `--no-images` | one subscription, and says so |
| The three `image_storage_url` branches | empty → `ValueError`; `$CLTL_STORAGE_URL` → `ValueError`; no trailing slash → normalised with a warning |
| Clean shutdown | `Stopping.` → `Closed scenario …` → exited |
| Rung 3, no broker and no storage | `attach/inprocess.py` prints both replies, including `The image you uploaded is 64x48` |
| Rung 1, the notebook's own cells executed verbatim | text → `NOTEBOOK CELL TEST (via notebook)` **and** ELIZA's reply; image → `The image you uploaded is 700x640 (via notebook)`, alone |
| Teardown, tenants first | no containers, no `cltl-example` network |

### What the run caught

**`ghcr.io/leolani/cltl-monitoring` is not a published package.** It answers
`unauthorized` for `:latest` and for a version tag alike, while
`cltl-emissor-data` pulled anonymously from the same registry in the same
minute — so this is absence, not throttling. Monitoring therefore moved behind a
compose **profile**, off by default, with `CLTL_MONITORING_URL` empty so the chat
UI leaves the tab out rather than showing one whose iframe cannot load. Enabling
it is one flag and two variables the day the image exists.

That in turn forced a detail worth recording: **a service excluded by a profile
is still interpolated.** A `:?` required variable would have failed the default
`up` for a service that `up` does not start, so nothing monitoring-related uses
one.

**The size-mismatch path proved itself by accident.** A probe declared
`width=320&height=240` while posting the 700×640 PNG, and the listener answered
`700x640` from the pixels while logging `declared bounds (0, 0, 320, 240)`
beside it. That is exactly the case the cross-check exists for, and it is the
concrete answer to "why fetch at all when the signal already says the size".

**A pre-existing hang in the notebook, found by executing it rather than
reading it.** The wire-up cell — text-only before this change — did
`bus.subscribe(TOPIC_IN, respond)` and then `wait_until_bound([TOPIC_IN])`, on a
topic the `show` cell four cells earlier had already subscribed. That call could
never succeed: `KombuEventBus` keeps **one consumer per topic**, so a second
`subscribe` to a topic it is already consuming appends the handler to that
consumer's list and creates no new queue (`kombu.py`'s `subscribe`). The check
waits for the number of bound queues to *rise*, so it hung for the full 30
seconds and then raised a `TimeoutError` naming a routing key that was, in fact,
bound — which reads like a broker fault and is not one.

The extended cell inherited the bug and doubled it. The fix is to delete the
call and say why: the handler is live the moment `subscribe` returns, and only
the *first* subscription to a topic on a given bus has a binding to wait for.
`listen.py` is unaffected — its bus is fresh and its two subscriptions really
are the first — and the rule is now in `wait_until_bound`'s own docstring,
`attaching.md`, and `gotchas.md`.

**A fragile cell dependency, created by the reordering.** Putting the image
section between the manual text reply and the wire-up left two cells depending
on imports that lived in a cell a reader might reasonably skip. The five payload
imports moved to the setup cell at the top, where `from connect import …`
already is.

Two self-inflicted confusions, recorded so the next reader does not repeat them:
`pgrep -f listen.py` matches the shell that is running the `pgrep`, which made a
cleanly-exited process look like it was still running; and zsh does not
word-split an unquoted parameter, so a `for t in "tenant-a 8000"; do set -- $t`
loop silently passed the whole string as `$1` and did nothing.

---

## 4. Not done, and why

- **Rung 4 remains unbuilt.** No `makefile`, and `cltl-dev/cltl-requirements/mirror/`
  and `leolani/` are empty, so no local image build can resolve a `cltl.*`
  package. Unchanged by this work.
- **`requests` in the rung-4 image** is consequently unverified.
  `cltl.backend[impl]` names it; it is in `cltl-base` only transitively, and a
  `--no-index` install that must *resolve* the name will only succeed if it is
  genuinely already satisfied. Flagged in `docker.md`, not papered over.
- **The regions a person draws are ignored.** They arrive inside
  `signal.mentions`, shaped exactly as `cltl-object-recognition` produces them.
  Reading them is a natural next exercise and a poor placeholder — measuring the
  picture is obviously silly, which is what a placeholder should be.
