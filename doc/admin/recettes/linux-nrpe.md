# Recette : serveur Linux supervisé par NRPE

**Principe :** un petit agent, **NRPE**, tourne sur le serveur supervisé et
exécute à la demande des commandes **déclarées à l'avance** dans sa
configuration. Le poller l'interroge avec `check_nrpe` (port TCP 5666).

À choisir plutôt que [SSH](linux-ssh.md) quand le parc a déjà des agents
NRPE, ou quand on ne souhaite pas ouvrir SSH au serveur de supervision.

## 1. Installer l'agent sur le serveur supervisé

Debian / Ubuntu :

```bash
sudo apt install nagios-nrpe-server monitoring-plugins-basic
```

RHEL et dérivés (dépôt EPEL) :

```bash
sudo dnf install nrpe nagios-plugins-disk nagios-plugins-load nagios-plugins-procs
```

## 2. Configurer l'agent

Dans `/etc/nagios/nrpe.cfg` (ou un fichier de `/etc/nagios/nrpe.d/`) :

```
# Seul le serveur de supervision peut interroger l'agent
allowed_hosts=127.0.0.1,192.0.2.5

# Les arguments venant du réseau sont refusés (recommandé)
dont_blame_nrpe=0

# Commandes autorisées, avec leurs seuils figés
command[check_load]=/usr/lib/nagios/plugins/check_load -r -w 2,1.5,1.2 -c 4,3,2
command[check_disk_root]=/usr/lib/nagios/plugins/check_disk -w 15% -c 10% -p /
command[check_procs_zombie]=/usr/lib/nagios/plugins/check_procs -w 5 -c 10 -s Z
```

Le chemin des plugins dépend de la distribution
(`/usr/lib64/nagios/plugins` sur RHEL). Redémarrez l'agent :
`sudo systemctl restart nagios-nrpe-server` (ou `nrpe`).

Ouvrez le port 5666/TCP du pare-feu **uniquement** pour l'adresse du
serveur de supervision.

## 3. Déclarer les services

La commande fournie `check_nrpe!<nom>` (`etc/commands/check_nrpe.cfg`)
appelle la commande `<nom>` de l'agent :

```
define service {
    use                     generic-service
    hostgroup_name          linux
    service_description     Disque racine
    check_command           check_nrpe!check_disk_root
}

define service {
    use                     generic-service
    hostgroup_name          linux
    service_description     Charge
    check_command           check_nrpe!check_load
}
```

Appliqués au groupe `linux`, ces services sont créés sur chaque serveur Linux.

## 4. Tester depuis le poller

```bash
podman-compose exec poller /usr/lib/nagios/plugins/check_nrpe -H 192.0.2.10
podman-compose exec poller /usr/lib/nagios/plugins/check_nrpe -H 192.0.2.10 -c check_disk_root
```

Sans `-c`, `check_nrpe` affiche la version de l'agent : c'est le test de
connectivité.

## Chiffrement

NRPE chiffre la connexion par TLS ; les versions 4 et plus acceptent un
**certificat client**, ce qui authentifie le serveur de supervision. Déposez
le certificat et la clé du client dans `etc/certs/` (jamais versionnés) et
utilisez la commande `check_nrpe_tls` décrite dans
[etc/certs/README.md](../../../etc/certs/README.md).

## Passer des arguments (déconseillé)

`check_nrpe_args` (`etc/commands/check_nrpe_args.cfg`) transmet des
arguments à l'agent, qui doit l'autoriser (`dont_blame_nrpe=1` et
`command[x]=... $ARG1$`). Cela permet de régler les seuils depuis Shinken,
mais quiconque peut joindre l'agent peut alors choisir ses arguments.
Préférez des commandes figées côté agent.

## Dépannage

| Message | Cause |
|---|---|
| `Connection refused by host` | agent arrêté ou pare-feu |
| `CHECK_NRPE: Error - Could not connect ... Connection reset by peer` | adresse du poller absente de `allowed_hosts` |
| `NRPE: Command 'xxx' not defined` | commande absente de `nrpe.cfg`, ou agent non redémarré |
| `CHECK_NRPE STATE UNKNOWN: Socket timeout` | commande trop longue côté agent (le délai de `check_nrpe` est de 9 s) |
