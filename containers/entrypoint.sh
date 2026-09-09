#!/bin/sh
set -eu

role="${1:-arbiter}"
shift || true
config_root="${SHINKEN_CONFIG:-/etc/shinken}"

case "$role" in
  arbiter)
    if [ "$#" -eq 0 ]; then
      echo "arbiter requires one or more -c configuration files" >&2
      echo "example: arbiter -c ${config_root}/shinken-specific.cfg" >&2
      exit 64
    fi
    exec shinken-arbiter "$@"
    ;;
  broker|poller|reactionner|receiver|scheduler)
    if [ "$#" -eq 0 ]; then
      set -- -c "${config_root}/daemons/${role}d.ini.in"
    fi
    exec "shinken-${role}" "$@"
    ;;
  shell)
    exec /bin/sh "$@"
    ;;
  *)
    exec "$role" "$@"
    ;;
esac
