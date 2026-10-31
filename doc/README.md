---
title: "Shinken — présentation du domaine"
domain: "Shinken"
type: "guide"
level: "debutant"
duration: "5 min"
version: "1.0"
updated: "2026-09-13"
owner: "Administration Supervision"
status: "valid"
order: 1
keywords: [shinken, supervision, monitoring, podman, livestatus, thruk, glossaire]
summary: "Point d'entrée de la documentation Shinken : parcours guidés, architecture du dépôt et glossaire."
---

# Documentation Shinken

Ce dépôt (`shinken_gpt`, branche `modernize/podman-python3`) est un fork de
[Shinken](https://github.com/naparuba/shinken), un moteur de supervision
compatible Nagios, porté en Python 3 et conteneurisé avec Podman.

Chaque fiche de ce domaine est **autonome** : elle contient son contexte, ses
prérequis, ses étapes et sa validation.

## Parcours guidés

| Je veux… | Fiche |
|---|---|
| Savoir si cette branche peut remplacer un Shinken master en production (revue du 31/10/2026) | [Revue de migration — synthèse](revue/SYNTHESE.md) |
| Comprendre ce qu'est Shinken et comment ce fork est organisé | [Shinken, qu'est-ce que c'est ?](presentation.md) |
| Installer et lancer la stack sur un serveur | [Installer et lancer Shinken](installation.md) |
| Ajouter des hôtes, services, contacts à superviser | [Configurer Shinken](configuration.md) |
| Choisir comment superviser une machine : SSH, passif, NRPE, SNMP, API | [Choisir un type de check](checks/README.md) |
| Superviser un Linux par SSH, recevoir des résultats passifs | [SSH actif](checks/ssh-actif.md) · [SSH passif](checks/ssh-passif.md) |
| Superviser un Windows (NSClient++), un switch, une API | [NRPE](checks/nrpe.md) · [SNMP](checks/snmp.md) · [API et HTTP](checks/api.md) |
| Brancher une interface web (Thruk) dessus | [Brancher Thruk via Livestatus](livestatus-thruk.md) |
| Recharger la config, forcer un check, faire un ack/downtime | [Exploiter Shinken au quotidien](exploitation.md) |
| Comprendre un comportement bizarre avant de rouvrir une enquête | [Dépanner Shinken](depannage.md) |

## Architecture du dépôt

```
shinken_gpt/
├── shinken/            ← le cœur Shinken (daemons, objets de config, RPC)
├── modules/            ← modules broker embarqués (livestatus, logstore_null, status_webui, dummy_*)
├── etc/                ← configuration Shinken (montée en lecture seule dans les containers)
│   ├── hosts/ services/ contacts/ commands/ modules/ …
│   ├── certs/ ssh_keys/ passive/ secrets/  ← secrets des checks (gitignorés)
│   └── templates/      ← generic-host, generic-service, etc.
├── compose.yaml        ← 6 containers Podman (un par daemon) + passive-ssh (profil "passive")
├── containers/         ← entrypoint, récepteur passif SSH, plugins fournis (check_json_api)
├── contrib/checks/     ← à poser sur les machines supervisées (SSH, NSClient++, NRPE, clients passifs)
├── Containerfile        ← image des containers (Python 3, plugins Nagios standard, NRPE, SNMP, SSH)
└── doc/                ← vous êtes ici
```

!!! information "Pourquoi un fork de plus"
    Le projet upstream Shinken n'a plus de développement actif compatible
    Python 3 récent. Ce fork porte le cœur, les daemons et un vrai module
    Livestatus (absent du dépôt upstream, distribué historiquement à part)
    vers Python 3.11+, dans une architecture conteneurisée reproductible.

## Glossaire

| Terme | Définition |
|---|---|
| **Arbiter** | Daemon qui lit la config et la distribue à tous les autres. |
| **Scheduler** | Daemon qui décide quand chaque check doit s'exécuter. |
| **Poller** | Daemon qui exécute réellement les plugins de check (SSH, HTTP, NRPE…). |
| **Reactionner** | Daemon qui exécute les notifications et event handlers. |
| **Broker** | Daemon qui centralise l'état (broks) et porte les modules (Livestatus, webui). |
| **Receiver** | Daemon qui encaisse les résultats passifs et commandes externes entrantes. |
| **Brok** | Message interne (`BROK`) transportant un changement d'état entre daemons. |
| **Livestatus** | Protocole texte (requêtes `GET`/`COMMAND`) pour interroger et piloter Shinken depuis l'extérieur — c'est ce que parle Thruk. |
| **Thruk** | Interface web générique compatible Livestatus, pas incluse dans ce dépôt (voir [Brancher Thruk](livestatus-thruk.md)). |
