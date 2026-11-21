<!-- Page générée par doc/tools/gen_reference.py depuis le code : ne pas modifier à la main. -->


# Mode de notification (notificationway)

Directives acceptées dans un bloc `define notificationway { ... }`. Une directive absente prend la valeur par défaut indiquée ; « obligatoire » signifie qu'aucune valeur par défaut n'est prévue : la définir (directement ou par un modèle), sauf si la description indique qu'elle est déduite.

| Directive | Type | Défaut | Description |
|---|---|---|---|
| `definition_order` | entier | `100` |  |
| `host_notification_commands` | liste | **obligatoire** | Commandes de notification d'hôte. |
| `host_notification_options` | liste |  | Événements d'hôte notifiés (d,u,r,f,s,n). |
| `host_notification_period` | texte | **obligatoire** | Période des notifications d'hôte. |
| `host_notifications_enabled` | booléen (0/1) | 1 | Active les notifications d'hôte pour ce contact. |
| `imported_from` | texte | `unknown` | Renseigné automatiquement : fichier source de la définition. |
| `min_business_impact` | entier | `0` | Impact métier minimal des objets pour lesquels ce contact ou ce mode est notifié. |
| `name` | texte |  | Nom du modèle, utilisé par « use » dans les autres objets. |
| `notificationway_name` | texte | **obligatoire** | Nom unique du mode de notification. |
| `register` | booléen (0/1) | 1 | 0 = l'objet est un modèle et n'est pas instancié. |
| `service_notification_commands` | liste | **obligatoire** | Commandes de notification de service. |
| `service_notification_options` | liste |  | Événements de service notifiés (w,u,c,r,f,s,n). |
| `service_notification_period` | texte | **obligatoire** | Période des notifications de service. |
| `service_notifications_enabled` | booléen (0/1) | 1 | Active les notifications de service pour ce contact. |
| `use` | liste |  | Modèle(s) dont l'objet hérite, séparés par des virgules (le premier est prioritaire). |

Retour à l'[index de la référence](README.md).
