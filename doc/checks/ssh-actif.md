---
title: "Superviser un serveur Linux par SSH (check actif)"
domain: "Shinken"
type: "procedure"
level: "intermediaire"
duration: "20 min"
version: "1.0"
updated: "2026-10-31"
owner: "Administration Supervision"
status: "valid"
order: 11
keywords: [ssh, check_by_ssh, authorized_keys, known_hosts, podman, rootless, linux]
summary: "Superviser un serveur Linux sans agent : clé dédiée côté Shinken, compte restreint et commande forcée côté cible."
---

# Superviser un serveur Linux par SSH (check actif)

## Objectif

Le poller se connecte en SSH à la machine, lui demande un check par son
**nom** (`load`, `disk`...) et récupère le résultat. Rien d'autre à
installer sur la cible que les plugins Nagios standard.

```
poller (Podman)  --ssh, clé dédiée-->  srv-web01 : compte "monitoring"
  check_by_ssh -C "disk"                 authorized_keys: command="/usr/local/bin/shinken-checks"
                                         -> exécute check_disk -w 20% -c 10% (seuils fixés sur la cible)
  "DISK OK - ..."  <--------------------
```

## Principe de sécurité

La clé de supervision est **restreinte sur la cible** par une commande forcée
(`command=` dans `authorized_keys`). Shinken envoie seulement un nom de
check ; le script `shinken-checks` le compare à une liste fixe et n'exécute
rien d'autre. Même volée, la clé ne donne ni shell, ni redirection de port,
ni exécution de commande arbitraire.

## Prérequis

