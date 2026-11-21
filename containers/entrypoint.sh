#!/bin/sh
# Point d'entrée de l'image Shinken.
#
# Usage : shinken-entrypoint <rôle> [options du daemon]
#   rôle : arbiter | scheduler | poller | reactionner | broker | receiver
#          check  (valide la configuration : shinken-arbiter -v, puis sort)
#          passive-ssh (réception des résultats passifs par SSH,
#                 doc/admin/recettes/passif-ssh.md)
#          shell  (ouvre un /bin/sh)   ou toute autre commande, exécutée telle quelle.
#
# La configuration montée (SHINKEN_CONFIG, /etc/shinken par défaut) n'est
# JAMAIS modifiée. Quand SHINKEN_CONTAINER_DNS=1 (cas de compose.yaml et des
# quadlets), elle est copiée dans SHINKEN_RUNTIME_CONFIG (/tmp/shinken-config)
# et la COPIE est adaptée au réseau des conteneurs :
#
#  0. les secrets (ssh_keys/, certs/, passive/, secrets/) ne sont PAS copiés :
#     ils sont lus à leur chemin d'origine (/etc/shinken/...), et une clé en
#     0600 illisible par un daemon ne doit pas faire échouer la copie, donc
#     le démarrage de tous les conteneurs.
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

log() {
  echo "shinken-entrypoint: $*" >&2
}

role="${1:-arbiter}"
[ "$#" -gt 0 ] && shift
config_root="${SHINKEN_CONFIG:-/etc/shinken}"
# Secrets are read from the mounted configuration, never from the runtime copy.
secrets_root="$config_root"

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
  (cd "$config_root" && tar -cf - --exclude=./ssh_keys --exclude=./certs \
      --exclude=./passive --exclude=./secrets .) \
    | (cd "$runtime_root" && tar -xf -)

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

# Passive results pushed over SSH (doc/admin/recettes/passif-ssh.md): an
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
