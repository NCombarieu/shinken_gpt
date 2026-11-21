<!-- Page générée par doc/tools/gen_reference.py depuis le code : ne pas modifier à la main. -->


# Module (module)

Directives acceptées dans un bloc `define module { ... }`. Une directive absente prend la valeur par défaut indiquée ; « obligatoire » signifie qu'aucune valeur par défaut n'est prévue : la définir (directement ou par un modèle), sauf si la description indique qu'elle est déduite.

| Directive | Type | Défaut | Description |
|---|---|---|---|
| `definition_order` | entier | `100` |  |
| `imported_from` | texte | `unknown` | Renseigné automatiquement : fichier source de la définition. |
| `module_name` | texte | **obligatoire** | Nom unique du module, référencé par la directive modules des daemons. |
| `module_type` | texte | **obligatoire** | Fait exécuter la commande par un module du poller ou du reactionner au lieu d'un processus. |
| `modules` | liste |  | Modules chargés (noms définis par module_name). |
| `name` | texte |  | Nom du modèle, utilisé par « use » dans les autres objets. |
| `register` | booléen (0/1) | 1 | 0 = l'objet est un modèle et n'est pas instancié. |
| `use` | liste |  | Modèle(s) dont l'objet hérite, séparés par des virgules (le premier est prioritaire). |

Retour à l'[index de la référence](README.md).
