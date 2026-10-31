<!-- Page générée par doc/tools/gen_reference.py depuis le code : ne pas modifier à la main. -->


# Période de temps (timeperiod)

Directives acceptées dans un bloc `define timeperiod { ... }`. Une directive absente prend la valeur par défaut indiquée ; « obligatoire » signifie qu'aucune valeur par défaut n'est prévue : la définir (directement ou par un modèle), sauf si la description indique qu'elle est déduite.

| Directive | Type | Défaut | Description |
|---|---|---|---|
| `alias` | texte |  | Nom long affiché dans les interfaces. |
| `dateranges` | liste |  | Plages de dates et d'heures (lignes « monday 09:00-18:00 », « 2027-03-29 00:00-24:00 »…). |
| `definition_order` | entier | `100` |  |
| `exclude` | liste |  | Périodes retirées de celle-ci (ex. jours fériés). |
| `imported_from` | texte | `unknown` | Renseigné automatiquement : fichier source de la définition. |
| `is_active` | booléen (0/1) | 0 |  |
| `name` | texte |  | Nom du modèle, utilisé par « use » dans les autres objets. |
| `register` | entier | `1` | 0 = l'objet est un modèle et n'est pas instancié. |
| `timeperiod_name` | texte | **obligatoire** | Nom unique de la période. |
| `use` | texte |  | Modèle(s) dont l'objet hérite, séparés par des virgules (le premier est prioritaire). |

Retour à l'[index de la référence](README.md).
