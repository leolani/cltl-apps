# Making it yours

Turning the template into your own module. Mechanical, in this order — later
steps depend on earlier ones.

Two names change throughout: **`myorg`**, your organisation's namespace, and
**`example`**, this module's name.

A note on the namespace before you pick one: it must **not** be `cltl`. That
namespace belongs to the platform's own distributions, and a third-party module
that squats in it will eventually collide with a package someone else installs.
Use your own — that is what makes your module yours rather than a fork.

## 1. See what you are changing

```bash
git grep -l 'myorg\|example\|Example' -- ':!docs' ':!README.md'
```

`docs/` and the README describe the *template*, not your module; they are
usually deleted or rewritten wholesale rather than edited (step 7).

## 2. Rename the packages

```bash
git mv src/myorg src/<your-namespace>
git mv src/<your-namespace>/example src/<your-namespace>/<your-module>
```

Then update every `from myorg.example ...` import — in the moved files
themselves, in `src/main.py`, and in `attach/inprocess.py`.

`src/<your-namespace>/tenant/` moves with the namespace but keeps its own name —
or disappears entirely, which is step 5 below. If you keep it, its imports need
the same treatment.

## 3. `setup.py`

- `name='<your-namespace>.<your-module>'`
- `find_namespace_packages(include=['<your-namespace>.*'], where='src')` —
  note the `.*`, and see
  [`component.md`](component.md#packaging) for why bare `<your-namespace>`
  must not be in that list
- `url`, `author`, `author_email`, `description`

## 4. The config section

Rename `[myorg.example]` in `config/default.config` and
`config/custom.config.example`, and update the matching
`config_manager.get_config("myorg.example")` in your service.

`[myorg.tenant]` renames the same way if you keep it — but read the next step
first.

## 5. Decide whether to delete `myorg.tenant`

**Usually: delete it.** It is not custom functionality and it is not an example
to follow. It exists because this template's deployment has no `cltl-context`,
so nothing else can open a tenant's scenario. Yours probably does.

Delete it when your deployment runs a `cltl-context` per tenant, or is
single-tenant:

```bash
git rm -r src/myorg/tenant tests/test_scenario.py tests/test_tenant_service.py
```

then drop `TenantContainer` from `src/main.py`'s bases and its import, remove
the `[myorg.tenant]` section from `config/default.config`, and delete
`TenantContainerLifecycleTest` and `_InProcessTenantContainer` from
`tests/test_container.py`.

Nothing in `myorg.example` refers to any of it — that is the property the
separation exists to give you, and it is why this is a clean deletion rather
than an unpicking. [`tenancy.md`](tenancy.md) has the full reasoning.

**Keep it** only if you are genuinely deploying into a multi-tenant setup where
the tenant side has no `cltl-context` of its own. In that case rename its config
section along with the rest, and read
[`tenancy.md`](tenancy.md#two-openers-one-tenant) before running more than one
opener per tenant.

## 6. The build system

In `makefile`:

- **`artifact_name`** — must match what your distribution name actually
  normalises to on disk. Rebuild once and look at the sdist that appears; the
  comment in the makefile explains why this cannot just be computed.
- **`ghcr_registry`** — your own registry, e.g. `ghcr.io/<your-org>`. Change
  this before your first `docker` target, so a stray push cannot reach
  someone else's namespace.
- **`docker_base`** — leave it. It is the platform's base image, not the
  template's.

In `Dockerfile`: `WORKDIR /cltl-example` → `WORKDIR /cltl-<your-module>`, plus
the two `LABEL` lines.

In `compose/example.compose.yml`: the service name, the image reference, and
the container-side path of the volume mount — which must match the new
`WORKDIR`.

## 7. Replace the placeholder

- **`echo.py`** — your own logic, behind the `Example` ABC (rename that too;
  `api.py` is one method).
- **`tests/test_echo.py`** — tests for your logic.
- **`attach/`, `docs/`** — the teaching material. Keep them if you want the same
  onboarding story for people who copy *your* module; delete them if not.

## 8. Keep the rest

Especially `tests/test_service.py`. Its assertions about `source=`, about
`stop()` returning cleanly, and about empty topics being rejected are testing
**the platform's sharp edges**, not this template's placeholder logic. They stay
relevant no matter what your module ends up doing.

`tests/test_tenancy.py` too, even in a single-tenant deployment: it pins the
two once-only warnings that are the only thing standing between a misconfigured
bus and total silence.

## Verify the rename worked

```bash
git grep -i myorg -- ':!docs' ':!README.md'   # should print nothing
make build && make build
make test
```

`make` needs this template inside a `cltl-dev` checkout — see
[`gotchas.md`](gotchas.md#there-is-no-makefile). Without one, the unit tests
still run on their own:

```bash
python3.10 -m venv .venv && . .venv/bin/activate
pip install -r requirements.notebook.txt pytest
PYTHONPATH=.:src python -m pytest tests
```

A rename that has not been built and tested is not finished — the failure mode
is a half-renamed namespace, which does not show up until import time.

## Optional next steps

- **An HTTP endpoint** — return a memoized Flask app from the service's `app`
  property instead of `None`; `cltl-monitoring` in the platform is the worked
  example.
- **Being composable by a deployment** rather than only attached from outside —
  a deployment needs an entry in its own module registry naming your
  container class as `"<your-namespace>.<your-module>.container:YourContainer"`.
