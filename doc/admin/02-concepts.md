# Concepts essentiels

**Public :** administrateur de la supervision, niveau simple.

## Hôtes et services

- Un **hôte** (`define host`) est une machine ou un équipement joignable sur
  le réseau : serveur, commutateur, imprimante, ou même un site web.
- Un **service** (`define service`) est une chose que l'on vérifie *sur* un
  hôte : l'espace disque, un port, une page web, une base de données. Un
  service appartient toujours à un hôte.

Chaque hôte et chaque service a un **check** : une commande
(`check_command`) qui exécute un **plugin** et en interprète le résultat.

## Le plugin et son code retour

Un plugin est un programme qui fait une mesure, affiche **une ligne de
texte** et se termine avec un **code retour** :

| Code | État d'un service | État d'un hôte |
|---|---|---|
| 0 | **OK** | **UP** |
| 1 | **WARNING** : seuil d'alerte franchi | UP (un hôte n'a pas d'état WARNING) |
| 2 | **CRITICAL** : seuil critique franchi ou panne | **DOWN** |
| 3 | **UNKNOWN** : la mesure n'a pas pu être faite (mauvais argument, délai dépassé…) | DOWN |

Un hôte est **UNREACHABLE** (injoignable) lorsque son check échoue et que
tous ses **parents** (directive `parents`, par exemple le routeur devant lui)
sont eux-mêmes DOWN : on sait alors que le problème vient d'ailleurs.

Un objet jamais encore vérifié est **PENDING** (en attente).

Exemple de sortie de plugin :

```
DISK OK - free space: / 12034 MB (61% inode=89%);| /=7701MB;15738;17707;0;19675
```

Ce qui suit le `|` est la **perfdata** (données de performance) : des
mesures chiffrées exploitables pour des graphiques. Voir
[écrire un plugin](16-ecrire-un-plugin.md).

## Checks actifs et passifs

- **Actif** : Shinken décide quand vérifier et lance lui-même le plugin, à
  intervalle régulier (`check_interval`). C'est le cas par défaut.
- **Passif** : le résultat est envoyé à Shinken par un tiers (script, autre
  logiciel, tâche planifiée). Shinken ne lance rien ; il peut seulement
  constater qu'aucun résultat n'arrive plus (*freshness*). Voir
  [checks passifs](15-checks-passifs-commandes-externes.md).

## États SOFT et HARD

Un problème ponctuel (un paquet perdu, un pic de charge) ne doit pas réveiller
l'astreinte. Shinken distingue donc :

- **SOFT** : un problème vient d'être constaté mais n'est pas encore
  confirmé. Shinken revérifie plus souvent (`retry_interval`). **Aucune
  notification.**
- **HARD** : le problème est confirmé après `max_check_attempts` checks en
  échec consécutifs. **Les notifications partent.**

Exemple avec `check_interval 5`, `retry_interval 2`, `max_check_attempts 3`
(valeurs du modèle `generic-service`) :

| Minute | Résultat du check | État | Action |
|---|---|---|---|
| 0 | OK | OK (HARD) | prochain check dans 5 min (`check_interval`) |
| 5 | CRITICAL | CRITICAL **SOFT** 1/3 | prochain check dans 2 min (`retry_interval`) |
| 7 | CRITICAL | CRITICAL **SOFT** 2/3 | prochain check dans 2 min |
| 9 | CRITICAL | CRITICAL **HARD** 3/3 | **notification**, retour au rythme de 5 min |
| 14, 19… | CRITICAL | CRITICAL HARD | rappel toutes les `notification_interval` minutes |

Le retour à OK est immédiat (un seul check OK suffit) et donne lieu à une
notification de **rétablissement** (*recovery*) si le problème était HARD.

| Directive | Rôle | `generic-service` | `generic-host` |
|---|---|---|---|
| `check_interval` | minutes entre deux checks en temps normal | 5 | 5 |
| `retry_interval` | minutes entre deux checks pendant un état SOFT | 2 | 1 |
| `max_check_attempts` | nombre d'échecs pour passer HARD | 3 | 2 |

Pour adapter la tolérance d'un service, utilisez les modèles de
`etc/templates/time_templates.cfg` (`5min_short`, `5min_long`…).

## Périodes de temps

Une **période** (`define timeperiod`) décrit des plages horaires : `24x7`,
`workhours` (heures ouvrées hors jours fériés), `none` (jamais). Elle sert à
limiter :

- les checks : `check_period` ;
- les notifications : `notification_period` (sur l'hôte ou le service) et
  `host_notification_period` / `service_notification_period` (sur le
  contact).

Exemple : `notification_period workhours` sur un serveur de test — il est
vérifié en permanence mais ne prévient qu'aux heures ouvrées. Syntaxe :
[périodes de temps](18-periodes-de-temps.md).

## Notifications

Une notification part lorsqu'un hôte ou un service entre en état **HARD**
problématique, puis à chaque rappel (`notification_interval`, en minutes ;
`0` = une seule notification), et au rétablissement. Il faut pour cela :

1. que `notifications_enabled` soit à 1 et que l'on soit dans la
   `notification_period` ;
2. que l'état figure dans `notification_options` (`w,u,c,r,f,s` pour un
   service, `d,u,r,f,s` pour un hôte : warning, unknown, critical, recovery,
   flapping, downtime / down, unreachable…) ;
3. que l'objet ait des **contacts** (`contacts`, `contact_groups`) ;
4. que le problème ne soit ni **acquitté** ni en **downtime**.

Le contact reçoit alors le message selon ses **modes de notification**
(`notificationways`, par défaut l'e-mail). Détails :
[notifications](17-notifications.md).

## Acquittement et downtime

- **Acquitter** (*acknowledge*) un problème, c'est dire « je m'en occupe » :
  les rappels de notification s'arrêtent jusqu'au retour à la normale.
- Un **downtime** est une maintenance planifiée : pendant la période
  déclarée, l'objet est vérifié mais ne notifie pas.

Voir [acquitter et planifier un downtime](04-acquitter-et-planifier-un-downtime.md).

## Flapping

Un service qui change d'état sans arrêt (OK, CRITICAL, OK…) est dit
**flapping**. Shinken le détecte et suspend les notifications tant que cela
dure, pour éviter une avalanche de messages. Voir
[flapping et event handlers](14-flapping-et-event-handlers.md).

## Suite

- [Lire l'interface web](03-interface-web.md)
- [Glossaire](../glossaire.md)
