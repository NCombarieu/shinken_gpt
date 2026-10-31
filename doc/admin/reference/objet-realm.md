<!-- Page générée par doc/tools/gen_reference.py depuis le code : ne pas modifier à la main. -->


# Realm (realm)

Directives acceptées dans un bloc `define realm { ... }`. Une directive absente prend la valeur par défaut indiquée ; « obligatoire » signifie qu'aucune valeur par défaut n'est prévue : la définir (directement ou par un modèle), sauf si la description indique qu'elle est déduite.

| Directive | Type | Défaut | Description |
|---|---|---|---|
| `broker_complete_links` | booléen (0/1) | 0 |  |
| `default` | booléen (0/1) | 0 | Realm par défaut des objets qui n'en précisent pas. |
| `definition_order` | entier | `100` |  |
| `higher_realms` | liste |  |  |
| `imported_from` | texte | `unknown` | Renseigné automatiquement : fichier source de la définition. |
| `members` | liste |  | Membres du groupe (pour un groupe de services : couples hôte,service). |
| `name` | texte |  | Nom du modèle, utilisé par « use » dans les autres objets. |
| `realm_members` | liste |  | Sous-realms de ce realm. |
| `realm_name` | texte | **obligatoire** | Nom unique du realm. |
| `register` | booléen (0/1) | 1 | 0 = l'objet est un modèle et n'est pas instancié. |
| `unknown_members` | liste |  |  |
| `use` | liste |  | Modèle(s) dont l'objet hérite, séparés par des virgules (le premier est prioritaire). |

Retour à l'[index de la référence](README.md).
