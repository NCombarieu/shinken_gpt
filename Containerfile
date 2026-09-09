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
    && apt-get install -y --no-install-recommends libcurl4 nagios-plugins-basic tini \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 shinken \
    && useradd --uid 10001 --gid shinken --home-dir /var/lib/shinken --create-home shinken \
    && install -d -o shinken -g shinken /etc/shinken /var/lib/shinken /var/log/shinken /run/shinken

COPY --from=builder /dist/ /tmp/dist/
RUN python -m pip install /tmp/dist/*.whl && rm -rf /tmp/dist
COPY --chown=shinken:shinken etc/ /usr/local/share/shinken/etc/
COPY --chmod=755 containers/entrypoint.sh /usr/local/bin/shinken-entrypoint

USER 10001:10001
WORKDIR /var/lib/shinken
VOLUME ["/etc/shinken", "/var/lib/shinken", "/var/log/shinken"]
ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/shinken-entrypoint"]
CMD ["arbiter"]
