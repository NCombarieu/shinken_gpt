<!-- Page générée par doc/tools/gen_reference.py depuis le code : ne pas modifier à la main. -->


# Groupe d'hôtes (hostgroup)

Directives acceptées dans un bloc `define hostgroup { ... }`. Une directive absente prend la valeur par défaut indiquée ; « obligatoire » signifie qu'aucune valeur par défaut n'est prévue : la définir (directement ou par un modèle), sauf si la description indique qu'elle est déduite.

| Directive | Type | Défaut | Description |
|---|---|---|---|
| `action_url` | texte |  | URL d'action, affichée dans les interfaces. |
| `alias` | texte | **obligatoire** | Nom long affiché dans les interfaces. |
| `definition_order` | entier | `100` |  |
| `hostgroup_members` | texte | **obligatoire** | Groupes d'hôtes inclus dans ce groupe. |
| `hostgroup_name` | texte | **obligatoire** | Nom unique du groupe. |
| `imported_from` | texte | `unknown` | Renseigné automatiquement : fichier source de la définition. |
| `members` | liste |  | Membres du groupe (pour un groupe de services : couples hôte,service). |
| `name` | texte |  | Nom du modèle, utilisé par « use » dans les autres objets. |
| `notes` | texte |  | Texte libre affiché dans les interfaces. |
| `notes_url` | texte |  | URL d'une documentation, affichée dans les interfaces. |
| `realm` | texte |  | Realm auquel l'objet appartient (supervision distribuée). |
| `register` | booléen (0/1) | 1 | 0 = l'objet est un modèle et n'est pas instancié. |
| `unknown_members` | liste |  |  |
| `use` | liste |  | Modèle(s) dont l'objet hérite, séparés par des virgules (le premier est prioritaire). |

Retour à l'[index de la référence](README.md).
