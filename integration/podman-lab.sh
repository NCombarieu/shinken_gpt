#!/bin/bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
IMAGE=${SHINKEN_LAB_IMAGE:-localhost/shinken:integration}
NETWORK=${SHINKEN_LAB_NETWORK:-shinken-integration}
DATA_VOLUME=${SHINKEN_LAB_DATA_VOLUME:-shinken-integration-data}
LOG_VOLUME=${SHINKEN_LAB_LOG_VOLUME:-shinken-integration-logs}
CONFIG_DIR=$(mktemp -d)
CONTAINERS=(lab-arbiter lab-scheduler lab-poller lab-reactionner lab-broker lab-receiver lab-http)

cleanup() {
    local status=$?
    if (( status != 0 )); then
        echo "--- container status ---" >&2
        podman ps -a --filter "network=${NETWORK}" >&2 || true
        echo "--- web status ---" >&2
        curl -fsS http://127.0.0.1:18080/api/status >&2 || true
        for container in "${CONTAINERS[@]}"; do
            echo "--- ${container} logs ---" >&2
            podman logs "$container" >&2 || true
        done
    fi
    for container in "${CONTAINERS[@]}"; do
        podman rm -f "$container" >/dev/null 2>&1 || true
    done
    podman network rm "$NETWORK" >/dev/null 2>&1 || true
    podman volume rm -f "$DATA_VOLUME" "$LOG_VOLUME" >/dev/null 2>&1 || true
    rm -rf "$CONFIG_DIR"
    exit "$status"
}
trap cleanup EXIT

cp -a "$ROOT_DIR/etc/." "$CONFIG_DIR/"

# Each daemon lives in its own container. The historical sample configuration
# assumes a monolithic localhost deployment, so give the arbiter routable
# service names on the dedicated Podman network.
sed -i -E 's/^([[:space:]]*address[[:space:]]+).*/\1scheduler/' "$CONFIG_DIR/schedulers/scheduler-master.cfg"
sed -i -E 's/^([[:space:]]*address[[:space:]]+).*/\1poller/' "$CONFIG_DIR/pollers/poller-master.cfg"
sed -i -E 's/^([[:space:]]*address[[:space:]]+).*/\1reactionner/' "$CONFIG_DIR/reactionners/reactionner-master.cfg"
sed -i -E 's/^([[:space:]]*address[[:space:]]+).*/\1broker/' "$CONFIG_DIR/brokers/broker-master.cfg"
sed -i -E 's/^([[:space:]]*address[[:space:]]+).*/\1receiver/' "$CONFIG_DIR/receivers/receiver-master.cfg"

# Image-provided modules live outside /var/lib/shinken so persistent data
# volumes cannot hide the application code.
sed -i -E 's#^modules_dir=.*#modules_dir=/usr/local/lib/shinken/modules#' "$CONFIG_DIR/shinken.cfg"
for daemon_ini in "$CONFIG_DIR"/daemons/*.ini; do
    sed -i -E 's#^modules_dir=.*#modules_dir=/usr/local/lib/shinken/modules#' "$daemon_ini"
done
sed -i -E 's/^([[:space:]]*)modules[[:space:]]*$/\1modules             status-webui/' "$CONFIG_DIR/brokers/broker-master.cfg"

# Integration checks should run immediately instead of being spread over the
# historical five-minute startup window.
sed -i -E 's/^max_service_check_spread=.*/max_service_check_spread=0/' "$CONFIG_DIR/shinken.cfg"
sed -i -E 's/^max_host_check_spread=.*/max_host_check_spread=0/' "$CONFIG_DIR/shinken.cfg"

cat >"$CONFIG_DIR/modules/status-webui.cfg" <<'EOF'
define module {
    module_name     status-webui
    module_type     status_webui
    host            0.0.0.0
    port            8080
}
EOF

cat >"$CONFIG_DIR/commands/integration-lab.cfg" <<'EOF'
define command {
    command_name    integration-host
    command_line    /usr/local/bin/python /opt/shinken-integration/check_lab.py host $HOSTADDRESS$ /var/lib/shinken/integration-checks.log
}

define command {
    command_name    integration-http
    command_line    /usr/local/bin/python /opt/shinken-integration/check_lab.py http $HOSTADDRESS$ /var/lib/shinken/integration-checks.log
}
EOF

