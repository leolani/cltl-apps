# A stand-in for a fresh Ubuntu cloud VM: systemd as PID 1 and nothing else
# the installer would install itself, plus the login user `ubuntu` with
# passwordless sudo that cloud images come with. Run privileged, with the
# attached volume as a Docker volume, by scripts/test/run.sh.
ARG UBUNTU=24.04
FROM ubuntu:${UBUNTU}

ENV container=docker
RUN apt-get update \
    && apt-get install -y --no-install-recommends systemd systemd-sysv dbus ca-certificates curl sudo \
    && rm -rf /var/lib/apt/lists/* \
    && (id ubuntu > /dev/null 2>&1 || useradd -m -s /bin/bash ubuntu) \
    && echo 'ubuntu ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/ubuntu \
    && systemctl mask systemd-logind.service getty.target console-getty.service \
           systemd-networkd-wait-online.service systemd-resolved.service

STOPSIGNAL SIGRTMIN+3
CMD ["/sbin/init"]
