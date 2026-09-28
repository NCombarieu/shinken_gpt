---
title: "Shinken, qu'est-ce que c'est ?"
domain: "Shinken"
type: "guide"
level: "debutant"
duration: "10 min"
version: "1.0"
updated: "2026-09-13"
owner: "Administration Supervision"
status: "valid"
order: 2
keywords: [shinken, presentation, architecture, daemons, nagios, fork]
summary: "Présentation de Shinken, de son architecture en daemons, et de ce qui distingue ce fork de l'upstream."
---

# Shinken, qu'est-ce que c'est ?

## En une phrase

Shinken surveille des hôtes et des services (un serveur est joignable ? un
disque a de la place ? une API répond ?) en exécutant périodiquement des
**checks** (des petits programmes qui répondent OK/WARNING/CRITICAL/UNKNOWN),
et déclenche des notifications quand l'état change.

Il est **compatible Nagios** : mêmes plugins, même format de fichiers de
configuration (`define host { ... }`), même vocabulaire (host, service,
contact, timeperiod, command…).

## Ce qui le distingue de Nagios

Là où Nagios est un seul processus monolithique, Shinken **éclate le travail
en six daemons spécialisés**, chacun avec un rôle précis :

```
                    ┌──────────┐
                    │ Arbiter  │  lit etc/, distribue la config
                    └────┬─────┘
          ┌──────────────┼──────────────┬──────────────┐
          ▼              ▼              ▼              ▼
    ┌──────────┐  ┌──────────┐   ┌────────────┐  ┌──────────┐
    │Scheduler │  │  Poller  │   │Reactionner │  │ Receiver │
    │ decide   │  │ execute  │   │  execute   │  │ encaisse │
    │ quand    │  │ les      │   │notifs/event│  │ resultats│
    │ checker  │  │ checks   │   │  handlers  │  │ passifs  │
    └────┬─────┘  └──────────┘   └────────────┘  └──────────┘
         │
         ▼
    ┌──────────┐
    │  Broker  │  centralise l'etat, porte les modules
    │          │  (Livestatus, webui...)
    └──────────┘
```

Chaque daemon peut tourner sur une machine différente, être dupliqué pour la
haute disponibilité, ou être "taggé" pour ne traiter qu'un sous-ensemble
d'hôtes (utile en environnement multi-site). **Dans ce dépôt, les six
tournent en local, chacun dans son propre container Podman** (voir
`compose.yaml`) — c'est le déploiement le plus simple, pas le seul possible.

!!! information "Pourquoi ça compte en pratique"
    Comprendre cette séparation évite des heures de débogage : si un check ne
    se déclenche jamais, le problème peut être dans l'**arbiter** (config mal
    distribuée), le **scheduler** (mauvaise planification) ou le **poller**
    (le plugin échoue silencieusement). Les trois ont des logs séparés
    (`podman logs shinken_<daemon>_1`).

## Ce qui distingue *ce fork*

Le Shinken upstream (`naparuba/shinken`) est resté sur Python 2 et n'a plus
de développement actif compatible avec les versions récentes de Python.
Ce fork (`modernize/podman-python3`) :

- porte le cœur, les six daemons et leurs échanges réseau vers **Python
  3.11+** ;
- inclut un vrai **module Livestatus** porté en Python 3
  (`modules/livestatus/`) — historiquement distribué à part de Shinken, pas
  absent de l'écosystème, juste jamais inclus dans ce dépôt avant ;
- se déploie **entièrement par containers Podman**, avec une configuration
  montée en lecture seule depuis `etc/` (pas d'installation système, pas de
  paquet à maintenir) ;
- corrige plusieurs bugs réels découverts en le faisant tourner en
  conditions réelles (voir [Dépanner Shinken](depannage.md)), dont une
  régression de sécurité sur la désérialisation pickle entre daemons.

## Où vivent les checks concrètement

Trois choses à retenir absolument pour ne pas se perdre :

1. **Le poller exécute les plugins dans son propre container.** Un
   `check_by_ssh` ou un `check_http` s'exécute *depuis* le container
   `shinken_poller_1`, pas depuis votre poste. Voir
   [Configurer Shinken](configuration.md#reseau-depuis-un-container) pour les
   implications réseau.
2. **La configuration vit dans `etc/`, montée en lecture seule.** Modifier un
   `.cfg` ne demande jamais de reconstruire l'image — juste de relancer
   l'arbiter (voir [Exploiter Shinken](exploitation.md)).
3. **Rien ne s'affiche tout seul.** Shinken n'a pas d'interface web native
   dans ce fork au-delà d'un module minimal (`status_webui`, port 8081) —
   pour une vraie interface, voir [Brancher Thruk via
   Livestatus](livestatus-thruk.md).

## Pour aller plus loin

- [Installer et lancer Shinken](installation.md)
- [Configurer Shinken](configuration.md)
- Le dépôt upstream historique, <https://github.com/naparuba/shinken> :
  syntaxe des objets de configuration (`define host { ... }`,
  `define service { ... }`, etc.) largement inchangée, ce fork modernise
  l'exécution, pas le format de configuration.
