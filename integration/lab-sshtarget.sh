#!/bin/sh
# Integration lab: an unprivileged sshd playing a monitored Linux host.
# The only key allowed is the poller's, with a forced command
# (contrib/checks/ssh/shinken-checks), exactly as on a real target.
set -eu
d=/var/lib/shinken/sshtarget
mkdir -p "$d"
chmod 700 "$d"
[ -f "$d/host_key" ] || ssh-keygen -q -t ed25519 -N "" -f "$d/host_key"
cp /opt/sshtarget/authorized_keys "$d/authorized_keys"
chmod 600 "$d/authorized_keys"
cat >"$d/sshd_config" <<CFG
Port 2200
HostKey $d/host_key
PidFile $d/sshd.pid
AuthorizedKeysFile $d/authorized_keys
AllowUsers $(id -un)
PasswordAuthentication no
KbdInteractiveAuthentication no
UsePAM no
CFG
exec /usr/sbin/sshd -D -e -f "$d/sshd_config"
