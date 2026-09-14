#!/bin/bash
# Ephemeral integration infrastructure only; the frontend contains no monitoring core.
set -euo pipefail
cd "$(dirname "$0")/../.."
mkdir -p rust-ui-results
cleanup() {
    docker logs rust-ui-engine > rust-ui-results/engine.log 2>&1 || true
    docker logs rust-ui-web > rust-ui-results/web-startup.log 2>&1 || true
    docker cp rust-ui-web:/omd/sites/demo/var/log/thruk.log rust-ui-results/thruk.log >/dev/null 2>&1 || true
    docker rm -f rust-ui-web rust-ui-engine >/dev/null 2>&1 || true
    docker network rm rust-ui >/dev/null 2>&1 || true
}
trap cleanup EXIT
image="docker.io/consol/omd-labs-debian:latest"
docker pull "$image"
docker image inspect "$image" --format '{{json .RepoDigests}}' > rust-ui-results/frontend-image.json
docker build -f Containerfile.rust -t shinken-rs:ui .
docker network create rust-ui >/dev/null
docker run -d --name rust-ui-engine --network rust-ui --network-alias engine \
    -p 127.0.0.1::6557 shinken-rs:ui
docker run -d --name rust-ui-web --network rust-ui \
    -p 127.0.0.1::80 \
    -v "$PWD/rust/tests/thruk-ui/playbook.yml:/root/ansible_dropin/playbook.yml:ro" "$image"
port="$(docker port rust-ui-web 80/tcp | awk -F: '{print $NF}')"
engine_port="$(docker port rust-ui-engine 6557/tcp | awk -F: '{print $NF}')"
python3 rust/tests/thruk-ui-smoke.py "$port" "$engine_port" rust-ui-results
docker exec rust-ui-web su - demo -c 'thruk -V' > rust-ui-results/frontend-version.txt
docker exec rust-ui-web omd config demo show CORE | tee rust-ui-results/frontend-core.txt
test "$(docker exec rust-ui-web omd config demo show CORE)" = "none"
