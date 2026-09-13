---
title: "Configurer Shinken"
domain: "Shinken"
type: "guide"
level: "intermediaire"
duration: "25 min"
version: "1.0"
updated: "2026-09-13"
owner: "Administration Supervision"
status: "valid"
order: 4
keywords: [configuration, hosts, services, templates, commands, contacts, ssh, nrpe]
summary: "Structure des fichiers de configuration Shinken, ajout d'hôtes/services, et particularités du réseau depuis un container."
---

# Configurer Shinken

## Objectif

Comprendre où et comment ajouter des hôtes, services, contacts et commandes
de check dans ce dépôt, et éviter les pièges spécifiques à l'exécution en
container.

## Où vivent les fichiers

Tout vit sous `etc/`, monté en lecture seule dans les six containers
(`./etc:/etc/shinken:ro,Z` dans `compose.yaml`) :

```
etc/
├── hosts/       ← define host { ... }
├── services/    ← define service { ... }
├── contacts/    ← define contact { ... }, contactgroups
├── commands/    ← define command { ... }
├── templates/   ← generic-host, generic-service (heritage "use")
├── modules/     ← modules broker (livestatus, status-webui, logstore-null)
├── certs/       ← certificats NRPE (gitignore, voir plus bas)
└── ssh_keys/    ← clefs SSH pour check_by_ssh (gitignore, voir plus bas)
```

Un fichier `.cfg` n'importe où sous ces dossiers est automatiquement chargé
par l'arbiter au démarrage (`cfg_dir=hosts`, `cfg_dir=services`, etc. dans
`etc/shinken.cfg`) — pas besoin de le référencer ailleurs.

!!! attention "Aucun rebuild necessaire pour un .cfg"
    Éditer un fichier sous `etc/` prend effet au prochain redémarrage de
    l'arbiter (`podman restart shinken_arbiter_1`), **jamais** besoin de
    `podman-compose build`. Le build n'est nécessaire que pour du code
    Python (`shinken/`, `modules/*.py`). Détails dans [Exploiter
    Shinken](exploitation.md).

## Ajouter un hôte et un service

Exemple minimal, à adapter (voir `etc/hosts/internet-fun.cfg` et
`etc/services/internet-fun.cfg` pour des exemples réels dans ce dépôt) :

```ini
# etc/hosts/mon-serveur.cfg
define host{
        use                     generic-host
        host_name               mon-serveur
        address                 mon-serveur.example.org
        check_command           check_tcp!443
        }
```

```ini
# etc/services/mon-serveur.cfg
define service{
        use                     generic-service
        host_name               mon-serveur
        service_description     HTTPS
        check_command           check_https_public
        }
```

`generic-host`/`generic-service` (dans `etc/templates/`) portent déjà
`contact_groups admins,users` et les intervalles par défaut — pas besoin de
les répéter.

!!! attention "Caractères interdits dans service_description"
    Shinken refuse `(` et `)` dans un `service_description`
    (`My service_description got the character ( that is not allowed`), et
    fait planter l'**arbiter en boucle** au chargement, pas juste ce
    service. `CPU (SSH)` → `CPU via SSH`. Détail dans [Dépanner
    Shinken](depannage.md).

## Réseau depuis un container {#reseau-depuis-un-container}

C'est le **poller** qui exécute les plugins, depuis son propre container
(`shinken_poller_1`) — pas depuis votre poste ni depuis l'hôte directement.
Trois conséquences concrètes :

1. **ICMP (ping) est bloqué volontairement.** `compose.yaml` retire toutes
   les capacités (`cap_drop: ALL`), y compris `CAP_NET_RAW`. `check_ping`,
   `check_icmp`, et donc le `check_host_alive` par défaut (qui appelle
   `check_ping`), **ne fonctionneront jamais** tels quels. Remplacer le
   `check_command` d'un host par un check TCP/HTTP :

    ```ini
    check_command    check_tcp!443
    ```

   Les checks TCP/HTTP/SSH/NRPE normaux n'ont besoin d'aucune capacité
   spéciale et fonctionnent normalement.

2. **Joindre l'hôte qui fait tourner les containers, depuis un container,
   ne se fait ni par son IP publique ni par la gateway du bridge Podman.**
   Utiliser le nom spécial de Podman rootless :

    ```ini
    address    host.containers.internal
    ```

3. **Le firewall de l'hôte peut bloquer le trafic venant des containers**
   vers les propres services de l'hôte, même via `host.containers.internal`
   — vérifier les règles `nftables`/`firewalld` si un check échoue alors que
   le service cible tourne bien.

## Commandes SSH (`check_by_ssh`) et NRPE (`check_nrpe_ssl`)

Deux briques distinctes, toutes deux nécessitant des secrets qui **ne vont
jamais dans git** :

- **NRPE/NSClient++** : déposer les certificats sous `etc/certs/` (voir
  `etc/certs/README.md` dans le dépôt pour l'exemple de commande complet).
- **SSH** : déposer une clef privée dédiée sous `etc/ssh_keys/` (voir
  `etc/ssh_keys/README.md`), et **restreindre côté serveur cible** via
  `authorized_keys` :

    ```
    command="/chemin/vers/mon_script.sh",no-port-forwarding,no-X11-forwarding,no-agent-forwarding,no-pty ssh-ed25519 AAAA... shinken-monitoring
    ```

!!! attention "Ne jamais interpoler la commande du client dans le command= force"
    `command="... $SSH_ORIGINAL_COMMAND"` réintroduit une injection shell et
    annule toute la restriction : le client contrôle alors ce qui s'exécute.
    Le `command=` doit être **entièrement figé**, arguments compris.

!!! information "Permissions des clefs sous Podman rootless"
    Les UID à l'intérieur d'un container Podman rootless sont **remappés**
    par rapport à l'hôte. Un `chown`/`chmod` classique sur une clef montée
    cible le mauvais UID réel. Utiliser `podman unshare chown/chmod`, et
    relancer le container concerné juste après (le montage a parfois besoin
    d'un restart pour reprendre le nouvel état). Détails dans [Configurer
    l'accès SSH](livestatus-thruk.md) et [Dépanner Shinken](depannage.md).

## Modules broker

Le broker charge ses modules via `etc/brokers/broker-master.cfg` :

```
modules             livestatus,status-webui
```

Chaque module référencé doit avoir sa propre définition sous
`etc/modules/*.cfg` (`define module{ module_name ... module_type ... }`).
Voir [Brancher Thruk via Livestatus](livestatus-thruk.md) pour le détail du
module Livestatus.

## Voir aussi

- [Installer et lancer Shinken](installation.md)
- [Exploiter Shinken au quotidien](exploitation.md)
- [Dépanner Shinken](depannage.md)
