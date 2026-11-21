<!-- Page générée par doc/tools/gen_reference.py depuis le code : ne pas modifier à la main. -->


# Commande (command)

Directives acceptées dans un bloc `define command { ... }`. Une directive absente prend la valeur par défaut indiquée ; « obligatoire » signifie qu'aucune valeur par défaut n'est prévue : la définir (directement ou par un modèle), sauf si la description indique qu'elle est déduite.

| Directive | Type | Défaut | Description |
|---|---|---|---|
| `command_line` | texte | **obligatoire** | Ligne exécutée ; macros ($HOSTADDRESS$, $ARG1$, $USER1$…) remplacées avant exécution. |
| `command_name` | texte | **obligatoire** | Nom unique de la commande, utilisé dans check_command, event_handler… |
| `definition_order` | entier | `100` |  |
| `enable_environment_macros` | booléen (0/1) | 0 | Exporter les macros en variables d'environnement pour cette commande. |
| `imported_from` | texte | `unknown` | Renseigné automatiquement : fichier source de la définition. |
| `module_type` | texte |  | Fait exécuter la commande par un module du poller ou du reactionner au lieu d'un processus. |
| `name` | texte |  | Nom du modèle, utilisé par « use » dans les autres objets. |
| `poller_tag` | texte | `None` | Seuls les pollers portant ce tag exécutent les checks de l'objet. |
| `priority` | entier | `100` |  |
| `reactionner_tag` | texte | `None` | Seuls les reactionners portant ce tag exécutent les notifications et event handlers. |
| `register` | booléen (0/1) | 1 | 0 = l'objet est un modèle et n'est pas instancié. |
| `timeout` | entier | `-1` | Durée maximale d'exécution en secondes (-1 = valeur globale). |
| `use` | liste |  | Modèle(s) dont l'objet hérite, séparés par des virgules (le premier est prioritaire). |

Retour à l'[index de la référence](README.md).
