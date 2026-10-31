<!-- Page générée par doc/tools/gen_reference.py depuis le code : ne pas modifier à la main. -->


# Contact (contact)

Directives acceptées dans un bloc `define contact { ... }`. Une directive absente prend la valeur par défaut indiquée ; « obligatoire » signifie qu'aucune valeur par défaut n'est prévue : la définir (directement ou par un modèle), sauf si la description indique qu'elle est déduite.

Toute directive commençant par `_` est une macro personnalisée (voir [macros](macros.md)).

| Directive | Type | Défaut | Description |
|---|---|---|---|
| `address1` | texte | `none` |  |
| `address2` | texte | `none` |  |
| `address3` | texte | `none` |  |
| `address4` | texte | `none` |  |
| `address5` | texte | `none` |  |
| `address6` | texte | `none` |  |
| `alias` | texte | `none` | Nom long affiché dans les interfaces. |
| `can_submit_commands` | booléen (0/1) | 0 | Autorise l'envoi de commandes (acquittement, downtime…) depuis les interfaces. |
| `contact_name` | texte | **obligatoire** | Identifiant unique du contact ; doit correspondre au login dans Thruk. |
| `contactgroups` | liste |  | Groupes de contacts dont le contact fait partie. |
| `definition_order` | entier | `100` |  |
| `email` | texte | `none` | Adresse e-mail ($CONTACTEMAIL$). |
| `expert` | booléen (0/1) | 0 |  |
| `host_notification_commands` | liste | **obligatoire** | Commandes de notification d'hôte. |
| `host_notification_options` | liste |  | Événements d'hôte notifiés (d,u,r,f,s,n). |
| `host_notification_period` | texte | **obligatoire** | Période des notifications d'hôte. |
| `host_notifications_enabled` | booléen (0/1) | 1 | Active les notifications d'hôte pour ce contact. |
| `imported_from` | texte | `unknown` | Renseigné automatiquement : fichier source de la définition. |
| `is_admin` | booléen (0/1) | 0 | Droits d'administration dans les interfaces qui l'exploitent. |
| `min_business_impact` | entier | `0` | Impact métier minimal des objets pour lesquels ce contact ou ce mode est notifié. |
| `name` | texte |  | Nom du modèle, utilisé par « use » dans les autres objets. |
| `notificationways` | liste |  | Modes de notification (objets notificationway) du contact. |
| `pager` | texte | `none` | Numéro de téléphone ou de pager ($CONTACTPAGER$). |
| `password` | texte | `NOPASSWORDSET` | Mot de passe pour les interfaces qui s'authentifient auprès de Shinken. |
| `register` | booléen (0/1) | 1 | 0 = l'objet est un modèle et n'est pas instancié. |
| `retain_status_information` | booléen (0/1) | 1 | Conserver l'état au redémarrage (nécessite un module de rétention). |
| `service_notification_commands` | liste | **obligatoire** | Commandes de notification de service. |
| `service_notification_options` | liste |  | Événements de service notifiés (w,u,c,r,f,s,n). |
| `service_notification_period` | texte | **obligatoire** | Période des notifications de service. |
| `service_notifications_enabled` | booléen (0/1) | 1 | Active les notifications de service pour ce contact. |
| `use` | liste |  | Modèle(s) dont l'objet hérite, séparés par des virgules (le premier est prioritaire). |

Retour à l'[index de la référence](README.md).
