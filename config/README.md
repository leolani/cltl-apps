# config/ — generated, not tracked

This directory is empty until you populate it. Every module in this checkout
bind-mounts the same three files from here, so what is in this directory is
what decides which deployment this checkout is — see
[`../doc/DEPLOYMENT.md`](../doc/DEPLOYMENT.md).

Populate it with the shared baseline plus exactly one role:

```bash
cp templates/common/config/* templates/standalone/config/* config/   # everything, one machine, no tenant
# or
cp templates/common/config/* templates/server/config/* config/       # the shared, untenanted half
# or
cp templates/common/config/* templates/client/config/* config/       # one tenant's user-facing half
```

(run these from the repository root, not from inside `config/`)

That leaves four files here:

| File | What it is |
|---|---|
| `default.config` | The platform baseline, identical for every role. Change it only for a platform-wide default, like a topic name |
| `logging.config` | Log levels and formatting, identical for every role |
| `custom.config` | **What makes this checkout its role** — the handful of keys that differ, plus anything specific to this one deployment (tenant id, where the server is) |
| `<role>.env` | The values Compose needs before any container exists: image tag, published ports, project name |

The role lives in `custom.config`, not in which modules you happen to run:
`templates/server/config/custom.config` and
`templates/client/config/custom.config` differ from the standalone baseline
in about six keys each, and reading those two files side by side is the
shortest description of what "server" and "client" actually mean here.

Nothing under this directory except this file and `.gitignore` is
version-controlled: a live deployment's tenant id, ports and local overrides
have no business in this repository's history, and `templates/` stays the one
place a platform-wide change is made.
