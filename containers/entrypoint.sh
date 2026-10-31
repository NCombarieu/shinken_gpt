#!/bin/sh
set -eu

role="${1:-arbiter}"
shift || true
config_root="${SHINKEN_CONFIG:-/etc/shinken}"
# Secrets are always read from the mounted configuration, never from the
# runtime copy made by prepare_container_config (which excludes them).
secrets_root="$config_root"

log() {
  echo "shinken-entrypoint: $*" >&2
}

prepare_container_config() {
  [ "${SHINKEN_CONTAINER_DNS:-0}" = "1" ] || return 0

  runtime_root="${SHINKEN_RUNTIME_CONFIG:-/tmp/shinken-config}"
  rm -rf "$runtime_root"
  mkdir -p "$runtime_root"
  # Secrets (cles SSH, certificats NRPE) are referenced by absolute
  # /etc/shinken/... paths and may legitimately be unreadable by some
  # daemons: never copy them, so one private key in 0600 cannot make every
  # container crash-loop on a failed copy.
  (cd "$config_root" && tar -cf - --exclude=./ssh_keys --exclude=./certs \
      --exclude=./passive --exclude=./secrets .) \
    | (cd "$runtime_root" && tar -xf -)
  # A git-ignored *.local.cfg (SNMPv3 passwords...) that the container cannot
  # read would silently vanish from the copy: say so.
  for local_cfg in "$config_root"/resource.d/*.local.cfg; do
    [ -e "$local_cfg" ] || continue
    [ -r "$local_cfg" ] || log "WARNING: $local_cfg is not readable by uid $(id -u):" \
      "its macros are not loaded (podman unshare chown $(id -u):$(id -g) <file>)"
  done

  # Container service names are resolvable through the Podman/Docker network,
  # unlike the historical monolithic 'localhost' addresses.
  sed -i -E 's/^([[:space:]]*address[[:space:]]+).*/\1scheduler/' "$runtime_root/schedulers/scheduler-master.cfg"
  sed -i -E 's/^([[:space:]]*address[[:space:]]+).*/\1poller/' "$runtime_root/pollers/poller-master.cfg"
  sed -i -E 's/^([[:space:]]*address[[:space:]]+).*/\1reactionner/' "$runtime_root/reactionners/reactionner-master.cfg"
  sed -i -E 's/^([[:space:]]*address[[:space:]]+).*/\1broker/' "$runtime_root/brokers/broker-master.cfg"
  sed -i -E 's/^([[:space:]]*address[[:space:]]+).*/\1receiver/' "$runtime_root/receivers/receiver-master.cfg"

  modules_dir="${SHINKEN_MODULES_DIR:-/usr/local/lib/shinken/modules}"
  sed -i -E "s#^modules_dir=.*#modules_dir=${modules_dir}#" "$runtime_root/shinken.cfg"
  for daemon_ini in "$runtime_root"/daemons/*.ini; do
    [ -f "$daemon_ini" ] || continue
    sed -i -E "s#^modules_dir=.*#modules_dir=${modules_dir}#" "$daemon_ini"
  done

  if [ "${SHINKEN_STATUS_WEBUI:-0}" = "1" ]; then
    mkdir -p "$runtime_root/modules"
    cat >"$runtime_root/modules/status-webui.cfg" <<'EOF'
define module {
    module_name     status-webui
    module_type     status_webui
    host            0.0.0.0
    port            8080
}
EOF
    sed -i -E 's/^([[:space:]]*)modules[[:space:]]*$/\1modules             status-webui/' \
      "$runtime_root/brokers/broker-master.cfg"
  fi

  config_root="$runtime_root"
}

# SSH client setup for check_by_ssh (poller only). Private keys dropped in
# /etc/shinken/ssh_keys are copied to a private runtime directory in 0600,
# owned by the container user, because ssh refuses keys that are group/world
# readable or owned by someone else -- which is what a bind mount from a
# rootless host usually looks like. /etc/ssh/ssh_config.d/shinken.conf
# (baked in the image) includes the generated config.
prepare_ssh_client() {
  keys_dir="${SHINKEN_SSH_KEYS:-${secrets_root}/ssh_keys}"
  ssh_runtime="${SHINKEN_SSH_RUNTIME:-/tmp/shinken-ssh}"
  rm -rf "$ssh_runtime"
  mkdir -p "$ssh_runtime"
  chmod 700 "$ssh_runtime"
  identities=""
  if [ -d "$keys_dir" ]; then
    for key in "$keys_dir"/*; do
      [ -f "$key" ] || continue
      case "$(basename "$key")" in
        *.pub|known_hosts|README*) continue ;;
      esac
      if [ ! -r "$key" ]; then
        log "WARNING: SSH key $key is not readable by uid $(id -u); run on the host:" \
          "podman unshare chown $(id -u):$(id -g) <file> (see doc/checks/ssh-actif.md)"
        continue
      fi
      grep -q 'PRIVATE KEY' "$key" 2>/dev/null || continue
      dest="$ssh_runtime/$(basename "$key")"
      cp "$key" "$dest"
      chmod 600 "$dest"
      identities="${identities}    IdentityFile \"${dest}\"
"
    done
  fi

  if [ -e "$keys_dir/known_hosts" ]; then
    # Pinned host keys. If the file is unreadable, keep strict checking (every
    # SSH check fails visibly) rather than silently trusting on first use.
    known_hosts="$keys_dir/known_hosts"
    strict="${SHINKEN_SSH_STRICT:-yes}"
    [ -r "$known_hosts" ] || log "WARNING: $known_hosts is not readable by uid $(id -u):" \
      "SSH checks will fail (podman unshare chown $(id -u):$(id -g) <file>)"
  else
    # No pinned known_hosts: trust on first use, remembered in the data volume.
    known_hosts="${SHINKEN_SSH_TOFU_FILE:-/var/lib/shinken/ssh_known_hosts}"
    strict="${SHINKEN_SSH_STRICT:-accept-new}"
    log "no $keys_dir/known_hosts: SSH host keys are trusted on first use ($known_hosts)"
  fi

  {
    echo "Host *"
    echo "    BatchMode yes"
    echo "    ConnectTimeout 10"
    echo "    IdentitiesOnly yes"
    printf '%s' "$identities"
    echo "    UserKnownHostsFile \"$known_hosts\""
    echo "    GlobalKnownHostsFile /dev/null"
    echo "    StrictHostKeyChecking $strict"
  } >"$ssh_runtime/config"
  chmod 600 "$ssh_runtime/config"
}

# Passive results pushed over SSH (doc/checks/ssh-passif.md): an
# unprivileged sshd that only ever runs shinken-passive-receive. Each key in
# authorized_keys is bound to one Shinken host through
# environment="SHINKEN_PASSIVE_HOST=<host>" on its line. That option is NOT
# passed through the environment (PermitUserEnvironment stays off, so a
# ~/.ssh/environment cannot override it): with ExposeAuthInfo, the receiver
# looks up the host of the key that actually authenticated. State lives in
# the container's own volume (compose: passive-ssh-data), not in the volume
# shared with the other daemons.
run_passive_sshd() {
  state_dir="${SHINKEN_PASSIVE_STATE:-/var/lib/shinken/passive-ssh}"
  runtime="${SHINKEN_PASSIVE_RUNTIME:-/tmp/shinken-sshd}"
  authorized="${SHINKEN_PASSIVE_AUTHORIZED_KEYS:-${secrets_root}/passive/authorized_keys}"
  port="${SHINKEN_PASSIVE_PORT:-2222}"
  livestatus="${SHINKEN_LIVESTATUS:-broker:50000}"
  case "$livestatus" in
    *[!A-Za-z0-9.:_-]*|"") log "ERROR: invalid SHINKEN_LIVESTATUS=$livestatus (expected host:port)"; exit 1 ;;
  esac
  mkdir -p "$state_dir" "$runtime"
  chmod 700 "$state_dir" "$runtime"
  [ -f "$state_dir/ssh_host_ed25519_key" ] \
    || ssh-keygen -q -t ed25519 -N "" -f "$state_dir/ssh_host_ed25519_key"
  if [ ! -r "$authorized" ]; then
    log "ERROR: $authorized is missing or unreadable; no client could connect"
    exit 1
  fi
  # sshd (StrictModes) checks the ownership and modes of AuthorizedKeysFile
  # and of every parent directory: use a private copy outside /tmp.
  cp "$authorized" "$state_dir/authorized_keys"
  chmod 600 "$state_dir/authorized_keys"
  cat >"$runtime/sshd_config" <<EOF
Port $port
HostKey $state_dir/ssh_host_ed25519_key
PidFile $runtime/sshd.pid
AuthorizedKeysFile $state_dir/authorized_keys
AllowUsers $(id -un)
PubkeyAuthentication yes
PasswordAuthentication no
KbdInteractiveAuthentication no
UsePAM no
PermitUserEnvironment no
PermitUserRC no
ExposeAuthInfo yes
ForceCommand /usr/local/bin/shinken-passive-receive --livestatus $livestatus --authorized-keys $state_dir/authorized_keys
DisableForwarding yes
PermitTTY no
PrintMotd no
LogLevel INFO
EOF
  exec /usr/sbin/sshd -D -e -f "$runtime/sshd_config"
}

prepare_container_config

case "$role" in
  passive-ssh)
    run_passive_sshd
    ;;
  arbiter)
    if [ "$#" -eq 0 ]; then
      set -- -c "${config_root}/shinken.cfg"
    fi
    exec shinken-arbiter "$@"
    ;;
  broker|poller|reactionner|receiver)
    [ "$role" = poller ] && prepare_ssh_client
    if [ "$#" -eq 0 ]; then
      set -- -c "${config_root}/daemons/${role}d.ini"
    fi
    exec "shinken-${role}" "$@"
    ;;
  scheduler)
    if [ "$#" -eq 0 ]; then
      set -- -c "${config_root}/daemons/schedulerd.ini"
    fi
    exec shinken-scheduler "$@"
    ;;
  shell)
    exec /bin/sh "$@"
    ;;
  *)
    exec "$role" "$@"
    ;;
esac
