#!/bin/sh
set -eu

role="${1:-arbiter}"
shift || true
config_root="${SHINKEN_CONFIG:-/etc/shinken}"

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
