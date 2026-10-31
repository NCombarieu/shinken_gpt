---
title: "Configurer Shinken"
domain: "Shinken"
type: "guide"
level: "intermediaire"
duration: "25 min"
version: "1.0"
updated: "2026-10-31"
owner: "Administration Supervision"
status: "valid"
order: 4
keywords: [configuration, hosts, services, templates, commands, contacts, ssh, nrpe, snmp, api, passif]
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
├── certs/       ← certificats NRPE (gitignore)
├── ssh_keys/    ← clés SSH pour check_by_ssh (gitignore)
├── passive/     ← clés des clients passifs SSH (gitignore)
└── secrets/     ← jetons d'API (gitignore)
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

1. **ICMP (ping) est bloqué par défaut, réautorisé seulement sur le poller.**
   `compose.yaml` retire toutes les capacités par défaut (`cap_drop: ALL`),
   mais le service `poller` (celui qui exécute réellement les plugins)
   ajoute `cap_add: [NET_RAW]` — donc `check_ping`/`check_icmp` fonctionnent
   normalement (voir `etc/hosts/localhost.cfg`, host `KIKI`). Les autres
   daemons (arbiter, scheduler, broker, reactionner, receiver) restent sans
   aucune capacité réseau spéciale, `NET_RAW` n'est ajoutée qu'au strict
   nécessaire.

   Pour un check "est-ce que le service répond" plutôt que "est-ce que l'IP
   répond au ping", un check TCP/HTTP reste plus pertinent :

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

## Types de checks (SSH, passif, NRPE, SNMP, API) {#types-de-checks}

Chaque méthode de supervision a sa fiche, avec la configuration côté
cible, côté Shinken, la validation et le dépannage :

| Méthode | Fiche |
|---|---|
| Choisir la bonne méthode | [Choisir un type de check](checks/README.md) |
| Serveur Linux sans agent, par SSH | [SSH actif](checks/ssh-actif.md) |
| La machine envoie ses résultats (cron, traitement, Windows) | [SSH passif](checks/ssh-passif.md) |
| Agent NRPE : Linux, Windows NSClient++ (alias, PowerShell) | [NRPE et NSClient++](checks/nrpe.md) |
| Switchs, routeurs, onduleurs, NAS | [SNMP](checks/snmp.md) |
| Application web, endpoint `/health`, API REST, certificat | [API et HTTP](checks/api.md) |

Les secrets (clés SSH, certificats NRPE, mots de passe SNMPv3, jetons
d'API) vont dans `etc/ssh_keys/`, `etc/certs/`, `etc/resource.d/*.local.cfg`
et `etc/secrets/`, tous **ignorés par git**.

!!! information "Fichiers lisibles par les conteneurs (Podman rootless)"
    Les UID des conteneurs Podman rootless sont **remappés** par rapport à
    l'hôte. Une clé posée sur l'hôte avec `chmod 600` n'est pas lisible
    par le poller (uid 10001). Une seule commande, une fois, la rend
    lisible : `podman unshare chown 10001:10001 <fichier>`. La propriété
    est écrite sur disque et reste valable après une recréation des
    conteneurs. Pour les clés SSH, le poller en fait ensuite lui-même une
    copie privée en `0600` : aucun `chmod` n'est nécessaire.

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
