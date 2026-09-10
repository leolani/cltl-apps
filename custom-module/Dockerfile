# syntax = docker/dockerfile:1.4

ARG base_image=ghcr.io/leolani/cltl-base:latest
FROM ${base_image}

LABEL org.opencontainers.image.source="https://github.com/leolani/cltl-example"
LABEL org.opencontainers.image.description="Template module for attaching custom processing to a Leolani deployment"
LABEL org.opencontainers.image.licenses="MIT"

COPY --from=leolani . /leolani/

WORKDIR /cltl-example
# requirements.docker.txt, not requirements.txt: the image resolves entirely
# from /leolani (the offline first-party sdist registry) plus whatever the
# base image already has preinstalled (kombu, Flask, Werkzeug — see
# cltl-requirements/requirements.base.txt). `pytest` and `requests` are
# third-party packages this component's own distribution does not need
# (test-only, and attach/-only respectively) and neither is preinstalled in
# the base image, so `--no-index` cannot resolve them here. Same split
# cltl-vad uses, for the same reason — see that component's
# requirements.docker.txt.
COPY setup.py requirements.docker.txt README.md VERSION ./
COPY src ./src

RUN pip install --no-index --no-build-isolation --find-links=/leolani -r requirements.docker.txt && \
    rm -rf /leolani && \
    find /usr/local/lib/python3.10 -type d -name __pycache__ -exec rm -rf {} +

# Every other component's image ships NO config/ at all — a deployment bind-
# mounts its own generated directory over /cltl-<name>/config
# (integration/compose/docker-compose.yml), because the deployment already
# knows about that module and generates a matching [cltl.<name>] section.
# A deployment built without this template in mind has no such section, so
# ExampleContainer would raise `ValueError: No configuration for myorg.example`
# the moment it started. Carrying config/default.config in the image is what
# lets compose/example.compose.yml mount only a single custom.config *file*
# over it instead of a whole directory — see docs/docker.md.
COPY config ./config

HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["python", "src/main.py"]
