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

## Joining a running deployment

`compose/example.compose.yml` attaches one service to a deployment that is
**already running**. It is not a deployment of its own.

With the deployment from [`deployment.md`](deployment.md) up:

```bash
make docker-ghcr-build

export CLTL_DEMO_CONFIG=$PWD/deployment/config
export CLTL_DEMO_NETWORK=cltl-example-deployment_cltl
docker compose -f compose/example.compose.yml -p cltl-example-module up
```

Two variables, and both are worth understanding rather than pasting.

**`CLTL_DEMO_NETWORK`** is the deployment's compose network, named
`<compose project>_cltl`. The deployment file pins its project name explicitly,
so this is stable wherever you run it from — without that pin, compose would
name the project after the file's *parent directory* (`deployment`) and the
network would be `deployment_cltl`. Confirm rather than assume:

```bash
docker network ls --format '{{.Name}}' | grep cltl
```

**`CLTL_DEMO_CONFIG`** is the directory holding the deployment's configuration.
The compose file mounts **one file** out of it — the deployment's
`default.config`, over this image's `config/custom.config`, where the platform's
loader reads it as an overlay on top of the `default.config` already baked into
the image. That is the asymmetry from the previous section in practice: the
image brings its own `[myorg.example]` section, the deployment brings the
broker connection, and the two are merged by the config loader.

Finally, every `$VAR` that the mounted config interpolates must be defined in
the container's environment, **even when empty** — an undefined one is passed
through as a literal string with only a warning, never a hard failure. See
[`tenancy.md`](tenancy.md) for what that specifically breaks.

## Joining a deployment you built yourself

The same two things: a config file carrying the deployment's broker settings,
and its compose network name (`docker network ls`, or `docker compose -p
<project> ps` to find the project). Nothing else in
`compose/example.compose.yml` changes.

If your deployment *does* know about your module — because you added a section
for it to the deployment's own configuration — then you are no longer a
third-party attachment, and you can mount the whole config directory over
`/cltl-example/config` the way every platform component does.
