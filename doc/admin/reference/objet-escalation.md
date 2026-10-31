<!-- Page générée par doc/tools/gen_reference.py depuis le code : ne pas modifier à la main. -->


# Escalade (escalation)

Directives acceptées dans un bloc `define escalation { ... }`. Une directive absente prend la valeur par défaut indiquée ; « obligatoire » signifie qu'aucune valeur par défaut n'est prévue : la définir (directement ou par un modèle), sauf si la description indique qu'elle est déduite.

| Directive | Type | Défaut | Description |
|---|---|---|---|
| `contact_groups` | liste |  | Groupes de contacts notifiés et autorisés à voir l'objet. |
| `contacts` | liste |  | Contacts notifiés et autorisés à voir l'objet. |
| `definition_order` | entier | `100` |  |
| `escalation_name` | texte | **obligatoire** | Nom unique de l'escalade. |
| `escalation_options` | liste | `d,u,r,w,c` | États concernés par l'escalade. |
| `escalation_period` | texte |  | Période pendant laquelle l'escalade s'applique. |
| `first_notification` | entier | **obligatoire** | Numéro de la première notification concernée. |
| `first_notification_time` | entier | **obligatoire** | Minutes de problème à partir desquelles l'escalade s'applique. |
| `imported_from` | texte | `unknown` | Renseigné automatiquement : fichier source de la définition. |
| `last_notification` | entier | **obligatoire** | Numéro de la dernière notification concernée (0 = sans fin). |
| `last_notification_time` | entier | **obligatoire** | Minutes de problème après lesquelles l'escalade cesse (0 = sans fin). |
| `name` | texte |  | Nom du modèle, utilisé par « use » dans les autres objets. |
| `notification_interval` | entier | `-1` | Minutes entre deux rappels de notification (0 = une seule notification). |
| `register` | booléen (0/1) | 1 | 0 = l'objet est un modèle et n'est pas instancié. |
| `use` | liste |  | Modèle(s) dont l'objet hérite, séparés par des virgules (le premier est prioritaire). |

Retour à l'[index de la référence](README.md).
