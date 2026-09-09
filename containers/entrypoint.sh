#!/bin/sh
set -eu

role="${1:-arbiter}"
shift || true

case "$role" in
  arbiter)
    if [ "$#" -eq 0 ]; then
      set -- -c "${SHINKEN_CONFIG:-/etc/shinken}/shinken.cfg"
    fi
    exec shinken-arbiter "$@"
    ;;
  broker|poller|reactionner|receiver|scheduler)
    if [ "$#" -eq 0 ]; then
      set -- -c "${SHINKEN_CONFIG:-/etc/shinken}/daemons/${role}d.ini"
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
