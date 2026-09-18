# A classroom deployment of the custom-module exercise

Status: scaffolded, not yet deployed · Date: 2026-09-18

## Why

`custom-module/` is a template for attaching your own code to a running Leolani
agent. Everything in it — the deployment it ships, the notebook, the scripts,
the ten documents — assumes **one person, one laptop, one afternoon**: a broker
on `127.0.0.1`, a password printed in four places, a tenant called `tenant-a`,
and a reader who is simultaneously the operator of the deployment and its only
user.

The course inverts every one of those assumptions. One deployment runs
permanently on a real host, unattended. Thirty students each hold a tenant, each
attach from their own laptop over the network, and each open and close many
scenario sessions over a term.

A review of `custom-module/` against that scenario (see
[Where this came from](#where-this-came-from)) found that almost nothing in it
is *wrong*. It is correct for what it was written for. The failures are all one
assumption inverted — which is why the answer is a second deployment rather than
edits to the first.

## What this is, and what it is not

**A new sibling directory in `cltl-apps`**, alongside `eliza-server/`,
`client/`, `custom-client/` and `custom-module/`. It owns the course's server,
its student provisioning, its credentials, its operations, and the documents
that override `custom-module`'s localhost defaults.

```
ma-combot-2026/
  server.compose.yml  the server stack, hardened for unattended running
  .env.example        hostname, ACME email, admin credentials, image tag
  config/             rabbitmq.conf + the server components' config
  edge/Caddyfile      TLS, per-student auth, method limits for storage
  student/            the tenant stack a student runs on their own laptop
  roster.example      student -> tenant id -> broker user
  bin/                provision, reissue, sync-certs, prune-images
  docs/               operator.md, student.md, known-issues.md
  docs/plans/         this file
  secrets/ sheets/ storage/ logs/     generated, gitignored
```

The compose file sits at the top rather than in a `compose/` directory, because
relative bind mounts resolve against the compose file's own directory: one level
down, every `./config` in it would have silently meant `compose/config`.

The directory is named for the course it serves rather than for what it
contains, unlike its siblings: it is one term's deployment, and a later term
gets its own directory rather than a migration.

**`custom-module/` is frozen.** Not "mostly unchanged" — untouched. It stays the
standalone demonstration of how the platform works, runnable by one person on a
laptop with no course and no server, which is exactly what makes it a template
worth copying. Every classroom-specific value lives here instead. If something
in `custom-module/` turns out to be genuinely wrong rather than merely
laptop-shaped, that is a separate change with its own justification, not a
by-product of this one.

## Where each piece runs

| Server (four containers, any class size) | Student's laptop (one stack each) |
|---|---|
| `rabbitmq` — the shared broker, TLS on 5671 | the tenant stack: `chatui`, on `localhost:8000` |
| `storage` — the shared image store, loopback only | the notebook or `listen.py` |
| `eliza` — one untenanted ELIZA for everyone | a browser pointed at their own chat UI |
| `caddy` — TLS and authentication for storage | |

**The tenant stack is tenant-*side* by routing key, not by location.** Nothing
about a tenant requires it to sit next to the broker; `custom-module`'s own
`docs/tenancy.md` makes the point that a tenant is not a network. The shipped
`deployment/tenant.compose.yml` nonetheless runs on the server, because it joins
the `cltl-example` network as `external: true` (`:126`) and addresses `rabbitmq`
and `storage` by container name (`:72`, `:80`) — all three of which only resolve
on the Docker host running the server half.

Moving it to the laptop is therefore a **configuration** change living in
`ma-combot-2026/student/`, not a platform change. What it buys is most of the edge:
the chat UI has no authentication and, with `[cltl.chat-ui] timeout: 0`, no
per-browser session either (`ChatUiService` takes the `_use_cookie = False`
branch at `cltl-chat-ui/src/cltl_service/chatui/service.py:125-126`). On a public
port for thirty students both are serious. On `localhost` neither matters: the
only person who can reach a student's chat UI is that student.

It costs Docker Desktop on every student machine, and it moves chat UI failures
onto machines the instructor cannot inspect.

## The trust model, stated plainly

This is the decision the rest of the plan hangs off, so it goes first.

**Between students: cooperative, not enforced — deliberately.** A student can
subscribe untenanted and read the whole class, publish into another tenant as
though they were the agent, close somebody's scenario, and fetch a classmate's
uploaded image by the uuid that just went past. `custom-module`'s own
`docs/tenancy.md:58-63` says this outright, and the notebook's final cells teach
the mechanism. We accept it for the first iteration. Students are told, and
trusted.

This is not merely tolerable, it is worth something: enforcing isolation with
per-tenant topic permissions would deny the untenanted observer, and the
untenanted observer is the *control* in the notebook's isolation demonstration —
the thing that distinguishes "tenant-b is isolated" from "the broker is down".
Enforcement would break the one cell that shows what the isolation actually
rests on.

**Between the class and the internet: closed.** Trust extends to the people in
the room, not to anyone who reads a public template repository and finds a
world-reachable broker behind a published password.

**The control that replaces isolation is traceability — and it does not exist
today.** All thirty laptops would otherwise connect as the single user `leolani`
(`custom-module/deployment/server.compose.yml:43-44`) from behind campus NAT.
Under a trust model, attribution is the only thing standing between "someone did
something odd" and an unanswerable question. So per-student credentials move
from being the fix for isolation to being the entire point — issued with
**permissive** permissions, so that nothing is blocked and everything is
attributed.

With the chat UI on the laptop, exactly two things are public and both are
credentialed per student: the broker on 5671, and the storage endpoint behind
Caddy.

## What gets built

### 1. Host and network

1. Provision the host and give it **one** public DNS name. One name serves both
   Caddy (443) and RabbitMQ (5671), so there is one certificate to obtain and
   one to renew.
2. **Stock Caddy**, with automatic HTTPS over HTTP-01. No `xcaddy` build and no
   DNS provider token: those are only needed for wildcard certificates, and
   wildcards were only needed when every student had a subdomain. See
   [What was decided](#what-was-decided-and-why).
3. Caddy fronts **the storage endpoint only** — plus, optionally, the RabbitMQ
   management UI behind `basic_auth` for the instructor.
4. Open ports: 443, 5671, SSH. Everything else binds loopback
   (`"127.0.0.1:15672:15672"`). The short `"host:container"` form that
   `custom-module` uses publishes on *all* interfaces, which is right for a
   laptop and wrong here.

#### The image store is the exception, and needs its own rules

Everything else can hide behind loopback. The image store cannot: both
`load_image` in the student's notebook **and** the chat UI on their laptop now
reach it across the internet. It has to be secured rather than hidden, and —
unlike in a server-side arrangement — that includes the **write** path, because
the chat UI is the only thing that ever writes and it no longer sits on the
deployment's network.

**The obstacle.** Every direct HTTP client in the platform already honours
credentials embedded in `storage_url`: `remote_storage.py:49-53,69-72`
concatenates the URL and calls `requests` directly, and the chat UI uploads with
a plain `requests.put` (`cltl-chat-ui/.../service.py:490`, url built at `:475`).
Only one client drops them — `CltlAudioAdapter.send`
(`cltl-backend/src/cltl/backend/source/client_source.py:27-45`) rewrites the URL
*after* `requests` has already prepared authentication, so no `Authorization`
header is ever generated. Verified empirically against `requests 2.34.2`:
credentials in `storage_url` produce no header, where the same userinfo on a
direct `requests.get` does. That is a bug, not a missing feature, and it is
exactly the kind of silent failure this template spends ten documents
documenting.

**Primary: fix the adapter upstream, then use ordinary HTTP authentication.**
About five lines in `CltlAudioAdapter.send` (`client_source.py:34-42`): after
rewriting the URL, derive credentials from `self._storage_url`
(`requests.utils.get_auth_from_url`), apply them to the copied request, and strip
the userinfo from the URL actually sent. The adapter is mounted in exactly two
places (`client_source.py:76` and `:180`), so one fix covers the audio client,
the image client, `load_image` and `cltl-monitoring`.

Every side then uses the same standard mechanism. A student's `storage_url` is
`https://alice:<pw>@course.example/storage/` in both their notebook and their
`CLTL_STORAGE_URL`. Caddy carries one `basic_auth` block per student, allows
`GET`, `HEAD` and `PUT` and denies everything else, sets a request-body limit
matching `image_max_size` (10 MiB), and attributes every request through
`{http.auth.user.id}` — with no secret in the access log.

The cross-repo cost, stated honestly: a commit in the `cltl-backend` submodule
plus a pointer commit in `cltl-dev` (use the `submodule-git` skill), and a pinned
SHA in the course requirements. What it does **not** need is the useful part:
the chat UI and the storage service are both unaffected, so **no container image
has to be rebuilt**. The fix only has to reach the notebook's `pip install`.

**Fallback: a per-student token in the path** —
`https://course.example/t/<token>/storage/` — if the fix cannot be published and
pinned before the term. It works today with no upstream change, because a path
prefix survives `urljoin` on every client. The cost is that a bearer credential
then lives in URLs and therefore in the access log.

The two are interchangeable late: Caddy swaps a `basic_auth` block for a path
matcher, the student's `storage_url` changes form, and nothing else in the
design moves.

Either way, state the residual risk plainly: a credential holder can overwrite
another student's image by id, because `CachedImageStorage.store` overwrites
without complaint and ids are chosen by the caller
(`cltl-backend/src/cltl_service/backend/storage.py:99-109`). Accepted under the
trust model, and now attributable.

### 2. Broker: per-student credentials

5. One RabbitMQ user per student, random password, **permissive** permissions on
   the vhost (`.*` / `.*` / `.*`). Traceable, not restrictive — this is the
   trust model expressed in configuration. Both the student's notebook and their
   laptop's chat UI connect with it.
6. Keep the administrator credential separate and off every student sheet. Do
   not publish 15672. If the bindings screen is pedagogically load-bearing — and
   it is: `docs/tenancy.md` and `docs/gotchas.md` both send readers there — put
   it behind Caddy with its own authentication.
7. **TLS on 5671**, consuming the certificate Caddy obtained. RabbitMQ does not
   reload certificates on its own: after a renewal run
   `rabbitmqctl eval 'ssl:clear_pem_cache().'`, or restart the broker and accept
   that every connection drops and kombu reconnects.
8. Set `disk_free_limit` and `vm_memory_high_watermark` explicitly, and enable
   rotation on RabbitMQ's own log. Retain connection logs for the term: they
   *are* the audit trail the trust model depends on.
9. Put `?heartbeat=30` in the AMQP URL students are given, so that a laptop that
   closes its lid has its exclusive queue reclaimed promptly rather than after a
   TCP timeout nobody has measured. A URL parameter, so it needs no code change
   — but see [To verify](#to-verify-before-the-term).

**Caddy cannot help here, and no proxy can.** AMQP authentication is in-protocol
SASL during connection negotiation, so per-student RabbitMQ users are required
whatever terminates TLS. Stock Caddy cannot proxy TCP at all; the `caddy-l4`
plugin could terminate TLS for AMQPS, and is declined — a community plugin in
the critical path of the whole class, for no benefit RabbitMQ's own TLS listener
does not already give.

### 3. Deployment hardening

Copied from `custom-module/deployment/`, then changed in five ways. Each is a
laptop-versus-server difference, not a defect in the original.

10. `restart: unless-stopped` on every service. `custom-module` sets
    `restart: "no"` throughout (`server.compose.yml:80,117`,
    `tenant.compose.yml:63,103`), which is right for something you tear down the
    same day and wrong for a host that must survive a reboot unattended.
11. A healthcheck on `eliza`. It is the single shared process serving every
    tenant, it has none today, and its death presents to students as "I only get
    one reply" — which `docs/gotchas.md:241-252` teaches them to read as *their
    own listener having died*. Thirty people would debug their own laptops.
12. Docker `logging:` driver options on every service, and `level: INFO` rather
    than `DEBUG` in the logging config
    (`deployment/config/server/logging.config:15`). DEBUG with no rotation is a
    disk-full outage on a timer.
13. A retention sweep over the image store. There is no delete path in
    `CachedImageStorage` at all — `store` writes a PNG and a `_meta.json` per
    upload and nothing ever removes them. The cascade is why this is not
    cosmetic: images and RabbitMQ share a filesystem, and a full disk trips the
    broker's disk alarm, which blocks publishers for every tenant at once.
14. Pin `CLTL_IMAGE_TAG` to a version tag rather than `:latest`, and pin the
    three platform libraries to commit SHAs in this directory's own requirements
    file — the same SHAs that carry the adapter fix above.
    `custom-module/requirements.notebook.txt` tracks the moving `ref_scenarios`
    branch and says so in its own header; with a server pinned only by when it
    was last pulled, that is how a class splits into "works" and "unmarshal
    error" along install-date lines.

### 4. Student stacks

15. A roster mapping student → tenant id → broker user → storage credential.
    **No port column and no subdomain:** every laptop uses `localhost:8000`, so
    `CLTL_CHATUI_PORT` can become a plain default instead of the required value
    it is today. Tenant ids must match `^[a-z0-9][a-z0-9_-]*$` — the rung-4
    guard in `custom-module/src/myorg/tenant/service.py` is right about that and
    rungs 1–2 do not enforce it, so the roster is where it gets checked.
16. `ma-combot-2026/student/`: a copy of `tenant.compose.yml` with four changes —
    drop the `external` network, point `CLTL_AMQP_URL` at
    `amqps://<user>:<pw>@course.example:5671/?heartbeat=30`, point
    `CLTL_STORAGE_URL` at the authenticated storage URL, and set
    `CLTL_MONITORING_URL` to a localhost address or leave it empty.
17. Accept the new support cost: a broken chat UI is now on a machine the
    instructor cannot log into. Ask for `docker compose logs` rather than
    guessing, and keep the reset procedure short enough to send in a message.

### 5. Course materials

18. A per-student connection sheet, four values: their `amqps://` broker URL
    with their own credentials, their tenant id, their authenticated storage
    URL, and `http://localhost:8000/chatui/static/chat.html`.
19. An override note for the three addresses the notebook hardcodes —
    `AMQP_URL` and `MANAGEMENT_URL` in cell 1, and `STORAGE_URL` in cell 12. The
    third is the one that matters: it comes from `connect.DEFAULT_STORAGE_URL`,
    sixty lines into the image section, and a student who changes only the first
    gets a notebook whose entire text half works while images fail as a caught
    warning whose documented causes do not include "you are pointing at your own
    laptop".
20. A note that `TENANT_B` in cell 18 is now a classmate. Either reserve an
    unused id for it, or warn that cell 19's confident *"traffic it should not be
    able to see"* message is expected on a shared server and is not a fault.
    Twenty-nine of thirty students will otherwise hit it and report a bug.
21. A known-issues page, carrying the things neither of the template's documents
    covers because neither is wrong on a laptop:
    - A `ScenarioStopped` clears whatever scenario the chat UI is holding,
      regardless of which scenario it names
      (`cltl-chat-ui/src/cltl_service/chatui/service.py:564-574` keys only on
      the payload type). An abandoned kernel whose cleanup cell is run later
      kills the student's *current* conversation.
    - Two browser tabs are one shared conversation, not two sessions, and the
      chat UI keeps every message of every session in memory for the life of the
      container (`cltl/chatui/memory.py:16-17` is append-only; `stop_chat`
      clears only the current id). Now a per-laptop concern rather than a
      cross-student one.
    - Re-running the notebook's setup cell abandons a bus whose consumer threads
      retry forever; re-running the handler cell *appends* a handler, so the
      notebook then replies twice, then three times.

### 6. Operations

22. Monitor disk, RabbitMQ alarms, and `eliza` liveness. The class cannot report
    any of these usefully — every symptom looks like their own laptop.
23. Write down the reset procedures: restart `eliza`, prune the image store,
    reissue a student's credentials.
24. Rehearse with three fake students end to end before week one, including one
    off-campus laptop on bad wifi.

## What was decided, and why

**`custom-module` frozen rather than parameterised.** A template that requires a
course to run is no longer a template. Every classroom value is an override that
lives here, which also means the demo keeps working for the next reader who
finds the repository with no server to attach to.

**Students copy the template; the course ships only connection details.**
`custom-module`'s stated purpose is "copy this repository". Following that keeps
one copy of the teaching material in the world and nothing to keep in sync.

**Tenant stacks on laptops, not on the server.** This is the decision that sets
the size of everything else. It removes thirty containers, thirty published
ports, thirty subdomains, the wildcard certificate, the custom Caddy build and
the per-student chat UI authentication — and it turns the chat UI's missing
authentication and missing session from public exposure into a property of the
student's own machine. The server stays at four containers for any class size,
and the 1 s transcript poll (`chat.js:2`) never crosses the network. It costs
Docker Desktop on every laptop; confirm the licensing position before the term.

**Fix the adapter upstream rather than work around it.** Every other HTTP client
in the platform already honours credentials in `storage_url`; only the
`cltl-storage:` adapter drops them. Working around that with a token in the URL
would leave the bug in place for the next person and put a bearer credential in
every access log. The fix is about five lines and needs no image rebuild.

**Stock Caddy over an `xcaddy` build.** A consequence of the laptop decision:
one hostname needs only HTTP-01. The earlier wildcard/DNS-01 plan was premised
on a subdomain per student and is superseded — recorded here so it is not
re-litigated.

**RabbitMQ's own TLS over `caddy-l4`.** No proxy can authenticate AMQP, so the
plugin would only move where TLS terminates, at the price of putting a community
plugin in the critical path of the whole class.

**Per-student users with permissive permissions, not topic permissions.** Topic
permissions would enforce isolation and break the notebook's untenanted control
cell, which is one of the better things in the material. Permissive per-user
credentials give the benefit we actually want — attribution — without the cost.
If a later iteration needs enforcement, topic permissions are the mechanism, and
cells 17–19 of the notebook are what it will cost.

**Connection-level attribution, not message-level.** Per-user credentials
attribute connections, channels and management actions. Attributing an
individual *message* needs the `rabbitmq_tracing` plugin, which is real and has
real overhead. Not in the first iteration; named so the decision is visible
rather than overlooked.

## Deliberately not done

- **No enforced tenant isolation.** Accepted for iteration one; see
  [the trust model](#the-trust-model-stated-plainly).
- **No per-tenant image storage.** Two students' pixels stay in one store,
  separated by an unguessable uuid, exactly as `docs/tenancy.md:86-97` describes.
  Enforcement would mean a `cltl-backend` per tenant.
- **No scenario expiry.** Nothing in the platform expires a scenario; the
  recovery is to open a new one, and that is documented. Adding a TTL or
  heartbeat to `cltl-chat-ui` would end conversations nobody asked to end.
- **No fix for the shared `ElizaImpl`.** One instance serves the whole class.
  Its responses are drawn from static tables, so it is effectively stateless;
  its one shared flag gates a greeting branch this deployment disables anyway.
- **No changes to `custom-module`.** Including the three cells that mislead on a
  shared server — those are handled in the course documents, where the
  classroom context actually exists.
- **One platform change, and only one:** the `cltl-backend` adapter fix. It is a
  bug fix with a five-line diff and no image rebuild, not a feature the course
  needs the platform to grow.

## What the scaffolding actually verified

Built and checked in place, rather than asserted:

- **The Caddyfile validates against real Caddy 2.8** (`caddy validate`), which
  also confirms the `basic_auth` spelling — it was `basicauth` before 2.8 — the
  `import` inside that block, the method matcher and `request_body max_size`.
- **`config/rabbitmq.conf` is accepted by RabbitMQ 4.1**, the TLS listener comes
  up on 5671, and `management.path_prefix = /rabbitmq` answers 200 at the prefix
  and 301 at the root. Pinning 4.1 rather than the demo's 3.12 is a change this
  made: **3.12 is end of life** and takes no security updates, which is fine for
  an afternoon on a laptop and not for a term on a public host.
- **Both compose files parse**, every bind mount resolves under this directory,
  and the published ports are exactly 80, 443 and 5671 — plaintext AMQP, the
  management UI and storage all bind `127.0.0.1`. The `:?` guards fire with
  their own messages when a variable is missing.
- **All four configuration files parse** as `ConfigParser` documents.
- **The scripts are syntax-clean**, and `provision.sh` was run far enough to
  confirm it skips comments and blank lines, rejects a tenant id containing a
  `.` before touching Docker, and generates credentials idempotently.

Nothing here has met a live broker, a real certificate or a student. The list
below is what that still leaves open.

## To verify before the term

1. **`amqps://` reaches `KombuEventBus` intact**, and certificate verification
   behaves. The URL is passed straight to `kombu.Connection`, so it should, but
   kombu is not installed in the container this plan was written in.
2. **`?heartbeat=30` reaches the connection**, same caveat. If it does not, the
   reclaim window for a suspended laptop is whatever the negotiated default is —
   measure it rather than assume.
3. **`ssl:clear_pem_cache()` picks up a renewed certificate** without restarting
   the broker.
4. **Docker Desktop licensing** for the institution, since every student now
   needs it.
5. **If the fallback is used:** that Caddy's token-prefix stripping lands
   correctly on the `/storage` mount.

Two things worth reporting upstream regardless of what this course does: the
`cltl-storage:` adapter dropping credentials, and the chat UI's
`url_for`-generated image URL (`cltl-chat-ui/.../service.py:441-449`), which
emits a root-relative path and so cannot be served under a proxy path prefix.

## Where this came from

A critical review of `custom-module/` against this scenario, run across two
independent reviewers plus direct verification of the platform sources cited
above. Its conclusions in one line each:

- The notebook *code* is ready; the deployment around it is not, and three
  notebook cells are actively misleading at classroom scale.
- The blocking items are all about exposure to the internet, not about students:
  one shared credential, everything published on all interfaces, an
  unauthenticated image store that accepts writes, an administrator management
  UI the documents tell students to open.
- The strengths are real and untouched by this plan: the `CLTL_TENANT` guards,
  the byte-identical config blocks that make thirty tenants a loop rather than
  thirty files, per-subscriber exclusive queues, `listen.py`'s teardown
  ordering, and `docs/tenancy.md`, which predicted most of the review before it
  was written.
