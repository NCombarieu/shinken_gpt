#!/usr/bin/env bash
# Prepare Shinken runtime paths on RHEL/CentOS.
# Creates the standard directories and assigns ownership/permissions.

set -euo pipefail

SHINKEN_USER=${SHINKEN_USER:-shinken}
SHINKEN_GROUP=${SHINKEN_GROUP:-shinken}

# Minimal sanity checks
if [[ $(id -u) -ne 0 ]]; then
  echo "This script must be run as root." >&2
  exit 1
fi

if [[ ! -f /etc/redhat-release ]]; then
  echo "This script is intended for RHEL/CentOS-like distributions (missing /etc/redhat-release)." >&2
  exit 1
fi

create_user_group() {
  if ! getent group "${SHINKEN_GROUP}" > /dev/null; then
    groupadd --system "${SHINKEN_GROUP}"
  fi

  if ! id "${SHINKEN_USER}" > /dev/null 2>&1; then
    useradd --system --gid "${SHINKEN_GROUP}" \
      --home /var/lib/shinken --shell /sbin/nologin "${SHINKEN_USER}"
  fi
}

create_dirs() {
  local entries=(
    "/etc/shinken:0750"
    "/etc/shinken/packs:0750"
    "/var/lib/shinken:0755"
    "/var/lib/shinken/modules:0755"
    "/var/lib/shinken/libexec:0755"
    "/var/lib/shinken/share:0755"
    "/var/cache/shinken:0755"
    "/var/log/shinken:0755"
    "/var/run/shinken:0755"
  )

  for entry in "${entries[@]}"; do
    local path mode
    IFS=":" read -r path mode <<< "$entry"
    install -d -m "$mode" -o "$SHINKEN_USER" -g "$SHINKEN_GROUP" "$path"
  done
}

main() {
  echo "Configuring Shinken directories for RHEL using user ${SHINKEN_USER}:${SHINKEN_GROUP}"
  create_user_group
  create_dirs
  echo "Done. Paths ready under /etc/shinken, /var/lib/shinken, /var/cache/shinken, /var/log/shinken, /var/run/shinken."
}

main "$@"
