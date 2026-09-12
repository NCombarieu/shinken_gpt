#!/bin/sh
set -eu

role="${1:-arbiter}"
shift || true
config_root="${SHINKEN_CONFIG:-/etc/shinken}"

prepare_container_config() {
  [ "${SHINKEN_CONTAINER_DNS:-0}" = "1" ] || return 0

  runtime_root="${SHINKEN_RUNTIME_CONFIG:-/tmp/shinken-config}"
  rm -rf "$runtime_root"
  mkdir -p "$runtime_root"
  cp -R "${config_root}/." "$runtime_root/"

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

prepare_container_config

case "$role" in
  arbiter)
    if [ "$#" -eq 0 ]; then
      set -- -c "${config_root}/shinken.cfg"
    fi
    exec shinken-arbiter "$@"
    ;;
  broker|poller|reactionner|receiver)
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
