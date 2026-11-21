<!-- Page générée par doc/tools/gen_reference.py depuis le code : ne pas modifier à la main. -->


# Dépendance d'hôte (hostdependency)

Directives acceptées dans un bloc `define hostdependency { ... }`. Une directive absente prend la valeur par défaut indiquée ; « obligatoire » signifie qu'aucune valeur par défaut n'est prévue : la définir (directement ou par un modèle), sauf si la description indique qu'elle est déduite.

| Directive | Type | Défaut | Description |
|---|---|---|---|
| `definition_order` | entier | `100` |  |
| `dependency_period` | texte |  | Période pendant laquelle la dépendance s'applique. |
| `dependent_host_name` | texte | **obligatoire** | Hôte(s) dépendant(s). |
| `dependent_hostgroup_name` | texte |  | Groupe(s) d'hôtes dépendant(s). |
| `execution_failure_criteria` | liste | `n` | États du maître qui suspendent les checks du dépendant (o,d,u,p,n ou o,w,u,c,p,n). |
| `host_name` | texte | **obligatoire** | Nom unique de l'hôte (pour un service : hôte(s) auquel il est rattaché). |
| `hostgroup_name` | texte |  | Groupe(s) d'hôtes auxquels le service est appliqué. |
| `imported_from` | texte | `unknown` | Renseigné automatiquement : fichier source de la définition. |
| `inherits_parent` | booléen (0/1) | 0 | Le dépendant hérite aussi des dépendances du maître. |
| `name` | texte |  | Nom du modèle, utilisé par « use » dans les autres objets. |
| `notification_failure_criteria` | liste | `n` | États du maître qui suspendent les notifications du dépendant. |
| `register` | booléen (0/1) | 1 | 0 = l'objet est un modèle et n'est pas instancié. |
| `use` | liste |  | Modèle(s) dont l'objet hérite, séparés par des virgules (le premier est prioritaire). |

Retour à l'[index de la référence](README.md).
