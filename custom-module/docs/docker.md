# Docker (rung 4)

Building your module into an image and running it inside the deployment, like
any platform component.

## What is published here, and what is not

Worth being clear about, because it is the one place the two halves differ:

- **The deployment** you join comes from images on `ghcr.io/leolani`. Nothing
  to build; see [`deployment.md`](deployment.md).
- **This image is yours** and has to be built — and building it needs a
  `cltl-dev` checkout, because the `Dockerfile` resolves the platform's
  libraries offline from a local package registry (`cltl-requirements/`) that
  the published *images* do not carry.

Publishing a `ghcr.io/myorg/cltl-example` of your own is the point at which
*your* users stop needing that checkout too.

## Building

```bash
make docker-ghcr-build
```

produces `ghcr.io/myorg/cltl-example:<version>` and `:latest`, built `FROM`
`ghcr.io/leolani/cltl-base:latest` — the same base image every platform
component uses. The registry and base are set at the top of this repo's
`makefile`; [`making-it-yours.md`](making-it-yours.md) covers changing them.

The `Dockerfile` follows the platform's own pattern: a named build context
supplies the offline package registry, `pip install --no-index` resolves
everything without touching the network, and a `HEALTHCHECK` polls `/health` on
port 8000 — the same endpoint `src/main.py` serves when run standalone.

### One deliberate deviation: this image ships its own config

Every platform component's image ships with **no** `config/` directory at all.
Its deployment bind-mounts a whole generated directory over it, because the
deployment already knows about that module and generates a matching
`[cltl.<name>]` section for it.

That cannot work for a third-party module. A deployment that has never heard of
this template has no `[myorg.example]` section to generate, and the container
would fail at startup with `ValueError: No configuration for myorg.example`.

So this image carries its own `config/default.config`, with the canonical topic
names already filled in, and a deployment only has to supply the **connection
overlay** — which broker, which tenant. That asymmetry is the thing to
understand before changing how the config is mounted.

## Joining one tenant of a running deployment

`compose/example.compose.yml` attaches one service to a deployment that is
**already running**. It is not a deployment of its own. You run it once **per
tenant** — the project name interpolates `CLTL_TENANT`, so tenant-a's module and
tenant-b's coexist.

With the deployment from [`deployment.md`](deployment.md) up:

```bash
make docker-ghcr-build

export CLTL_DEMO_CONFIG=$PWD/deployment/config/tenant
CLTL_TENANT=tenant-a docker compose -f compose/example.compose.yml up -d
CLTL_TENANT=tenant-b docker compose -f compose/example.compose.yml up -d
```

Three variables, and all three are worth understanding rather than pasting.

**`CLTL_TENANT`** is the only thing that makes this container tenant-a's rather
than tenant-b's. It is **required**, at two levels: compose refuses to
interpolate the project name without it, and `myorg.tenant` refuses to start on
an empty or unexpanded value. Both refusals exist because the failure they
prevent is silent — see [`tenancy.md`](tenancy.md).

**`CLTL_SERVER_NETWORK`** defaults to `cltl-example`, the network
`deployment/server.compose.yml` creates and pins by name. Note what it is *not*:
it is the **server's** network, shared by every tenant, so joining it is how this
container reaches the broker and is emphatically not what scopes it to a tenant.
Against the integration harness's stacks the name is randomised, so confirm
rather than assume:

```bash
docker network ls --format '{{.Name}}' | grep cltl
```

**`CLTL_DEMO_CONFIG`** is the directory holding the deployment's configuration —
the **tenant** half, `deployment/config/tenant`, because that is the one
carrying `tenant: $CLTL_TENANT`. The compose file mounts **one file** out of it:
that `default.config`, over this image's `config/custom.config`, where the
platform's loader reads it as an overlay on top of the `default.config` already
baked into the image. That is the asymmetry from the previous section in
practice: the image brings its own `[myorg.example]` and `[myorg.tenant]`
sections, the deployment brings the broker connection, and the two are merged by
the config loader.

Finally, every `$VAR` that the mounted config interpolates must be defined in
the container's environment, **even when empty** — an undefined one is passed
through as a literal string with only a warning, never a hard failure. See
[`tenancy.md`](tenancy.md) for what that specifically breaks.

### One module per tenant, and the scenario race

Each module container opens its own tenant's scenario at startup, after waiting
`[myorg.tenant] start_delay` seconds. That wait is a guess, and unlike rungs 1–2
this container **cannot** do better: `requests` is not in the base image, so it
cannot poll RabbitMQ's management API, and `depends_on` does not reach across
compose projects to the tenant's chat UI.

If the guess loses, that tenant's chat UI stays blank with nothing logged.
`docker compose -f compose/example.compose.yml restart example` fixes it;
raising `start_delay` fixes it properly.

If you are *also* running `attach/listen.py` against the same tenant, set
`[myorg.tenant] start_scenario: false` here or pass `--no-scenario` there. Two
openers for one tenant is not fatal but it is confusing — see
[`tenancy.md`](tenancy.md#two-openers-one-tenant).

## Joining a deployment you built yourself

The same three things: a config file carrying the deployment's broker settings
and its tenant, the compose network name (`docker network ls`, or `docker
compose -p <project> ps` to find the project), and a tenant id. Nothing else in
`compose/example.compose.yml` changes.

If your deployment is single-tenant, leave `CLTL_TENANT` empty in the mounted
config and set `[myorg.tenant] start_scenario: false` — or, better, delete
`myorg.tenant` altogether, since a single-tenant deployment has a
`cltl-context` that can open the scenario itself.

If your deployment *does* know about your module — because you added a section
for it to the deployment's own configuration — then you are no longer a
third-party attachment, and you can mount the whole config directory over
`/cltl-example/config` the way every platform component does.