- Shinken déployé avec `compose.yaml` (le poller doit avoir été recréé avec
  l'image de cette version).
- Sur la cible : `sshd`, et les plugins Nagios
  (`apt install monitoring-plugins-basic` ou `dnf install nagios-plugins-all`).
- Le poller doit joindre la cible sur son port SSH (pare-feu).

## Étapes

### 1. Créer la clé de supervision (une seule pour tout le parc)

Sur le serveur Podman, à la racine du dépôt :

```sh
ssh-keygen -t ed25519 -N "" -C shinken-monitoring -f etc/ssh_keys/shinken_monitoring
podman unshare chown 10001:10001 etc/ssh_keys/shinken_monitoring
```

La seconde commande rend la clé lisible par l'utilisateur du conteneur
(uid 10001). Elle se fait **une fois** : la propriété est écrite sur disque.

### 2. Préparer la cible (en root)

```sh
useradd -m -s /bin/sh monitoring
install -m 755 shinken-checks /usr/local/bin/shinken-checks   # contrib/checks/ssh/shinken-checks
install -d -m 700 -o monitoring -g monitoring ~monitoring/.ssh
cat >~monitoring/.ssh/authorized_keys <<'EOF'
restrict,from="192.0.2.10",command="/usr/local/bin/shinken-checks" ssh-ed25519 AAAA...contenu de shinken_monitoring.pub... shinken-monitoring
EOF
chown monitoring: ~monitoring/.ssh/authorized_keys && chmod 600 ~monitoring/.ssh/authorized_keys
```

`restrict` coupe shell, PTY et redirections (OpenSSH 7.2 et plus ; sinon
`no-port-forwarding,no-X11-forwarding,no-agent-forwarding,no-pty`), et
`from=` n'accepte la clé que depuis l'adresse du serveur Podman telle que la
cible la voit.

Adaptez la liste des checks et leurs seuils dans `/usr/local/bin/shinken-checks`
(fourni : `load`, `disk`, `disk-root`, `swap`, `procs`, `zombies`, `users`,
`uptime`, `ntp`, `service-sshd`). Pour un script maison, ajoutez une ligne
`nom) exec /chemin/script ;;` ; le script doit appartenir à root et ne pas
être modifiable par `monitoring`.

!!! attention "Ne jamais réinjecter la commande du client"
    `command="... $SSH_ORIGINAL_COMMAND"`, ou un `eval`/`sh -c` de cette
    variable dans le script, redonne au client le choix de ce qui s'exécute.
    `shinken-checks` ne fait que la **comparer** à une liste (`case`).

### 3. Épingler l'empreinte SSH de la cible (recommandé)

```sh
ssh-keyscan -t ed25519 srv-web01.example.lan >> etc/ssh_keys/known_hosts
ssh-keyscan -t ed25519 -p 2200 srv-db01.example.lan >> etc/ssh_keys/known_hosts   # port non standard
podman unshare chown 10001:10001 etc/ssh_keys/known_hosts
```

Le nom doit être exactement l'`address` de l'hôte dans Shinken (un nom et
son IP sont deux entrées différentes).

Vérifiez l'empreinte affichée (`ssh-keygen -lf etc/ssh_keys/known_hosts`)
avec celle de la cible (`ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub`).

Avec un fichier `known_hosts`, une cible absente du fichier ou dont la clé a
changé est **refusée** : y compris celles qui marchaient déjà. Ajoutez
toutes les cibles existantes, par exemple pour `this-vps` (le serveur
Podman lui-même) :

```sh
ssh-keyscan -t ed25519 localhost | sed 's/^localhost/host.containers.internal/' >> etc/ssh_keys/known_hosts
``` Sans ce fichier, le poller accepte la clé d'une cible
à la première connexion puis la mémorise (`/var/lib/shinken/ssh_known_hosts`) :
pratique, mais une usurpation lors de cette première connexion passerait
inaperçue.

### 4. Déclarer l'hôte et ses services

```ini
# etc/hosts/srv-web01.cfg
define host{
        use                     linux-ssh
        host_name               srv-web01
        address                 srv-web01.example.lan
        ; _SSH_USER  monitoring   (défaut, défini dans generic-host)
        ; _SSH_PORT  22
        }
```

```ini
# etc/services/srv-web01.cfg
define service{
        use                     generic-service
        host_name               srv-web01
        service_description     Load
        check_command           check_by_ssh!load
        }
define service{
        use                     generic-service
        host_name               srv-web01
        service_description     Disk
        check_command           check_by_ssh!disk
        }
```

Le modèle `linux-ssh` vérifie l'hôte avec `check_ssh_port` (le sshd répond),
sans clé.

### 5. Appliquer

```sh
podman restart shinken_poller_1     # seulement si la clé ou known_hosts ont changé
podman restart shinken_arbiter_1    # recharge la configuration
```

## Validation

Depuis le poller, avec exactement ce que Shinken exécute :

```sh
podman exec shinken_poller_1 /usr/lib/nagios/plugins/check_by_ssh \
    -H srv-web01.example.lan -l monitoring -C disk -t 30
# DISK OK - free space: / 30328MiB (77% inode=98%);| ...

podman exec shinken_poller_1 /usr/lib/nagios/plugins/check_by_ssh \
    -H srv-web01.example.lan -l monitoring -C "cat /etc/shadow"
# UNKNOWN - check 'cat /etc/shadow' is not allowed on srv-web01   <- attendu
```

!!! information "Plusieurs clés"
    Toutes les clés de `etc/ssh_keys/` sont proposées à chaque connexion.
    Au-delà de 5 ou 6 clés, une cible peut refuser la connexion
    (`MaxAuthTries`) : gardez une seule clé de supervision pour le parc.

## Ce que fait le poller au démarrage

Le script de démarrage du conteneur poller (`containers/entrypoint.sh`) :

1. copie chaque clé privée de `/etc/shinken/ssh_keys/` dans un répertoire
   privé, en `0600`. `ssh` exige ce mode quand la clé appartient à
   l'utilisateur qui l'utilise ;
2. écrit la configuration du client ssh (incluse par
   `/etc/ssh/ssh_config.d/shinken.conf`) : `BatchMode yes` (jamais de
   question bloquante), `ConnectTimeout 10`, toutes les clés en
   `IdentityFile`, et le `known_hosts` décrit plus haut.

Les commandes n'ont donc besoin ni de `-i` ni de `-o`.

## Dépannage {#depannage}

| Symptôme | Cause | Action |
|---|---|---|
| Log du poller : `WARNING: SSH key ... is not readable by uid 10001` | Clé posée depuis l'hôte, illisible dans le conteneur rootless | `podman unshare chown 10001:10001 etc/ssh_keys/<clé>` puis `podman restart shinken_poller_1` |
| `Permission denied (publickey)` | Clé publique absente ou mal copiée sur la cible, droits de `~/.ssh` | Sur la cible : `~monitoring/.ssh` en 700, `authorized_keys` en 600, propriétaire `monitoring` ; voir `/var/log/auth.log` |
| `No ED25519 host key is known for X and you have requested strict checking` / `Host key verification failed` | Cible absente de `etc/ssh_keys/known_hosts` (le nom doit être celui de `address`), ou clé de la cible changée | Ajouter ou mettre à jour l'empreinte (étape 3), puis redémarrer le poller |
| `UNKNOWN - check 'xxx' is not allowed` | Nom de check absent de `shinken-checks` sur la cible | Ajouter une entrée au `case`, ou corriger le nom dans `check_command` |
| `Remote command execution failed` / plugin introuvable | Plugins non installés sur la cible, ou chemin différent | `ls /usr/lib/nagios/plugins` (Debian) ou `/usr/lib64/nagios/plugins` (RHEL) |
| `Connection timed out` | Pare-feu, ou mauvaise adresse | `podman exec shinken_poller_1 /usr/lib/nagios/plugins/check_ssh srv-web01` |

!!! information "Ancien service `check_by_ssh_cpu`"
    La commande `check_by_ssh_cpu!<utilisateur>` (service `CPU via SSH` de
    `this-vps`) fonctionne toujours. Elle n'a plus besoin de `-i` : la clé
    `shinken_monitoring` est prise dans la configuration générée.

## Voir aussi

- [SSH passif](ssh-passif.md) : la cible envoie elle-même ses résultats.
- [Choisir un type de check](README.md)
