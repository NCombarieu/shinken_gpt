#!/bin/bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
IMAGE=${SHINKEN_LAB_IMAGE:-localhost/shinken:integration}
NETWORK=${SHINKEN_LAB_NETWORK:-shinken-integration}
CONFIG_DIR=$(mktemp -d)
STATE_DIR=$(mktemp -d)
SSH_DIR=$(mktemp -d)
CONTAINERS=(lab-arbiter lab-scheduler lab-poller lab-reactionner lab-broker lab-receiver lab-http lab-sshtarget lab-passive-ssh)

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
            podman top "$container" >&2 || true
        done
        while IFS= read -r diagnostic_file; do
            echo "--- ${diagnostic_file#"$STATE_DIR"/} ---" >&2
            cat "$diagnostic_file" >&2 || true
        done < <(find "$STATE_DIR" -type f -print)
    fi
    for container in "${CONTAINERS[@]}"; do
        podman rm -f "$container" >/dev/null 2>&1 || true
    done
    podman network rm "$NETWORK" >/dev/null 2>&1 || true
    # Files chowned inside the user namespace are removed from inside it.
    podman unshare rm -rf "$CONFIG_DIR" "$STATE_DIR" "$SSH_DIR" 2>/dev/null \
        || rm -rf "$CONFIG_DIR" "$STATE_DIR" "$SSH_DIR"
    exit "$status"
}
trap cleanup EXIT

cp -a "$ROOT_DIR/etc/." "$CONFIG_DIR/"

# Addresses, modules_dir and the status web UI are adapted by the image
# entrypoint itself (SHINKEN_CONTAINER_DNS=1, SHINKEN_STATUS_WEBUI=1), exactly
# as in compose.yaml: only test-specific settings are changed here.
sed -i -E 's/^max_service_check_spread=.*/max_service_check_spread=0/' "$CONFIG_DIR/shinken.cfg"
sed -i -E 's/^max_host_check_spread=.*/max_host_check_spread=0/' "$CONFIG_DIR/shinken.cfg"

# --- SSH (doc/admin/recettes/linux-ssh.md, doc/admin/recettes/passif-ssh.md)
# Active: the poller's key ($SSHKEY$), restricted on the target by a forced
# command; made readable by the container user as documented.
ssh-keygen -q -t ed25519 -N "" -f "$CONFIG_DIR/ssh_keys/id_ed25519" -C lab-supervision
podman unshare chown 10001:10001 "$CONFIG_DIR/ssh_keys/id_ed25519" 2>/dev/null \
    || chmod 644 "$CONFIG_DIR/ssh_keys/id_ed25519"
sed -i -E 's/^\$SSHUSER\$=.*/$SSHUSER$=shinken/' "$CONFIG_DIR/resource.d/ssh.cfg"
chmod 755 "$SSH_DIR"
install -d -m 0755 "$SSH_DIR/target" "$SSH_DIR/client" "$CONFIG_DIR/passive"
install -m 0755 "$ROOT_DIR/contrib/checks/ssh/shinken-checks" "$SSH_DIR/target/shinken-checks"
install -m 0755 "$ROOT_DIR/integration/lab-sshtarget.sh" "$SSH_DIR/target/run-sshd.sh"
echo "restrict,command=\"/opt/sshtarget/shinken-checks\" $(cat "$CONFIG_DIR/ssh_keys/id_ed25519.pub")" \
    >"$SSH_DIR/target/authorized_keys"
# Passive: a client key bound to one Shinken host.
ssh-keygen -q -t ed25519 -N "" -f "$SSH_DIR/client/id_client" -C lab-client
chmod 644 "$SSH_DIR/client/id_client"
echo "environment=\"SHINKEN_PASSIVE_HOST=integration-passive\" $(cat "$SSH_DIR/client/id_client.pub")" \
    >"$CONFIG_DIR/passive/authorized_keys"

cat >"$CONFIG_DIR/commands/integration-lab.cfg" <<'EOF'
define command {
    command_name    integration-host
    command_line    /usr/local/bin/python /opt/shinken-integration/check_lab.py host $HOSTADDRESS$ /var/lib/shinken/integration-checks.log
}

define command {
    command_name    integration-http
    command_line    /usr/local/bin/python /opt/shinken-integration/check_lab.py http $HOSTADDRESS$ /var/lib/shinken/integration-checks.log
}

