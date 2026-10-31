# Performances et dimensionnement

**Public :** administrateur de la supervision et exploitant, niveau expert.

## Estimer la charge

La charge principale est le nombre de **checks par seconde** :

```
checks/s ≈ Σ (1 / (check_interval × 60))   sur tous les hôtes et services
```

Exemple : 2 000 services vérifiés toutes les 5 minutes et 200 hôtes toutes
les 5 minutes : 2 200 / 300 ≈ 7,3 checks par seconde. Ajoutez la durée
moyenne d'un check : avec 2 s par check, environ 15 checks tournent en
permanence en parallèle.

Les leviers, du plus efficace au moins efficace :

1. **Intervalles adaptés** : un certificat se vérifie une fois par jour, un
   disque toutes les 15 minutes ; seul ce qui change vite mérite 1 minute.
   Modèles prêts à l'emploi : `etc/templates/time_templates.cfg`.
2. **Checks rapides** : un délai interne court dans les plugins, des
   timeouts réalistes (`service_check_timeout`).
3. **Plus de workers** dans le poller, puis **plus de pollers**.
4. Plusieurs schedulers (voir [architecture distribuée](20-architecture-distribuee.md)).

## Réglages du poller

Dans la définition du poller (`etc/pollers/poller-master.cfg`) :

| Directive | Rôle | Valeur fournie |
|---|---|---|
| `min_workers` / `max_workers` | nombre de processus d'exécution ; `0` = un par processeur | 0 / 0 |
| `processes_by_worker` | checks exécutés en parallèle par processus | 256 |
| `polling_interval` | secondes entre deux demandes de travail au scheduler | 1 |

Le reactionner a les mêmes directives pour les notifications et event
handlers.

> **Note** — La directive Nagios `max_concurrent_checks` est **ignorée** par
> Shinken : la concurrence se règle par le nombre de workers et de pollers.

## Réglages globaux utiles (`shinken.cfg`)

| Directive | Effet sur les performances |
|---|---|
| `max_service_check_spread`, `max_host_check_spread` | étalement des premiers checks au démarrage (minutes) : évite un pic |
| `enable_environment_macros=0` | ne pas exporter toutes les macros en variables d'environnement (coûteux) |
| `flap_history` | mémoire : 4 octets × `flap_history` × (hôtes + services) |
| `max_plugins_output_length` | taille maximale conservée de la sortie d'un plugin |
| `interval_length` | durée en secondes d'une unité d'intervalle (60) : ne pas modifier |

## Mesurer

- **StatsD** : `statsd_enabled=1` dans `shinken.cfg` (l'arbiter transmet le
  réglage aux autres daemons) envoie les métriques internes (taille des files, temps de
  traitement des requêtes HTTP entre daemons) vers un serveur StatsD.
- **Livestatus** : la table `status` donne des compteurs globaux
  (`GET status`), voir [Livestatus](26-livestatus.md).
- **Latence** : la colonne `latency` des services (écart entre l'heure prévue
  et l'heure réelle d'un check) est le meilleur indicateur de saturation.
  Une latence qui grandit signale des pollers débordés.

```bash
printf 'GET services\nStats: avg latency\nStats: max latency\nStats: avg execution_time\n\n' \
    | nc 127.0.0.1 50000
```

## Le serveur lui-même

- Chaque daemon est un processus Python ; le poller crée en plus ses
  processus d'exécution. Comptez de la mémoire pour le scheduler
  (proportionnelle au nombre d'objets) et le broker (Livestatus garde l'état
  de tous les objets en mémoire).
- La base `livestatus.db` (historique) grossit avec le nombre d'événements :
  sa purge se règle par `max_logs_age` du module `logstore-sqlite` (voir
  [Livestatus](26-livestatus.md)).
