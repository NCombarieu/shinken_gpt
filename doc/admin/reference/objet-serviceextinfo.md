<!-- Page générée par doc/tools/gen_reference.py depuis le code : ne pas modifier à la main. -->


# Informations étendues de service (serviceextinfo)

Directives acceptées dans un bloc `define serviceextinfo { ... }`. Une directive absente prend la valeur par défaut indiquée ; « obligatoire » signifie qu'aucune valeur par défaut n'est prévue : la définir (directement ou par un modèle), sauf si la description indique qu'elle est déduite.

| Directive | Type | Défaut | Description |
|---|---|---|---|
| `definition_order` | entier | `100` |  |
| `host_name` | texte | **obligatoire** | Nom unique de l'hôte (pour un service : hôte(s) auquel il est rattaché). |
| `icon_image` | texte |  | Image affichée dans les interfaces. |
| `icon_image_alt` | texte |  |  |
| `imported_from` | texte | `unknown` | Renseigné automatiquement : fichier source de la définition. |
| `name` | texte |  | Nom du modèle, utilisé par « use » dans les autres objets. |
| `notes` | texte |  | Texte libre affiché dans les interfaces. |
| `notes_url` | texte |  | URL d'une documentation, affichée dans les interfaces. |
| `register` | booléen (0/1) | 1 | 0 = l'objet est un modèle et n'est pas instancié. |
| `service_description` | texte | **obligatoire** | Nom du service, unique pour un hôte. Caractères interdits : voir illegal_object_name_chars. |
| `use` | liste |  | Modèle(s) dont l'objet hérite, séparés par des virgules (le premier est prioritaire). |

Retour à l'[index de la référence](README.md).
