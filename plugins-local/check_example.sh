#!/bin/sh
# Exemple de plugin maison : taux d'occupation d'un système de fichiers.
#   check_example.sh [-p CHEMIN] [-w SEUIL_WARNING] [-c SEUIL_CRITICAL]
# Sortie au format Nagios, code retour 0/1/2/3.

path=/var/lib/shinken
warn=80
crit=90

while getopts "p:w:c:h" opt; do
  case "$opt" in
    p) path=$OPTARG ;;
    w) warn=$OPTARG ;;
    c) crit=$OPTARG ;;
    *) echo "Usage: $0 [-p path] [-w warn%] [-c crit%]"; exit 3 ;;
  esac
done

used=$(df -P "$path" 2>/dev/null | awk 'NR == 2 { sub("%", "", $5); print $5 }')
case "$used" in
  ''|*[!0-9]*) echo "UNKNOWN - cannot read usage of $path"; exit 3 ;;
esac

perf="used=${used}%;${warn};${crit};0;100"
if [ "$used" -ge "$crit" ]; then
  echo "CRITICAL - $path ${used}% used|$perf"; exit 2
elif [ "$used" -ge "$warn" ]; then
  echo "WARNING - $path ${used}% used|$perf"; exit 1
fi
echo "OK - $path ${used}% used|$perf"
exit 0
