#!/bin/sh
# Plugin déterministe de la recette e2e.
#   check_state.sh <fichier d'état> <nom> <journal>
# Lit 0/1/2/3 dans le fichier d'état (0 par défaut), journalise l'exécution
# dans <journal> et répond au format Nagios.
state=$(cat "$1" 2>/dev/null || echo 0)
echo "$(date +%s) $2 $state" >> "$3"
case "$state" in
  0) echo "OK - $2 is fine|value=0;1;2" ;;
  1) echo "WARNING - $2 is degraded|value=1;1;2" ;;
  2) echo "CRITICAL - $2 is broken|value=2;1;2" ;;
  *) echo "UNKNOWN - $2 state '$state'"; state=3 ;;
esac
exit "$state"
