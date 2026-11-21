# Architecture du code

**Public :** développeur. Description de l'architecture **réelle** de cette
version ; les noms de fichiers sont relatifs à la racine du dépôt.

## Vue d'ensemble

Six processus (daemons) indépendants, qui communiquent en HTTP. Chacun est
lancé par un script `bin/shinken-<daemon>` qui instancie une classe de
`shinken/daemons/` :

| Daemon | Classe | Fichier | Port |
|---|---|---|---|
| arbiter | `Arbiter` | `shinken/daemons/arbiterdaemon.py` | 7770 |
| scheduler | `Shinken` | `shinken/daemons/schedulerdaemon.py` (+ `shinken/scheduler.py`) | 7768 |
| poller | `Poller` | `shinken/daemons/pollerdaemon.py` (+ `shinken/satellite.py`) | 7771 |
| reactionner | `Reactionner` | `shinken/daemons/reactionnerdaemon.py` (+ `shinken/satellite.py`) | 7769 |
| broker | `Broker` | `shinken/daemons/brokerdaemon.py` | 7772 |
| receiver | `Receiver` | `shinken/daemons/receiverdaemon.py` | 7773 |

Base commune : `shinken/daemon.py` (`Daemon` : lecture du `.ini`, fichier
PID, journal local, serveur HTTP, gestion des modules, signaux) et
`shinken/satellite.py` (`BaseSatellite`, `Satellite` : réception de
configuration, files d'actions, workers).

Le dossier `shinken/daemons/<nom>/` contient des métadonnées de paquet
inutilisées ; le code des daemons est dans les fichiers `*daemon.py`.

## Flux de la configuration

```
etc/*.cfg ──► Arbiter
               │ Config.read_config()       shinken/objects/config.py : lecture, cfg_dir, macros de ressource
               │ create_objects()           un objet Python par « define »
               │ linkify_templates / apply_inheritance / explode
               │ fill_default / linkify / is_correct
               │ cut_into_parts()           découpage en « packs » d'hôtes liés, par realm
               ▼
           Dispatcher (shinken/dispatcher.py)
               │ POST /put_conf             une part de configuration par scheduler
               │ POST /put_conf             aux satellites : la liste des schedulers à contacter
               ▼
  scheduler(s)     poller(s), reactionner(s), broker(s), receiver(s)
```

L'arbiter vérifie ensuite périodiquement chaque daemon (`GET /ping`,
`/have_conf`, `/what_i_managed`) et redistribue la configuration à un
daemon de secours si un daemon meurt.

Les objets de configuration sont dans `shinken/objects/` : une classe par
type (`Host`, `Service`, `Contact`, `Timeperiod`…) et une classe conteneur
(`Hosts`, `Services`…). Les directives acceptées sont décrites par le
dictionnaire `properties` de chaque classe (types dans `shinken/property.py`)
— c'est la source de la [référence générée](../admin/reference/README.md).
L'état d'exécution est dans `running_properties`.

## Flux des checks

```
Scheduler                                    Poller
  Scheduler.schedule()  crée des Check        │
  (shinken/check.py)                          │ GET /get_checks (poller_tags, worker_capable…)
        ◄─────────────────────────────────────┤
                                              │ Worker (shinken/worker.py) exécute la commande
                                              │ (shinken/action.py : sous-processus, timeout)
        ◄─────────────────────────────────────┤ POST /put_results
  consume_results()  → SchedulingItem.consume_result()
     (shinken/objects/schedulingitem.py) : SOFT/HARD, flapping,
     notifications, event handlers, dépendances
```

Le poller **tire** le travail (`polling_interval`). Un poller déclaré
`passive 1` est au contraire alimenté par le scheduler (`/push_actions`,
`/get_returns`).

Le reactionner fonctionne de même pour les `Notification`
(`shinken/notification.py`) et `EventHandler` (`shinken/eventhandler.py`) :
`/get_checks` avec `do_actions=True`.

Les macros des lignes de commande sont résolues **par le scheduler** avant
l'envoi (`shinken/macroresolver.py`) : le poller exécute une ligne finale.

## Flux des broks (diffusion de l'état)

Un **brok** (`shinken/brok.py`) est un message d'état : configuration
initiale d'un objet, résultat de check, changement d'état, journal…

