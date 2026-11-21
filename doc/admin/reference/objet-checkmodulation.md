<!-- Page générée par doc/tools/gen_reference.py depuis le code : ne pas modifier à la main. -->


# Modulation de check (checkmodulation)

Directives acceptées dans un bloc `define checkmodulation { ... }`. Une directive absente prend la valeur par défaut indiquée ; « obligatoire » signifie qu'aucune valeur par défaut n'est prévue : la définir (directement ou par un modèle), sauf si la description indique qu'elle est déduite.

| Directive | Type | Défaut | Description |
|---|---|---|---|
| `check_command` | texte | **obligatoire** | Commande de check et ses arguments séparés par « ! » (ex. check_tcp!443). |
| `check_period` | texte | **obligatoire** | Période pendant laquelle les checks actifs sont exécutés. |
| `checkmodulation_name` | texte | **obligatoire** |  |
| `definition_order` | entier | `100` |  |
| `imported_from` | texte | `unknown` | Renseigné automatiquement : fichier source de la définition. |
| `name` | texte |  | Nom du modèle, utilisé par « use » dans les autres objets. |
| `register` | booléen (0/1) | 1 | 0 = l'objet est un modèle et n'est pas instancié. |
| `use` | liste |  | Modèle(s) dont l'objet hérite, séparés par des virgules (le premier est prioritaire). |

Retour à l'[index de la référence](README.md).
