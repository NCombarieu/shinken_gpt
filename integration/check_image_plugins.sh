#!/bin/sh
# Run inside the Shinken image: every plugin referenced by etc/commands must
# exist and load (no missing shared library, no missing Perl module), and the
# helpers the checks rely on must be present. Fails on the first problem
# category with the full list.
set -u
CONF=${1:-/etc/shinken}
P=/usr/lib/nagios/plugins
status=0

plugins=$(grep -rhoE '\$NAGIOSPLUGINSDIR\$/[A-Za-z0-9_.-]+' "$CONF/commands" \
  | sed 's#.*/##' | sort -u)
for plugin in $plugins; do
  path="$P/$plugin"
  if [ ! -x "$path" ]; then
    echo "MISSING plugin: $path"; status=1; continue
  fi
  case "$plugin" in
    *.pl)
      # Manubulon plugins: compile check + SNMPv3 crypto modules.
      perl -c "$path" >/dev/null 2>&1 || { echo "BROKEN perl plugin: $plugin"; status=1; }
      ;;
    *)
      if ldd "$path" 2>/dev/null | grep -q 'not found'; then
        echo "BROKEN plugin (missing libraries): $plugin: $(ldd "$path" | grep 'not found' | awk '{print $1}' | tr '\n' ' ')"
        status=1
      fi
      ;;
  esac
done

for module in Net::SNMP Crypt::DES Crypt::Rijndael Digest::HMAC; do
  perl -M"$module" -e1 2>/dev/null || { echo "MISSING perl module: $module (SNMPv3)"; status=1; }
done
for tool in ssh sshd ssh-keygen snmpget dig; do
  command -v "$tool" >/dev/null 2>&1 || [ -x "/usr/sbin/$tool" ] || { echo "MISSING tool: $tool"; status=1; }
done
[ -x /usr/local/bin/shinken-passive-receive ] \
  || { echo "MISSING: /usr/local/bin/shinken-passive-receive"; status=1; }

# sshd runs ForceCommand as "<login shell> -c <command>": nologin would reject
# every passive push (passive-ssh) and every forced command (lab target).
login_shell=$(getent passwd shinken | cut -d: -f7)
case "$login_shell" in
  */nologin|*/false|"") echo "BAD login shell for shinken: '$login_shell' (sshd ForceCommand needs a real shell)"; status=1 ;;
  *) [ -x "$login_shell" ] || { echo "MISSING login shell: $login_shell"; status=1; } ;;
esac

[ "$status" -eq 0 ] && echo "All $(echo "$plugins" | wc -w) referenced plugins and check helpers are present."
exit "$status"