define command {
    command_name    integration-fail
    command_line    /usr/local/bin/python /opt/shinken-integration/check_lab.py fail $HOSTADDRESS$ /var/lib/shinken/integration-checks.log
}
EOF

cat >"$CONFIG_DIR/hosts/integration-lab.cfg" <<'EOF'
define host {
    use                 generic-host
    host_name           integration-sshtarget
    address             sshtarget
    check_command       integration-host
    check_interval      1
    retry_interval      1
    max_check_attempts  1
}

define host {
    use                 generic-host
    host_name           integration-passive
    address             lab-http
    check_command       integration-host
    check_interval      1
    retry_interval      1
    max_check_attempts  1
}

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

define host {
    use                 generic-host
    host_name           integration-broker
    alias               Podman integration broker target
    address             broker
    check_command       integration-host
    check_interval      1
    retry_interval      1
    max_check_attempts  1
}
EOF

cat >"$CONFIG_DIR/services/integration-lab.cfg" <<'EOF'
define service {
    use                 generic-service
    host_name           integration-sshtarget
    service_description Load via SSH
    check_command       check_by_ssh!load
    check_interval      1
    retry_interval      1
    max_check_attempts  1
}

define service {
    use                 generic-service
    host_name           integration-sshtarget
    service_description Forbidden via SSH
    check_command       check_by_ssh!reboot
    check_interval      1
    retry_interval      1
    max_check_attempts  1
}

define service {
    use                 passive-service
    host_name           integration-passive
    service_description Backup
}

define service {
    use                 generic-service
    host_name           integration-http
    service_description HTTP endpoint
    check_command       integration-http
    check_interval      1
    retry_interval      1
    max_check_attempts  1
}

define service {
    use                 generic-service
    host_name           integration-broker
    service_description DNS resolution
    check_command       integration-host
    check_interval      1
    retry_interval      1
    max_check_attempts  1
}

define service {
    use                 generic-service
    host_name           integration-http
    service_description Intentional critical
    check_command       integration-fail
    check_interval      1
    retry_interval      1
    max_check_attempts  1
}
EOF

cd "$ROOT_DIR"
podman build --format docker --tag "$IMAGE" --file Containerfile .
podman network create "$NETWORK" >/dev/null

for role in arbiter scheduler poller reactionner broker receiver; do
    install -d -m 0777 "$STATE_DIR/$role/data" "$STATE_DIR/$role/log"
done

common_args=(
    --network "$NETWORK"
    --security-opt no-new-privileges
    --cap-drop ALL
    -e SHINKEN_CONTAINER_DNS=1
    -e SHINKEN_STATUS_WEBUI=1
    -e TZ=Europe/Paris
    -v "$CONFIG_DIR:/etc/shinken:ro,Z"
    -v "$ROOT_DIR/integration:/opt/shinken-integration:ro,Z"
)

run_daemon() {
    local role=$1
    shift
    podman run -d --name "lab-$role" --network-alias "$role" \
        "${common_args[@]}" \
        -v "$STATE_DIR/$role/data:/var/lib/shinken:Z" \
        -v "$STATE_DIR/$role/log:/var/log/shinken:Z" \
        "$@" "$IMAGE" "$role" >/dev/null
}

podman run -d --name lab-http --network "$NETWORK" "$IMAGE" \
    shell -c 'python -m http.server 8000 --bind 0.0.0.0 --directory /usr/local/lib/shinken/libexec' >/dev/null

run_daemon scheduler
run_daemon poller
run_daemon reactionner
run_daemon broker -p 127.0.0.1:18080:8080 -p 127.0.0.1:15000:50000
run_daemon receiver

# A monitored Linux host: unprivileged sshd on port 22 + forced command.
podman run -d --name lab-sshtarget --network "$NETWORK" --network-alias sshtarget \
    --security-opt no-new-privileges --cap-drop ALL \
    --sysctl net.ipv4.ip_unprivileged_port_start=22 -e SSH_PORT=22 \
    -v "$SSH_DIR/target:/opt/sshtarget:ro" "$IMAGE" shell /opt/sshtarget/run-sshd.sh >/dev/null

# Passive receiver: no -v for /var/lib/shinken, so the image's VOLUME gives it
# a fresh anonymous volume (the lab's 0777 state dirs would make sshd's
# StrictModes reject authorized_keys).
podman run -d --name lab-passive-ssh --network-alias passive-ssh \
    "${common_args[@]}" -e SHINKEN_LIVESTATUS=broker:50000 "$IMAGE" passive-ssh >/dev/null

