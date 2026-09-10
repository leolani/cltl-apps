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
usually deleted or rewritten wholesale rather than edited (step 6).

## 2. Rename the packages

```bash
git mv src/myorg src/<your-namespace>
git mv src/<your-namespace>/example src/<your-namespace>/<your-module>
```

Then update every `from myorg.example ...` import — in the moved files
themselves, in `src/main.py`, and in `attach/inprocess.py`.

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

## 5. The build system

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

## 6. Replace the placeholder

- **`echo.py`** — your own logic, behind the `Example` ABC (rename that too;
  `api.py` is one method).
- **`tests/test_echo.py`** — tests for your logic.
- **`attach/`, `docs/`** — the teaching material. Keep them if you want the same
  onboarding story for people who copy *your* module; delete them if not.

## 7. Keep the rest

Especially `tests/test_service.py`. Its assertions about `source=`, about
`stop()` returning cleanly, and about empty topics being rejected are testing
**the platform's sharp edges**, not this template's placeholder logic. They stay
relevant no matter what your module ends up doing.

## Verify the rename worked

```bash
git grep -i myorg -- ':!docs' ':!README.md'   # should print nothing
make build && make build
make test
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
