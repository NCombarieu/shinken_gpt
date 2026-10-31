# Image Shinken (Python 3) : un seul image pour les six daemons, le rôle est
# passé en argument (voir containers/entrypoint.sh).
#
#   podman build -t localhost/shinken:2.4.3 -t localhost/shinken:latest \
#       --build-arg VCS_REF=$(git rev-parse --short HEAD) .
#
# Base Debian 13 (trixie). Pour une construction reproductible, épinglez le
# digest : --build-arg PYTHON_IMAGE=docker.io/library/python:3.13-slim-trixie@sha256:...
ARG PYTHON_IMAGE=docker.io/library/python:3.13-slim-trixie

FROM ${PYTHON_IMAGE} AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

# Compilateur et en-têtes uniquement pour le cas où pip ne trouve pas de
# wheel binaire de pycurl pour l'architecture.
# Les versions apt suivent la base Debian épinglée (pas de pin par paquet).
# hadolint ignore=DL3008
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libcurl4-openssl-dev libssl-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
COPY pyproject.toml setup.py setup.cfg MANIFEST.in README.rst COPYING requirements.txt ./
COPY shinken/ shinken/
COPY bin/ bin/
# Toutes les dépendances sont construites ici en wheels : l'étape finale
# installe hors ligne (--no-index) et n'a pas besoin de compilateur.
RUN python -m pip install "build>=1.2,<2" \
    && python -m build --wheel --outdir /dist \
    && python -m pip wheel --wheel-dir /dist -r requirements.txt


FROM ${PYTHON_IMAGE} AS runtime

ARG SHINKEN_VERSION=2.4.3
ARG VCS_REF=unknown
ARG BUILD_DATE=unknown

LABEL org.opencontainers.image.title="Shinken" \
      org.opencontainers.image.description="Shinken monitoring daemons (Python 3): arbiter, scheduler, poller, reactionner, broker, receiver" \
      org.opencontainers.image.version="${SHINKEN_VERSION}" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.licenses="AGPL-3.0-or-later" \
      org.opencontainers.image.source="https://github.com/NCombarieu/shinken_gpt" \
      org.opencontainers.image.documentation="https://github.com/NCombarieu/shinken_gpt/tree/modernize/podman-python3/doc"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    SHINKEN_CONFIG=/etc/shinken \
    SHINKEN_MODULES_DIR=/usr/local/lib/shinken/modules

# Outils d'exploitation et plugins de supervision :
# - monitoring-plugins-basic/-standard : check_ping, check_icmp, check_http,
#   check_tcp, check_disk, check_dig, check_snmp, check_ldap, ... ($NAGIOSPLUGINSDIR$)
# - nagios-nrpe-plugin : check_nrpe ; openssh-client : check_by_ssh
# - nagios-snmp-plugins + libnet-snmp-perl + perl : check_snmp_*.pl (manubulon)
# - snmp, bind9-dnsutils, iputils-ping : snmpget, dig, ping utilisés par les plugins
# - procps (pkill/ps), tzdata (variable TZ), ca-certificates (TLS SMTP/HTTP)
# - libcurl4t64 : pycurl si la wheel a été compilée localement
# - tini : PID 1, récupère les processus zombies
# hadolint ignore=DL3008
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bind9-dnsutils \
        ca-certificates \
        iputils-ping \
        libcurl4t64 \
        libnet-snmp-perl \
        monitoring-plugins-basic \
        monitoring-plugins-standard \
        nagios-nrpe-plugin \
        nagios-snmp-plugins \
        openssh-client \
        perl \
        procps \
        snmp \
        tini \
        tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 shinken \
    && useradd --uid 10001 --gid shinken --home-dir /var/lib/shinken --no-create-home \
        --shell /usr/sbin/nologin shinken \
    && install -d -o shinken -g shinken -m 0750 /etc/shinken /var/lib/shinken /var/log/shinken /run/shinken \
    && install -d -m 0755 /usr/local/lib/shinken /usr/local/lib/shinken/plugins-local

COPY --from=builder /dist/ /tmp/dist/
# Installation hors ligne des wheels construites ci-dessus (versions figées).
# hadolint ignore=DL3013
RUN python -m pip install --no-index --find-links /tmp/dist shinken \
    && rm -rf /tmp/dist

# Code en lecture seule pour l'utilisateur shinken (propriétaire root).
# - modules/ : modules des daemons (SHINKEN_MODULES_DIR, modules_dir des .ini)
# - libexec/ : scripts fournis par Shinken ($PLUGINSDIR$), dont notify_by_email.py
# - cli/     : commandes de l'outil « shinken »
# La configuration (etc/) n'est PAS copiée : elle est montée sur /etc/shinken.
COPY modules/ /usr/local/lib/shinken/modules/
COPY libexec/ /usr/local/lib/shinken/libexec/
COPY cli/ /usr/local/lib/shinken/cli/
COPY --chmod=0755 containers/entrypoint.sh /usr/local/bin/shinken-entrypoint

USER 10001:10001
WORKDIR /var/lib/shinken
VOLUME ["/var/lib/shinken", "/var/log/shinken"]

# Vérifie que le daemon répond réellement sur son port (GET /ping) ; le rôle
# est déduit de la ligne de commande du conteneur.
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD ["shinken-healthcheck", "--daemon", "auto", "--timeout", "5"]

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/shinken-entrypoint"]
CMD ["arbiter"]
