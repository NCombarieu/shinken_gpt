# Glossaire

| Terme | Définition |
|---|---|
| **Acquittement** (*acknowledgement*) | Indication qu'un problème est pris en charge : les rappels de notification s'arrêtent. |
| **Actif (check)** | Check planifié et lancé par Shinken lui-même. |
| **Arbiter** | Daemon qui lit la configuration, la distribue aux autres daemons et les surveille. |
| **Brok** | Message interne décrivant un changement (état, résultat, journal) envoyé au broker. |
| **Broker** | Daemon qui collecte les broks et les transmet à ses modules (Livestatus, page d'état). |
| **Business rule** | Service dont l'état est calculé à partir d'autres hôtes et services (`bp_rule`). |
| **Check** | Exécution d'un plugin pour mesurer l'état d'un hôte ou d'un service. |
| **Commande** (*command*) | Définition d'une ligne à exécuter (check, notification, event handler) avec ses macros. |
| **Commande externe** | Ordre donné à Shinken de l'extérieur (acquitter, poser un downtime, soumettre un résultat). |
| **Contact** | Personne (ou compte) notifiée et autorisée à voir des objets. |
| **Daemon** | Processus de Shinken : arbiter, scheduler, poller, reactionner, broker, receiver. |
| **Dépendance** | Relation qui suspend les checks ou notifications d'un objet quand un autre est en panne. |
| **Downtime** | Période de maintenance déclarée : pas de notification de problème. |
| **Escalade** | Ajout de destinataires quand un problème dure. |
| **Event handler** | Commande lancée automatiquement à un changement d'état (auto-remédiation). |
| **Flapping** | Changements d'état trop fréquents ; les notifications sont alors suspendues. |
| **Freshness** (fraîcheur) | Vérification qu'un résultat passif est arrivé récemment. |
| **HARD (état)** | Problème confirmé après `max_check_attempts` échecs ; déclenche les notifications. |
| **Hôte** (*host*) | Machine ou équipement supervisé, joignable par une adresse. |
| **Impact** | Élément touché par la panne d'un autre (parent, dépendance, business rule). |
| **Livestatus** | Protocole texte (requêtes `GET`, `COMMAND`) pour lire l'état et piloter Shinken ; utilisé par Thruk. |
| **LQL** | *Livestatus Query Language*, le langage des requêtes Livestatus. |
| **Macro** | Variable `$NOM$` remplacée dans une ligne de commande avant exécution. |
| **Modèle** (*template*) | Objet non instancié (`register 0`) dont d'autres objets héritent par `use`. |
| **Module** | Extension chargée par un daemon (Livestatus, rétention, tube nommé…). |
| **`nagios.cmd`** | Tube nommé dans lequel on écrit des commandes externes. |
| **Notification** | Message envoyé à un contact lors d'un problème, d'un rétablissement… |
| **Notificationway** | Mode de notification d'un contact (commandes, périodes, états). |
| **Pack** | Ensemble prêt à l'emploi de modèles et commandes ; ou paquet d'hôtes liés confié à un même scheduler. |
| **Parent** | Hôte en amont dans le réseau ; s'il est DOWN, ses enfants deviennent UNREACHABLE. |
| **Passif (check)** | Résultat soumis à Shinken par un tiers au lieu d'être mesuré par lui. |
| **PENDING** | Objet jamais encore vérifié. |
| **Perfdata** | Données chiffrées renvoyées par un plugin après le `\|`. |
| **Période** (*timeperiod*) | Plages horaires limitant checks, notifications, escalades. |
| **Plugin** | Programme de check : une ligne de sortie et un code retour 0 à 3. |
| **Poller** | Daemon qui exécute les checks. |
| **`poller_tag`** | Étiquette qui réserve des checks à certains pollers. |
| **Reactionner** | Daemon qui exécute les notifications et event handlers. |
| **Realm** | Sous-ensemble autonome de la supervision (site), avec ses propres daemons. |
| **Receiver** | Daemon qui reçoit des données passives venant de l'extérieur. |
| **Rétention** | Sauvegarde de l'état (acquittements, downtimes…) entre deux redémarrages. |
| **Scheduler** | Daemon qui planifie les checks et calcule les états. |
| **Service** | Élément vérifié sur un hôte (disque, port, application). |
| **SOFT (état)** | Problème constaté mais pas encore confirmé ; pas de notification. |
| **Spare** | Daemon de secours, activé si le daemon principal tombe. |
| **Thruk** | Interface web (logiciel séparé) compatible Livestatus. |
| **UNREACHABLE** | État d'un hôte en panne dont les parents sont eux-mêmes en panne. |
| **Worker** | Processus d'exécution des checks dans un poller ou un reactionner. |
