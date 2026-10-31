#!/bin/sh
# Point d'entrée de l'image Shinken.
#
# Usage : shinken-entrypoint <rôle> [options du daemon]
#   rôle : arbiter | scheduler | poller | reactionner | broker | receiver
#          check  (valide la configuration : shinken-arbiter -v, puis sort)
#          shell  (ouvre un /bin/sh)   ou toute autre commande, exécutée telle quelle.
#
# La configuration montée (SHINKEN_CONFIG, /etc/shinken par défaut) n'est
# JAMAIS modifiée. Quand SHINKEN_CONTAINER_DNS=1 (cas de compose.yaml et des
# quadlets), elle est copiée dans SHINKEN_RUNTIME_CONFIG (/tmp/shinken-config)
# et la COPIE est adaptée au réseau des conteneurs :
#
#  1. address des satellites : dans chaque bloc « define scheduler|poller|
#     reactionner|broker|receiver » des fichiers *.cfg de la configuration,
#     une adresse « localhost » ou « 127.0.0.1 » est remplacée par le nom DNS
#     du conteneur : le rôle pour les daemons « <rôle>-master » (scheduler,
#     poller, ...), sinon le nom du daemon lui-même (poller_name poller-2 ->
#     address poller-2 : nommez le service compose comme le daemon).
#     Une adresse explicite (nom ou IP) n'est jamais touchée.
#  2. modules_dir de shinken.cfg et des daemons/*.ini est forcé à
#     SHINKEN_MODULES_DIR (/usr/local/lib/shinken/modules), où l'image installe
#     les modules.
#  3. si SHINKEN_STATUS_WEBUI=1 : modules/status-webui.cfg est créé s'il
#     n'existe pas (écoute 0.0.0.0:8080), et status-webui est ajouté à la ligne
#     « modules » de brokers/broker-master.cfg s'il n'y figure pas.
#
# Pour voir exactement ce qui tourne :
#   podman exec <conteneur> diff -ru /etc/shinken /tmp/shinken-config
set -eu

role="${1:-arbiter}"
[ "$#" -gt 0 ] && shift
config_root="${SHINKEN_CONFIG:-/etc/shinken}"

rewrite_addresses() {
  # $1 = fichier .cfg ; réécrit en place (dans la copie) les address par défaut.
  awk '
    function flush(   i, line, target) {
      target = ""
      if (kind != "" && name != "") {
        target = (name == kind "-master") ? kind : name
      }
      for (i = 1; i <= n; i++) {
        line = buf[i]
        if (target != "" && line ~ /^[[:space:]]*address[[:space:]]+(localhost|127\.0\.0\.1)([[:space:]]|;|$)/) {
          sub(/(localhost|127\.0\.0\.1)/, target, line)
        }
        print line
      }
      n = 0; kind = ""; name = ""; inblock = 0
    }
    /^[[:space:]]*define[[:space:]]+(scheduler|poller|reactionner|broker|receiver)[[:space:]]*\{?/ {
      if (inblock) flush()
      inblock = 1
      kind = $2; sub(/\{.*/, "", kind)
    }
    inblock {
      buf[++n] = $0
      if ($1 == kind "_name") name = $2
      if ($0 ~ /^[[:space:]]*\}/) flush()
      next
    }
    { print }
    END { if (inblock) flush() }
  ' "$1" > "$1.tmp" && mv "$1.tmp" "$1"
}

prepare_container_config() {
  [ "${SHINKEN_CONTAINER_DNS:-0}" = "1" ] || return 0

  runtime_root="${SHINKEN_RUNTIME_CONFIG:-/tmp/shinken-config}"
  rm -rf "$runtime_root"
  mkdir -p "$runtime_root"
  cp -R "${config_root}/." "$runtime_root/"

  # 1. Adresses des satellites
  for dir in schedulers pollers reactionners brokers receivers; do
    [ -d "$runtime_root/$dir" ] || continue
    find "$runtime_root/$dir" -type f -name '*.cfg' | while IFS= read -r cfg; do
      rewrite_addresses "$cfg"
    done
  done

  # 2. modules_dir
  modules_dir="${SHINKEN_MODULES_DIR:-/usr/local/lib/shinken/modules}"
  for file in "$runtime_root/shinken.cfg" "$runtime_root"/daemons/*.ini; do
    [ -f "$file" ] || continue
    sed -i -E "s#^([[:space:]]*modules_dir[[:space:]]*=).*#\1${modules_dir}#" "$file"
  done

  # 3. Mini interface web de statut du broker
  if [ "${SHINKEN_STATUS_WEBUI:-0}" = "1" ]; then
    mkdir -p "$runtime_root/modules"
    if ! grep -rqs 'module_name[[:space:]]\{1,\}status-webui' "$runtime_root/modules"; then
      cat >"$runtime_root/modules/status-webui.cfg" <<'EOF'
define module {
    module_name     status-webui
    module_type     status_webui
    host            0.0.0.0
    port            8080
}
EOF
    fi
    broker_cfg="$runtime_root/brokers/broker-master.cfg"
    if [ -f "$broker_cfg" ] && ! grep -Eq '^[[:space:]]*modules[[:space:]].*status-webui' "$broker_cfg"; then
      sed -i -E \
        -e 's/^([[:space:]]*modules)[[:space:]]*$/\1             status-webui/' \
        -e '/status-webui/! s/^([[:space:]]*modules[[:space:]]+[^;#]*[^;#[:space:]])/\1,status-webui/' \
        "$broker_cfg"
    fi
  fi

  config_root="$runtime_root"
}

prepare_container_config

case "$role" in
  arbiter)
    [ "$#" -eq 0 ] && set -- -c "${config_root}/shinken.cfg"
    exec shinken-arbiter "$@"
    ;;
  check)
    exec shinken-arbiter -v -c "${config_root}/shinken.cfg" "$@"
    ;;
  scheduler|broker|poller|reactionner|receiver)
    [ "$#" -eq 0 ] && set -- -c "${config_root}/daemons/${role}d.ini"
    exec "shinken-${role}" "$@"
    ;;
  shell)
    exec /bin/sh "$@"
    ;;
  *)
    exec "$role" "$@"
    ;;
esac
