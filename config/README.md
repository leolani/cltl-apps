# config/ — generated, not tracked

This directory is empty until you populate it. This checkout is meant to be
dedicated to exactly one deployment (a server, a client/tenant, or a
standalone module) — see [`../doc/DEPLOYMENT.md`](../doc/DEPLOYMENT.md) — so
there is no single default config that would be correct for every checkout.

To configure this checkout, copy the template matching its role:

```bash
cp ../templates/server/config/* config/    # for servers/*
# or
cp ../templates/client/config/* config/    # for clients/*
```

(paths above are relative to this `config/` directory — run the `cp` from
the repository root instead, e.g. `cp templates/server/config/* config/`).

Then edit the copied `custom.config`/`clients.env`/`servers.env` for this
specific deployment (tenant id, ports, `CLTL_SERVER_HOST`, …) — see
`doc/DEPLOYMENT.md` for what to change for each scenario.

Nothing under here except this file and `.gitignore` is version-controlled:
a live deployment's tenant id, ports, and any local overrides have no
business in this repo's history, and `templates/` stays the single place a
platform-wide change (e.g. a topic rename) is made once.
