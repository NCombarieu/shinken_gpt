# Protocole entre daemons

**Public :** développeur.

## Transport

- **HTTP/1.1** sur les ports des daemons (7768 à 7773 par défaut, directive
  `port` des `.ini` et des définitions de daemons).
- Serveur : Bottle sur Cheroot (`shinken/http_daemon.py`). La directive
  `http_backend` est conservée pour compatibilité mais ignorée.
- Client : pycurl (`shinken/http_client.py`), connexions persistantes,
  délais `timeout` (test de vie) et `data_timeout` (envoi de données).
- TLS optionnel (`use_ssl`, `ca_cert`, `server_cert`, `server_key`) ; pas
  d'authentification des clients.

## Routes

`HTTPDaemon.register(obj)` publie chaque méthode publique de l'objet
interface sous `/<nom>` et `/<nom-avec-tirets>` (ex. `/get_checks` et
`/get-checks`). Le verbe est donné par l'attribut `method` de la méthode
(`get` par défaut, `post` pour les envois de données).

| Route | Verbe | Servie par | Appelée par | Rôle |
|---|---|---|---|---|
| `/ping` | GET | tous | arbiter, sondes | test de vie (renvoie `"pong"`) |
| `/put_conf` | POST | tous sauf arbiter maître | arbiter | envoi de la configuration |
| `/have_conf`, `/wait_new_conf`, `/what_i_managed`, `/remove_from_conf` | GET | satellites | arbiter | suivi de la répartition |
| `/get_checks` | GET | scheduler | poller, reactionner | travail à faire |
| `/put_results` | POST | scheduler | poller, reactionner | résultats |
| `/push_actions`, `/get_returns` | POST / GET | poller, reactionner passifs | scheduler | mode passif |
| `/get_broks` | GET | scheduler, satellites | broker | broks en attente |
| `/push_broks` | POST | broker | arbiter | broks de l'arbiter |
| `/get_external_commands` | GET | broker, satellites | arbiter | commandes externes reçues |
| `/run_external_commands` | POST | scheduler | arbiter | commandes à appliquer |
| `/get_running_id` | GET | tous | arbiter, satellites | détecte un redémarrage |
| `/api`, `/api_full` | GET | tous | humains | liste des routes |

## Sérialisation

| Sens | Format |
|---|---|
| arguments d'un `POST` | formulaire multipart, un champ par argument : `base64(zlib(pickle(valeur)))` |
| réponses volumineuses (`get_checks`, `get_broks`, `get_returns`) | `base64(zlib(pickle(objet)))`, `application/octet-stream` |
| autres réponses | JSON |

Côté réception, la désérialisation passe toujours par
`SafeUnpickler.loads()` (`shinken/safepickle.py`), qui n'accepte qu'une liste
de classes autorisées : les objets Shinken attendus et quelques types de la
bibliothèque standard. Les noms de modules Python 2 présents dans d'anciens
flux (`copy_reg`, `__builtin__`) sont traduits.

> **Attention** — N'utilisez jamais `pickle.loads` directement sur une
> donnée reçue du réseau : un pickle forgé exécute du code. Toute nouvelle
> route qui reçoit des objets doit passer par `SafeUnpickler`, et toute
> nouvelle classe transmise doit être ajoutée explicitement à la liste
> blanche.

## Incompatibilité avec Shinken master

Shinken 2.4 (Python 2) envoie ses données en `PUT` avec un corps
`zlib(pickle)` au format Python 2. Les deux versions ne peuvent pas
dialoguer : une installation se migre en remplaçant **tous** les daemons en
même temps (voir le [guide de migration](../migration-depuis-shinken-master.md)).

## Sécurité

Pas d'authentification : un client qui joint un port peut lire la
configuration ou en pousser une. Le déploiement suppose un **réseau privé**
(voir [sécurité](../exploitation/09-securite.md)).