```
scheduler / poller / reactionner / receiver ──► (file de broks)
                                   ◄── GET /get_broks ── Broker
arbiter ── POST /push_broks ──► Broker
Broker ──► modules : manage_brok(brok)  (livestatus, status_webui, …)
```

Le broker tire les broks des autres daemons ; l'arbiter lui pousse les
siens. Chaque module du broker reçoit chaque brok (`BaseModule.manage_brok`
appelle `manage_<type>_brok`).

## Flux des commandes externes

```
Livestatus (module du broker) / nagios.cmd (module named-pipe de l'arbiter)
     │ ExternalCommand
     ▼
Broker.get_external_commands()  ◄── GET /get_external_commands ── Arbiter
     │
Arbiter : ExternalCommandManager (mode « dispatcher », shinken/external_command.py)
     │  commande « globale » interne (RESTART_PROGRAM…) : exécutée par l'arbiter
     │  commande sur un hôte ou service : envoyée au scheduler qui le gère
     ▼
Scheduler : POST /run_external_commands → ExternalCommandManager (mode « applyer »)
```

## Modules

Un module est un paquet Python de `modules/` chargé par
`shinken/modulesmanager.py` dans un daemon, selon la directive `modules` de
sa définition. Il peut être **interne** (appelé dans le processus du daemon,
via des *hooks*) ou **externe** (processus séparé, échanges par files).
Voir [écrire un module](ecrire-un-module.md).

| Module | Daemon | Rôle |
|---|---|---|
| `livestatus` | broker | serveur Livestatus (TCP 50000) |
| `logstore_sqlite`, `logstore_null` | broker (sous-modules de livestatus) | historique `GET log` |
| `status_webui` | broker | page d'état et API JSON |
| `retention_pickle` | scheduler | sauvegarde et restauration de l'état |
| `named_pipe` | arbiter, receiver | tube `nagios.cmd` |
| `dummy_*` | — | exemples et tests |

## Couche réseau

- Serveur : `shinken/http_daemon.py` — Bottle sur **Cheroot**, un pool de
  threads (`daemon_thread_pool_size`), TLS optionnel. Chaque méthode publique
  des objets « interface » (`Interface`, `IForArbiter`, `IChecks`, `IBroks`…)
  devient une route `/<nom>` (et `/<nom-avec-tirets>`).
- Client : `shinken/http_client.py` — **pycurl**, connexions persistantes.
- Sérialisation : pickle, compressé et encodé, avec désérialisation
  restreinte (`shinken/safepickle.py`). Détails :
  [protocole entre daemons](protocole-inter-daemons.md).

`shinken/pyro_wrapper.py` est un vestige non utilisé : il n'y a ni Pyro ni
protocol buffers dans le transport.

## Autres composants

| Fichier | Rôle |
|---|---|
| `shinken/log.py`, `shinken/structured_logging.py`, `shinken/bin_utils.py` | journalisation (voir [journalisation](journalisation.md)) |
| `shinken/stats.py` | métriques internes vers StatsD |
| `shinken/daterange.py`, `shinken/objects/timeperiod.py` | périodes de temps |
| `shinken/dependencynode.py` | business rules (`bp_rule`) |
| `shinken/downtime.py`, `acknowledge.py`, `comment.py` | maintenance, acquittements, commentaires |
| `shinken/trigger_functions.py`, `objects/trigger.py` | triggers (fonction héritée, non validée en Python 3) |
| `shinken/discovery/` | outil de découverte (non maintenu) |
| `bin/shinken-healthcheck` | sonde de santé (stdlib uniquement) |
| `containers/entrypoint.sh` | point d'entrée de l'image |

## Pour commencer à lire le code

1. `shinken/objects/item.py` puis `host.py` / `service.py` : modèle objet.
2. `shinken/objects/schedulingitem.py` : `consume_result`, la logique
   d'état (SOFT/HARD, notifications).
3. `shinken/scheduler.py` : la boucle du scheduler (`run`, tâches
   récurrentes).
4. `shinken/satellite.py` et `shinken/worker.py` : exécution des actions.
5. `shinken/dispatcher.py` : répartition de la configuration.
