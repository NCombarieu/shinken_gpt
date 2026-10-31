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

sed -i -E 's/^([[:space:]]*address[[:space:]]+).*/\1scheduler/' "$CONFIG_DIR/schedulers/scheduler-master.cfg"
sed -i -E 's/^([[:space:]]*address[[:space:]]+).*/\1poller/' "$CONFIG_DIR/pollers/poller-master.cfg"
sed -i -E 's/^([[:space:]]*address[[:space:]]+).*/\1reactionner/' "$CONFIG_DIR/reactionners/reactionner-master.cfg"
sed -i -E 's/^([[:space:]]*address[[:space:]]+).*/\1broker/' "$CONFIG_DIR/brokers/broker-master.cfg"
sed -i -E 's/^([[:space:]]*address[[:space:]]+).*/\1receiver/' "$CONFIG_DIR/receivers/receiver-master.cfg"

sed -i -E 's#^modules_dir=.*#modules_dir=/usr/local/lib/shinken/modules#' "$CONFIG_DIR/shinken.cfg"
for daemon_ini in "$CONFIG_DIR"/daemons/*.ini; do
    sed -i -E 's#^modules_dir=.*#modules_dir=/usr/local/lib/shinken/modules#' "$daemon_ini"
done
sed -i -E 's/^([[:space:]]*)modules[[:space:]]*$/\1modules             status-webui/' "$CONFIG_DIR/brokers/broker-master.cfg"

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

define command {
    command_name    integration-fail
    command_line    /usr/local/bin/python /opt/shinken-integration/check_lab.py fail $HOSTADDRESS$ /var/lib/shinken/integration-checks.log
}
EOF

# --- SSH material (doc/checks/ssh-actif.md, doc/checks/ssh-passif.md) -------
# Active: the poller's key, restricted on the target by a forced command.
ssh-keygen -q -t ed25519 -N "" -f "$CONFIG_DIR/ssh_keys/lab_monitoring" -C lab-monitoring
# Make the key readable by the container user, as documented. Rootless
# podman: chown inside the user namespace; otherwise fall back to 0644 (the
# poller copies keys to a private 0600 file anyway).
podman unshare chown 10001:10001 "$CONFIG_DIR/ssh_keys/lab_monitoring" 2>/dev/null \
    || chmod 644 "$CONFIG_DIR/ssh_keys/lab_monitoring"
chmod 755 "$SSH_DIR"
install -d -m 0755 "$SSH_DIR/target" "$SSH_DIR/client" "$SSH_DIR/www" "$CONFIG_DIR/passive"
install -m 0755 "$ROOT_DIR/contrib/checks/ssh/shinken-checks" "$SSH_DIR/target/shinken-checks"
install -m 0755 "$ROOT_DIR/integration/lab-sshtarget.sh" "$SSH_DIR/target/run-sshd.sh"
echo "command=\"/opt/sshtarget/shinken-checks\",no-port-forwarding,no-X11-forwarding,no-agent-forwarding,no-pty $(cat "$CONFIG_DIR/ssh_keys/lab_monitoring.pub")" \
    >"$SSH_DIR/target/authorized_keys"
# Passive: a client key bound to one Shinken host.
ssh-keygen -q -t ed25519 -N "" -f "$SSH_DIR/client/id_client" -C lab-client
chmod 644 "$SSH_DIR/client/id_client"
echo "environment=\"SHINKEN_PASSIVE_HOST=integration-passive\" $(cat "$SSH_DIR/client/id_client.pub")" \
    >"$CONFIG_DIR/passive/authorized_keys"
echo '{"status": "UP", "queue": {"pending": 3}}' >"$SSH_DIR/www/health.json"

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

define host {
    use                 linux-ssh
    host_name           integration-sshtarget
    address             sshtarget
    _SSH_USER           shinken
    _SSH_PORT           2200
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
    service_description API health
    check_command       check_json_api_expect!http://lab-http:8000/health.json!status!UP
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
podman build --tag "$IMAGE" --file Containerfile .
podman network create "$NETWORK" >/dev/null

for role in arbiter scheduler poller reactionner broker receiver; do
    install -d -m 0777 "$STATE_DIR/$role/data" "$STATE_DIR/$role/log"
done

common_args=(
    --network "$NETWORK"
    --security-opt no-new-privileges
    --cap-drop ALL
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

podman run -d --name lab-http --network "$NETWORK" \
    -v "$SSH_DIR/www:/srv/www:ro,z" "$IMAGE" \
    shell -c 'python -m http.server 8000 --bind 0.0.0.0 --directory /srv/www' >/dev/null

# A monitored Linux host: unprivileged sshd + forced-command dispatcher.
podman run -d --name lab-sshtarget --network "$NETWORK" --network-alias sshtarget \
    --security-opt no-new-privileges --cap-drop ALL \
    -v "$SSH_DIR/target:/opt/sshtarget:ro,z" "$IMAGE" shell /opt/sshtarget/run-sshd.sh >/dev/null

run_daemon scheduler
run_daemon poller
run_daemon reactionner
run_daemon broker -p 127.0.0.1:18080:8080
run_daemon receiver
# Passive receiver: its own anonymous volume for /var/lib/shinken (the lab's
# 0777 state dirs would make sshd's StrictModes reject authorized_keys).
podman run -d --name lab-passive-ssh --network-alias passive-ssh \
    "${common_args[@]}" -e SHINKEN_LIVESTATUS=broker:50000 "$IMAGE" passive-ssh >/dev/null

podman run --rm "${common_args[@]}" \
    -v "$STATE_DIR/arbiter/data:/var/lib/shinken:Z" \
    -v "$STATE_DIR/arbiter/log:/var/log/shinken:Z" \
    "$IMAGE" shinken-arbiter -v -c /etc/shinken/shinken.cfg
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

    # Push a passive result over SSH, as a client would; retried until the
    # receiver can see the service in Livestatus (configuration dispatched).
    if [[ ${passive_pushed:-0} != 1 ]]; then
        push_output=$(podman run --rm --network "$NETWORK" -v "$SSH_DIR/client:/opt/client:ro,z" "$IMAGE" \
            shell -c 'cp /opt/client/id_client /tmp/k && chmod 600 /tmp/k &&
                printf "integration-passive\tBackup\t1\tWARNING - lab passive result\n" |
                ssh -T -p 2222 -i /tmp/k -o BatchMode=yes -o StrictHostKeyChecking=accept-new \
                    -o UserKnownHostsFile=/tmp/kh shinken@passive-ssh' 2>&1 || true)
        grep -q 'forwarded=1 rejected=0' <<<"$push_output" && passive_pushed=1
    fi

    markers=$(cat "$STATE_DIR/poller/data/integration-checks.log" 2>/dev/null || true)
    status_json=$(curl -fsS http://127.0.0.1:18080/api/status 2>/dev/null || true)
    dashboard=$(curl -fsS http://127.0.0.1:18080/ 2>/dev/null || true)

    if (( all_running )) \
        && grep -q '^host-ok lab-http ' <<<"$markers" \
        && grep -q '^host-ok broker ' <<<"$markers" \
        && grep -q '^http-ok lab-http 200$' <<<"$markers" \
        && grep -q '^critical-seen lab-http$' <<<"$markers" \
        && grep -q 'integration-http' <<<"$status_json" \
        && grep -q 'integration-broker' <<<"$status_json" \
        && grep -q 'HTTP endpoint' <<<"$status_json" \
        && grep -q 'DNS resolution' <<<"$status_json" \
        && grep -q 'Intentional critical' <<<"$status_json" \
        && grep -q '<title>Shinken Status</title>' <<<"$dashboard" \
        && python3 "$ROOT_DIR/integration/check_lab_status.py" <<<"$status_json" >/dev/null; then
        echo "Distributed Shinken integration and broker web UI succeeded."
        python3 "$ROOT_DIR/integration/check_lab_status.py" <<<"$status_json"
        echo "$push_output"
        echo "$markers"
        echo "$status_json"
        podman ps --filter "network=${NETWORK}"
        exit 0
    fi
    sleep 2
done

echo "Integration checks and web status did not complete within 120 seconds." >&2
echo "--- last passive push ---" >&2
echo "${push_output:-never attempted}" >&2
echo "--- check types ---" >&2
python3 "$ROOT_DIR/integration/check_lab_status.py" <<<"${status_json:-{\}}" >&2 || true
exit 1