podman run --rm "${common_args[@]}" \
    -v "$STATE_DIR/arbiter/data:/var/lib/shinken:Z" \
    -v "$STATE_DIR/arbiter/log:/var/log/shinken:Z" \
    "$IMAGE" check
run_daemon arbiter

deadline=$((SECONDS + 120))
while (( SECONDS < deadline )); do
    all_running=1
    for container in "${CONTAINERS[@]}"; do
        if [[ $(podman inspect -f '{{.State.Running}}' "$container" 2>/dev/null || true) != true ]]; then
            all_running=0
            break
        fi
    done

    # Push a passive result over SSH, as a client would. Re-pushed every round
    # until the status shows it: "forwarded" only means accepted by Livestatus.
    if ! grep -q 'lab passive result' <<<"${status_json:-}"; then
        push_output=$(podman run --rm --network "$NETWORK" -v "$SSH_DIR/client:/opt/client:ro" "$IMAGE" \
            shell -c 'cp /opt/client/id_client /tmp/k && chmod 600 /tmp/k &&
                printf "integration-passive\tBackup\t1\tWARNING - lab passive result\n" |
                ssh -T -p 2222 -i /tmp/k -o BatchMode=yes -o StrictHostKeyChecking=accept-new \
                    -o UserKnownHostsFile=/tmp/kh shinken@passive-ssh' 2>&1 || true)
    fi

    markers=$(cat "$STATE_DIR/poller/data/integration-checks.log" 2>/dev/null || true)
    status_json=$(curl -fsS http://127.0.0.1:18080/api/status 2>/dev/null || true)
    dashboard=$(curl -fsS http://127.0.0.1:18080/ 2>/dev/null || true)
    livestatus=$(python3 "$ROOT_DIR/bin/shinken-healthcheck" --port 15000 --no-color 2>/dev/null || true)
    healthy=1
    unhealthy=""
    for role in scheduler poller reactionner broker receiver arbiter; do
        if ! health_output=$(podman exec "lab-$role" shinken-healthcheck --daemon auto 2>&1); then
            healthy=0
            unhealthy+="${role}(${health_output//[$'\n']/ }) "
        fi
    done

    # Record every unmet condition, so a timeout says which one blocked.
    pending=""
    (( all_running )) || pending+=" not-all-running"
    (( healthy )) || pending+=" healthcheck:${unhealthy}"
    grep -q 'integration-http' <<<"$livestatus" || pending+=" livestatus-report"
    grep -q '^host-ok lab-http ' <<<"$markers" || pending+=" marker:host-ok-lab-http"
    grep -q '^host-ok broker ' <<<"$markers" || pending+=" marker:host-ok-broker"
    grep -q '^http-ok lab-http 200$' <<<"$markers" || pending+=" marker:http-ok"
    grep -q '^critical-seen lab-http$' <<<"$markers" || pending+=" marker:critical-seen"
    for expected in integration-http integration-broker 'HTTP endpoint' 'DNS resolution' 'Intentional critical'; do
        grep -q "$expected" <<<"$status_json" || pending+=" status:${expected// /_}"
    done
    grep -q '<title>Shinken Status</title>' <<<"$dashboard" || pending+=" dashboard-title"
    ssh_status=$(python3 "$ROOT_DIR/integration/check_lab_status.py" <<<"${status_json:-{\}}" 2>&1) \
        || pending+=" ssh-checks"

    if [[ -z $pending ]]; then
        echo "Distributed Shinken integration and broker web UI succeeded."
        echo "$ssh_status"
        echo "$push_output"
        echo "$markers"
        echo "$status_json"
        podman ps --filter "network=${NETWORK}"
        exit 0
    fi
    sleep 2
done

echo "Integration checks and web status did not complete within 120 seconds." >&2
echo "Unmet conditions at the last round:${pending:- none recorded}" >&2
echo "--- SSH active / passive checks ---" >&2
echo "${ssh_status:-not evaluated}" >&2
echo "--- last passive push ---" >&2
echo "${push_output:-never attempted}" >&2
echo "--- livestatus report ---" >&2
echo "${livestatus:-empty}" >&2
echo "--- arbiter listening sockets (hex address:port, state 0A) ---" >&2
podman exec lab-arbiter sh -c 'grep " 0A " /proc/net/tcp /proc/net/tcp6' >&2 || true
exit 1
