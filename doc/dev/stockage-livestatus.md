# Livestatus et stockage de l'historique

**Public :** développeur. Usage côté administrateur :
[Livestatus](../admin/26-livestatus.md).

## Ce qui existe

| Composant | Dossier | Rôle |
|---|---|---|
| module `livestatus` (externe, broker) | `modules/livestatus/` | serveur TCP (et socket Unix optionnelle), parseur LQL, état en mémoire |
| sous-module `logstore_sqlite` | `modules/logstore_sqlite/` | historique (`GET log`) dans une base **SQLite** |
| sous-module `logstore_null` | `modules/logstore_null/` | n'enregistre rien |

Il n'existe **aucun** stockage MySQL, Oracle, MongoDB ni autre : les fichiers
`shinken/db_mysql.py` et `shinken/db_oracle.py` sont des restes d'anciens
modules et ne sont utilisés par aucun module livré.

## Organisation de `modules/livestatus/`

| Fichier | Rôle |
|---|---|
| `module.py` | classe `LiveStatus_broker` : lecture de la configuration, chargement du sous-module de stockage, boucle principale, réception des broks |
| `livestatus_regenerator.py` | reconstruit en mémoire les objets (hôtes, services…) à partir des broks |
| `livestatus_client_thread.py` | un thread par connexion cliente |
| `livestatus_request.py`, `livestatus_query.py`, `livestatus_command_query.py`, `livestatus_wait_query.py` | analyse et exécution des requêtes `GET`, `COMMAND`, `WaitCondition` |
| `livestatus_constraints.py`, `livestatus_stack.py` | filtres et statistiques (`Filter`, `Stats`, `And`, `Or`) |
| `livestatus_response.py` | formats de sortie (CSV, JSON, Python) |
| `mapping.py` | correspondance colonnes Livestatus → attributs Shinken, par table |
| `log_line.py` | lignes d'historique (classes et types de messages) |

## Interface d'un logstore

Le module `livestatus` charge le sous-module déclaré par sa directive
`modules` (type `logstore_*`) et l'utilise pour :

- enregistrer chaque brok `log` (alertes, notifications, commandes…) ;
- répondre aux requêtes sur la table `log` (filtres traduits en SQL pour
  SQLite) ;
- purger les entrées plus anciennes que `max_logs_age`.

Paramètres de `logstore_sqlite` : `database_file`, `max_logs_age` (nombre
suivi de `d`, `w`, `m` ou `y`), `archive_path`. La base tolère des textes
non UTF-8 hérités d'une base produite par la version Python 2.

Si le sous-module déclaré est introuvable, `livestatus` se rabat sur
`logstore_null` et journalise une erreur explicite.

## Modifier ou ajouter des colonnes

1. Ajouter l'entrée dans `mapping.py` (table, nom de colonne, type,
   attribut ou fonction source).
2. Vérifier que l'attribut est bien transmis par les broks (propriétés avec
   `fill_brok` dans `shinken/objects/`).
3. Ajouter un test de requête.
