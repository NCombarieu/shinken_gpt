FROM python:3.13-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libcurl4-openssl-dev libssl-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
COPY . .
RUN python -m pip install --upgrade pip build \
    && python -m build --wheel --outdir /dist

FROM python:3.13-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    SHINKEN_CONFIG=/etc/shinken

RUN apt-get update \
    && apt-get install -y --no-install-recommends libcurl4 tini \
        monitoring-plugins-basic monitoring-plugins-standard nagios-nrpe-plugin \
        nagios-snmp-plugins libnet-snmp-perl libcrypt-rijndael-perl libcrypt-des-perl libdigest-hmac-perl \
        snmp bind9-dnsutils liburiparser1 libldap2 \
        openssh-client openssh-server \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 shinken \
    && useradd --uid 10001 --gid shinken --home-dir /var/lib/shinken --create-home shinken \
    && install -d -o shinken -g shinken /etc/shinken /var/lib/shinken /var/log/shinken /run/shinken \
    && install -d -o shinken -g shinken /usr/local/lib/shinken/modules \
    && install -d /usr/local/lib/shinken/plugins \
    && rm -f /etc/ssh/ssh_host_*_key /etc/ssh/ssh_host_*_key.pub \
    && printf '%s\n' \
        '# Genere au demarrage du poller par shinken-entrypoint (cles copiees' \
        '# depuis /etc/shinken/ssh_keys, known_hosts). Voir doc/checks/ssh-actif.md' \
        'Include /tmp/shinken-ssh/config' \
        > /etc/ssh/ssh_config.d/shinken.conf

COPY --from=builder /dist/ /tmp/dist/
RUN python -m pip install /tmp/dist/*.whl && rm -rf /tmp/dist

COPY --chown=shinken:shinken etc/ /usr/local/share/shinken/etc/
COPY --chown=shinken:shinken modules/ /usr/local/lib/shinken/modules/
COPY --chmod=755 containers/entrypoint.sh /usr/local/bin/shinken-entrypoint
COPY --chmod=755 containers/shinken-passive-receive /usr/local/bin/shinken-passive-receive
COPY --chmod=755 containers/plugins/ /usr/local/lib/shinken/plugins/

USER 10001:10001
WORKDIR /var/lib/shinken
VOLUME ["/etc/shinken", "/var/lib/shinken", "/var/log/shinken"]
ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/shinken-entrypoint"]
CMD ["arbiter"]
