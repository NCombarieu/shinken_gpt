# Recette : serveur Linux supervisé par SSH

**Principe :** le poller se connecte en SSH au serveur supervisé avec une clé
dédiée et y exécute un script de check. Aucun agent à installer ; le serveur
supervisé décide **lui-même** de ce que la clé a le droit d'exécuter.

Commande fournie : `check_by_ssh` (`etc/commands/check_by_ssh.cfg`), avec le
compte `$SSHUSER$` et la clé `$SSHKEY$` (`etc/resource.d/ssh.cfg`).

## 1. Créer la clé sur le serveur de supervision

Depuis la racine du dépôt :

```bash
ssh-keygen -t ed25519 -N "" -C "supervision-shinken" -f etc/ssh_keys/id_ed25519
```

La clé privée doit être lisible par l'utilisateur des conteneurs (UID 10001)
et par lui seul. Avec Podman **rootless**, les UID des conteneurs sont
décalés par rapport à ceux de l'hôte : un `chown 10001` classique vise le
mauvais compte. Utilisez `podman unshare`, qui applique la correspondance :

```bash
podman unshare chown 10001:10001 etc/ssh_keys/id_ed25519
podman unshare chmod 600 etc/ssh_keys/id_ed25519
```

> **Note** — `podman unshare cat /proc/self/uid_map` affiche la
> correspondance des UID. Avec Podman exécuté en root, un simple
> `chown 10001:10001` suffit.

**Ne versionnez jamais la clé privée** : seul `etc/ssh_keys/README.md` est
suivi par git.

## 2. Préparer le serveur supervisé

Créez un compte dédié sans privilège et déposez le script de check :

```bash
sudo useradd --system --create-home --shell /bin/sh supervision
sudo install -d -o root -g root -m 755 /usr/local/lib/supervision
sudo install -o root -g root -m 755 check_load.sh /usr/local/lib/supervision/
```

Exemple de script `/usr/local/lib/supervision/check_load.sh` :

```bash
#!/bin/sh
# Charge moyenne sur 5 minutes rapportée au nombre de processeurs.
warn=${1:-2}; crit=${2:-4}
cpus=$(nproc)
load5=$(cut -d' ' -f2 /proc/loadavg)
ratio=$(awk -v l="$load5" -v c="$cpus" 'BEGIN { printf "%.2f", l / c }')
perf="'load5'=${load5};;;0; 'ratio'=${ratio};${warn};${crit};0;"
if awk -v r="$ratio" -v s="$crit" 'BEGIN { exit !(r >= s) }'; then
    echo "CRITICAL - charge ${load5} pour ${cpus} CPU|$perf"; exit 2
elif awk -v r="$ratio" -v s="$warn" 'BEGIN { exit !(r >= s) }'; then
    echo "WARNING - charge ${load5} pour ${cpus} CPU|$perf"; exit 1
fi
echo "OK - charge ${load5} pour ${cpus} CPU|$perf"
```

Les plugins standard peuvent aussi servir : installez le paquet
`monitoring-plugins-basic` sur le serveur supervisé et utilisez
`/usr/lib/nagios/plugins/check_disk`, `check_load`…

## 3. Restreindre la clé (étape essentielle)

Dans `~supervision/.ssh/authorized_keys` du serveur supervisé, placez la clé
publique (`etc/ssh_keys/id_ed25519.pub`) **précédée d'options de
restriction** :

```
command="/usr/local/lib/supervision/check_load.sh 2 4",restrict ssh-ed25519 AAAA... supervision-shinken
```

- `command="..."` : quelle que soit la commande demandée par le poller,
  **seule celle-ci s'exécute**. C'est la vraie protection : même volée, la
  clé ne permet rien d'autre.
- `restrict` : interdit le transfert de ports, d'agent, X11 et l'allocation
  de terminal (OpenSSH 7.2 et plus ; sinon
  `no-port-forwarding,no-X11-forwarding,no-agent-forwarding,no-pty`).
- Ajoutez `from="192.0.2.5"` (adresse du serveur de supervision) pour
  n'accepter la clé que depuis celui-ci.

### Plusieurs checks avec une seule clé

`command=` n'autorise qu'une commande. Pour plusieurs checks, imposez un
**aiguilleur** qui compare la commande demandée à une liste fermée :

```bash
#!/bin/sh
# /usr/local/lib/supervision/aiguilleur.sh, imposé par command= dans authorized_keys
case "$SSH_ORIGINAL_COMMAND" in
    check_load) exec /usr/local/lib/supervision/check_load.sh 2 4 ;;
    check_disk) exec /usr/lib/nagios/plugins/check_disk -w 15% -c 10% -p / ;;
    *) echo "UNKNOWN - commande refusée"; exit 3 ;;
esac
```

```
command="/usr/local/lib/supervision/aiguilleur.sh",restrict ssh-ed25519 AAAA... supervision-shinken
```

> **Attention** — Ne passez **jamais** `$SSH_ORIGINAL_COMMAND` à un shell
> (`sh -c "$SSH_ORIGINAL_COMMAND"`, `eval`, ou en argument non contrôlé) :
> le poller, ou quiconque détient la clé, pourrait alors exécuter n'importe
> quoi. Comparez-le à des valeurs fixes, comme ci-dessus.

## 4. Déclarer l'hôte et le service

```
define host {
    use                 generic-host
    host_name           srv-linux-01
    address             192.0.2.10
    hostgroups          linux
}

define service {
    use                     generic-service
    host_name               srv-linux-01
    service_description     Charge
    check_command           check_by_ssh!check_load
}
```

L'argument (`check_load`) est la commande envoyée : ignorée avec un
`command=` simple, utilisée par l'aiguilleur.

## 5. Tester depuis le poller

```bash
podman-compose exec poller /usr/lib/nagios/plugins/check_by_ssh \
    -H 192.0.2.10 -l supervision -i /etc/shinken/ssh_keys/id_ed25519 \
    -o StrictHostKeyChecking=accept-new -t 15 -C check_load
```

La première connexion enregistre la clé d'hôte du serveur dans
`/var/lib/shinken/.ssh/known_hosts` (volume persistant) ; une clé d'hôte qui
change ensuite fait échouer le check, ce qui est voulu.

## Dépannage

| Message | Cause |
|---|---|
| `Permission denied (publickey)` | clé publique absente ou mal copiée, droits de `~/.ssh` trop ouverts côté serveur supervisé |
| `Load key ...: Permission denied` ou `bad permissions` | droits de la clé privée : refaire l'étape 1 avec `podman unshare`, puis `podman-compose restart poller` |
| `Host key verification failed` | la clé d'hôte du serveur a changé : vérifier, puis retirer l'ancienne ligne de `known_hosts` |
| `Connection refused` / délai dépassé | pare-feu, ou adresse non joignable **depuis le conteneur poller** |
| Joindre le serveur Podman lui-même | utiliser l'adresse `host.containers.internal` (Podman 4.7 et plus) et autoriser le trafic des conteneurs dans le pare-feu de l'hôte |
