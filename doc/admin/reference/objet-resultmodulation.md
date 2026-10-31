<!-- Page générée par doc/tools/gen_reference.py depuis le code : ne pas modifier à la main. -->


# Modulation de résultat (resultmodulation)

Directives acceptées dans un bloc `define resultmodulation { ... }`. Une directive absente prend la valeur par défaut indiquée ; « obligatoire » signifie qu'aucune valeur par défaut n'est prévue : la définir (directement ou par un modèle), sauf si la description indique qu'elle est déduite.

| Directive | Type | Défaut | Description |
|---|---|---|---|
| `definition_order` | entier | `100` |  |
| `exit_code_modulation` | entier |  |  |
| `exit_codes_match` | liste d'entiers |  |  |
| `imported_from` | texte | `unknown` | Renseigné automatiquement : fichier source de la définition. |
| `modulation_period` | texte |  |  |
| `name` | texte |  | Nom du modèle, utilisé par « use » dans les autres objets. |
| `register` | booléen (0/1) | 1 | 0 = l'objet est un modèle et n'est pas instancié. |
| `resultmodulation_name` | texte | **obligatoire** |  |
| `use` | liste |  | Modèle(s) dont l'objet hérite, séparés par des virgules (le premier est prioritaire). |

Retour à l'[index de la référence](README.md).
