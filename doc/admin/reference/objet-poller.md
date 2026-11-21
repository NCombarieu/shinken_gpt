<!-- Page générée par doc/tools/gen_reference.py depuis le code : ne pas modifier à la main. -->


# Daemon poller (poller)

Directives acceptées dans un bloc `define poller { ... }`. Une directive absente prend la valeur par défaut indiquée ; « obligatoire » signifie qu'aucune valeur par défaut n'est prévue : la définir (directement ou par un modèle), sauf si la description indique qu'elle est déduite.

| Directive | Type | Défaut | Description |
|---|---|---|---|
| `address` | texte | `localhost` | Adresse IP ou nom DNS utilisé par les checks ($HOSTADDRESS$). |
| `check_interval` | entier | `60` | Secondes entre deux tests de vie du daemon par l'arbiter. |
| `data_timeout` | entier | `120` | Délai (secondes) des envois de données. |
| `definition_order` | entier | `100` |  |
| `harakiri_threshold` | texte |  |  |
| `hard_ssl_name_check` | booléen (0/1) | 1 | Vérifie le nom du certificat présenté. |
| `imported_from` | texte | `unknown` | Renseigné automatiquement : fichier source de la définition. |
| `manage_arbiters` | booléen (0/1) | 0 | Ce broker reçoit aussi les broks de l'arbiter. |
| `manage_sub_realms` | booléen (0/1) | 1 | Prend aussi en charge les sous-realms. |
| `max_check_attempts` | entier | `3` | Tests de vie en échec avant de déclarer le daemon mort. |
| `max_q_size` | entier | `0` |  |
| `max_workers` | entier | `30` | Nombre maximal de processus d'exécution (0 = un par processeur). |
| `min_workers` | entier | `0` | Nombre minimal de processus d'exécution (0 = un par processeur). |
| `modules` | liste |  | Modules chargés (noms définis par module_name). |
| `name` | texte |  | Nom du modèle, utilisé par « use » dans les autres objets. |
| `passive` | booléen (0/1) | 0 | Le daemon ne se connecte pas aux schedulers : c'est le scheduler qui lui pousse le travail. |
| `poller_name` | texte | **obligatoire** |  |
| `poller_tags` | liste | `None` | Tags traités par ce poller (« None » = objets sans tag). |
| `polling_interval` | entier | `1` | Secondes entre deux demandes de travail au scheduler. |
| `port` | entier | `7771` | Port TCP du daemon. |
| `processes_by_worker` | entier | `256` | Nombre de checks traités en parallèle par processus. |
| `q_factor` | entier | `0` |  |
| `realm` | texte |  | Realm auquel l'objet appartient (supervision distribuée). |
| `register` | booléen (0/1) | 1 | 0 = l'objet est un modèle et n'est pas instancié. |
| `results_batch` | entier | `0` |  |
| `satellitemap` | dictionnaire |  | Adresses à utiliser pour joindre les satellites (NAT). |
| `spare` | booléen (0/1) | 0 | 1 = daemon de secours, activé si le daemon principal tombe. |
| `timeout` | entier | `3` | Délai (secondes) d'un test de vie. |
| `use` | liste |  | Modèle(s) dont l'objet hérite, séparés par des virgules (le premier est prioritaire). |
| `use_ssl` | booléen (0/1) | 0 | Chiffre les échanges avec ce daemon (nécessite une vraie PKI). |
| `use_timezone` | texte | `NOTSET` |  |

Retour à l'[index de la référence](README.md).
