#!/bin/sh
# Lance un démon Shinken en avant-plan.
#   entrypoint.sh arbiter|scheduler|poller|broker|reactionner|receiver [options]
#
# Variables : SHINKEN_CFG (arbiter seulement, défaut /etc/shinken/shinken.cfg),
# SHINKEN_LOG_LEVEL (défaut WARNING), SHINKEN_DAEMON_INI (surcharge le .ini).
set -eu

daemon="${1:-arbiter}"
shift || true

case "$daemon" in
  arbiter|scheduler|poller|broker|reactionner|receiver) ;;
  *) echo "démon inconnu : $daemon" >&2; exit 64 ;;
esac

ini="${SHINKEN_DAEMON_INI:-/opt/shinken/daemons/${daemon}d.ini}"
# Le .ini de l'image est générique ; le niveau de log se règle par variable.
rendered="/var/run/shinken/${daemon}d.ini"
sed "s/^log_level=.*/log_level=${SHINKEN_LOG_LEVEL}/" "$ini" > "$rendered"

if [ "$daemon" = arbiter ]; then
  [ -r "$SHINKEN_CFG" ] || { echo "configuration absente : $SHINKEN_CFG" >&2; exit 66; }
  exec python3 /opt/shinken/bin/shinken-arbiter -c "$SHINKEN_CFG" "$@"
fi
exec python3 "/opt/shinken/bin/shinken-${daemon}" -c "$rendered" "$@"
