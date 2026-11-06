# A stand-in for a fresh Ubuntu cloud VM: systemd as PID 1 and nothing else
# the installer would install itself. Run privileged, with its own
# /var/lib/docker volume, by scripts/test/run.sh.
ARG UBUNTU=24.04
FROM ubuntu:${UBUNTU}

ENV container=docker
RUN apt-get update \
    && apt-get install -y --no-install-recommends systemd systemd-sysv dbus ca-certificates curl \
    && rm -rf /var/lib/apt/lists/* \
    && systemctl mask systemd-logind.service getty.target console-getty.service \
           systemd-networkd-wait-online.service systemd-resolved.service

STOPSIGNAL SIGRTMIN+3
CMD ["/sbin/init"]