cat >"$CONFIG_DIR/hosts/integration-lab.cfg" <<'EOF'
define host {
    use                 generic-host
    host_name           integration-http
    alias               Podman integration HTTP target
    address             lab-http
    check_command       integration-host
    check_interval      1
    retry_interval      1
    max_check_attempts  1
}
EOF

cat >"$CONFIG_DIR/services/integration-lab.cfg" <<'EOF'
define service {
    use                 generic-service
    host_name           integration-http
    service_description HTTP endpoint
    check_command       integration-http
    check_interval      1
    retry_interval      1
    max_check_attempts  1
}
EOF

cd "$ROOT_DIR"
podman build --tag "$IMAGE" --file Containerfile .
podman network create "$NETWORK" >/dev/null
podman volume create "$DATA_VOLUME" >/dev/null
podman volume create "$LOG_VOLUME" >/dev/null

common_args=(
    --network "$NETWORK"
    --security-opt no-new-privileges
    --cap-drop ALL
    -v "$CONFIG_DIR:/etc/shinken:ro,Z"
    -v "$ROOT_DIR/integration:/opt/shinken-integration:ro,Z"
    -v "$DATA_VOLUME:/var/lib/shinken:Z"
    -v "$LOG_VOLUME:/var/log/shinken:Z"
)

# A real target reachable only through the integration network.
podman run -d --name lab-http --network "$NETWORK" "$IMAGE" \
    shell -c 'python -m http.server 8000 --bind 0.0.0.0 --directory /usr/local/share/shinken/etc' >/dev/null

# Start satellites first. The arbiter will then distribute their configuration.
podman run -d --name lab-scheduler --network-alias scheduler "${common_args[@]}" "$IMAGE" scheduler >/dev/null
podman run -d --name lab-poller --network-alias poller "${common_args[@]}" "$IMAGE" poller >/dev/null
podman run -d --name lab-reactionner --network-alias reactionner "${common_args[@]}" "$IMAGE" reactionner >/dev/null
podman run -d --name lab-broker --network-alias broker -p 127.0.0.1:18080:8080 "${common_args[@]}" "$IMAGE" broker >/dev/null
podman run -d --name lab-receiver --network-alias receiver "${common_args[@]}" "$IMAGE" receiver >/dev/null

# Validate the exact configuration before starting the control plane.
podman run --rm "${common_args[@]}" "$IMAGE" shinken-arbiter -v -c /etc/shinken/shinken.cfg
podman run -d --name lab-arbiter --network-alias arbiter "${common_args[@]}" "$IMAGE" arbiter >/dev/null

# Prove that all long-running components stay alive, that an active host check
# and a real HTTP service check were dispatched to the poller, and that the
# broker received the resulting state and exposed it through the modern UI.
deadline=$((SECONDS + 120))
while (( SECONDS < deadline )); do
    all_running=1
    for container in lab-arbiter lab-scheduler lab-poller lab-reactionner lab-broker lab-receiver lab-http; do
        if [[ $(podman inspect -f '{{.State.Running}}' "$container" 2>/dev/null || true) != true ]]; then
            all_running=0
            break
        fi
    done

    markers=$(podman run --rm -v "$DATA_VOLUME:/var/lib/shinken:Z" "$IMAGE" \
        shell -c 'cat /var/lib/shinken/integration-checks.log 2>/dev/null || true')
    status_json=$(curl -fsS http://127.0.0.1:18080/api/status 2>/dev/null || true)
    dashboard=$(curl -fsS http://127.0.0.1:18080/ 2>/dev/null || true)

    if (( all_running )) \
        && grep -q '^host-ok lab-http ' <<<"$markers" \
        && grep -q '^http-ok lab-http 200$' <<<"$markers" \
        && grep -q 'integration-http' <<<"$status_json" \
        && grep -q 'HTTP endpoint' <<<"$status_json" \
        && grep -q '<title>Shinken Status</title>' <<<"$dashboard"; then
        echo "Distributed Shinken integration and broker web UI succeeded."
        echo "$markers"
        echo "$status_json"
        podman ps --filter "network=${NETWORK}"
        exit 0
    fi
    sleep 2
done

echo "Integration checks and web status did not complete within 120 seconds." >&2
exit 1
