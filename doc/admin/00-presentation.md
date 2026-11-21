# Présentation de Shinken

## En une phrase

Shinken surveille des **hôtes** (serveurs, équipements réseau, sites web…)
et leurs **services** (un disque, un port, une application) en exécutant
régulièrement des **checks** : de petits programmes, appelés *plugins*, qui
répondent OK, WARNING, CRITICAL ou UNKNOWN. Quand un état change, Shinken
prévient les bonnes personnes (**notifications**) et garde l'historique.

Shinken est **compatible Nagios** : mêmes plugins, même format de
configuration (`define host { ... }`), même vocabulaire. Un administrateur
habitué à Nagios, Icinga 1 ou Naemon s'y retrouve immédiatement.

## Ce que fait chaque composant

Là où Nagios est un seul processus, Shinken répartit le travail entre six
**daemons** spécialisés :

```
                 ┌──────────────┐
                 │   Arbiter    │  lit etc/, découpe et distribue la configuration
                 └──────┬───────┘
     ┌──────────────┬───┴──────────┬───────────────┬──────────────┐
     ▼              ▼              ▼               ▼              ▼
┌──────────┐  ┌──────────┐  ┌─────────────┐  ┌──────────┐  ┌──────────┐
│Scheduler │  │  Poller  │  │ Reactionner │  │  Broker  │  │ Receiver │
│ planifie │  │ exécute  │  │ envoie les  │  │ diffuse  │  │ reçoit   │
│ calcule  │  │ les      │  │ notifica-   │  │ l'état   │  │ résultats│
│ les états│  │ checks   │  │ tions       │  │ (Thruk)  │  │ passifs  │
└──────────┘  └──────────┘  └─────────────┘  └──────────┘  └──────────┘
```

| Daemon | Rôle | Port |
|---|---|---|
| **Arbiter** | Lit la configuration, la vérifie, l'envoie aux autres daemons, surveille qu'ils sont vivants. | 7770 |
| **Scheduler** | Planifie les checks, calcule les états (SOFT/HARD), décide des notifications. | 7768 |
| **Poller** | Exécute les plugins de check demandés par le scheduler. | 7771 |
| **Reactionner** | Exécute les notifications et les event handlers. | 7769 |
| **Broker** | Récupère les changements d'état et les diffuse aux modules : Livestatus (pour Thruk), WebUI, journaux. | 7772 |
| **Receiver** | Reçoit les résultats passifs et les commandes externes venant de l'extérieur. | 7773 |

Dans le déploiement fourni, les six daemons tournent sur la même machine,
chacun dans son conteneur Podman. Ils peuvent aussi être répartis sur
plusieurs machines ou dupliqués (voir
[architecture distribuée](20-architecture-distribuee.md)).

## Trois choses à retenir

1. **C'est le poller qui exécute les checks**, depuis son conteneur. Un
   `check_http` part du conteneur poller, pas de votre poste. Les plugins et
   les accès réseau doivent donc être disponibles *depuis le poller*.
2. **La configuration vit dans `etc/`**, sous forme de fichiers texte. Après
   une modification, on vérifie puis on recharge : voir le
   [démarrage rapide](01-demarrage-rapide.md).
3. **L'interface web n'est pas incluse.** Shinken fournit une page d'état
   minimale et un accès **Livestatus** ; l'interface recommandée est
   **Thruk**, installée à côté (voir [lire l'interface](03-interface-web.md)).

## Ce qui distingue cette version

Cette version reprend Shinken 2.4 (Python 2, projet amont plus maintenu) et
le porte sur **Python 3.11+**, avec un déploiement par **conteneurs Podman**.
Le format de configuration et le comportement de supervision sont inchangés ;
les différences avec Shinken « master » sont détaillées dans le
[guide de migration](../migration-depuis-shinken-master.md).

## Suite

- [Démarrage rapide](01-demarrage-rapide.md) : superviser un premier hôte.
- [Concepts essentiels](02-concepts.md) : états, SOFT/HARD, notifications.
- [Glossaire](../glossaire.md).
