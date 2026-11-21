<!-- Page générée par doc/tools/gen_reference.py depuis le code : ne pas modifier à la main. -->


# Exécution de découverte (discoveryrun)

Directives acceptées dans un bloc `define discoveryrun { ... }`. Une directive absente prend la valeur par défaut indiquée ; « obligatoire » signifie qu'aucune valeur par défaut n'est prévue : la définir (directement ou par un modèle), sauf si la description indique qu'elle est déduite.

| Directive | Type | Défaut | Description |
|---|---|---|---|
| `definition_order` | entier | `100` |  |
| `discoveryrun_command` | texte | **obligatoire** |  |
| `discoveryrun_name` | texte | **obligatoire** |  |
| `imported_from` | texte | `unknown` | Renseigné automatiquement : fichier source de la définition. |
| `name` | texte |  | Nom du modèle, utilisé par « use » dans les autres objets. |
| `register` | booléen (0/1) | 1 | 0 = l'objet est un modèle et n'est pas instancié. |
| `use` | liste |  | Modèle(s) dont l'objet hérite, séparés par des virgules (le premier est prioritaire). |

Retour à l'[index de la référence](README.md).
