# Journalisation

**Public :** développeur. Pour l'exploitation, voir [journaux](../exploitation/08-logs.md).

## Ce qui existe réellement

| Mécanisme | Code | Réglage |
|---|---|---|
| logger historique `Shinken` (couleurs, préfixe horodaté) | `shinken/log.py` (`logger`) | `log_level` des `.ini` et de `shinken.cfg` |
| journal local par daemon, rotation quotidienne à minuit, 5 fichiers conservés | `shinken/log.py` (`TimedRotatingFileHandler`) | `use_local_log`, `local_log` des `.ini` ; `local_log` de `shinken.cfg` |
| journaux structurés (texte ou JSON) sur la sortie | `shinken/structured_logging.py` (`setup_logging`) | options `--verbose`, `--debug`, `--json-logs`, `--logfile` |
| historique de supervision (alertes, notifications) | broks `log` → module `logstore_sqlite` | `etc/modules/logstore-sqlite.cfg` |

Les options de ligne de commande sont ajoutées à chaque daemon par
`shinken/bin_utils.py` (`add_logging_options`) et appliquées par
`setup_logging_from_options` :

| Option | Niveau / effet |
|---|---|
| (aucune) | WARNING |
| `--verbose` | INFO |
| `--debug` | DEBUG |
| `--json-logs` | `StructuredFormatter` : un objet JSON par ligne |
| `--logfile FICHIER` | ajoute un fichier de sortie |

Format JSON :

```json
{"timestamp": "2026-10-31 10:00:00,123", "daemon": "shinken-scheduler",
 "level": "WARNING", "logger": "Shinken", "message": "...",
 "module": "scheduler", "function": "run", "line": 1708}
```

Il n'y a **pas** de fichier `logging.cfg` ni de variable d'environnement
pour activer le JSON : seules les options ci-dessus existent.

## Écrire dans les journaux

```python
from shinken.log import logger

logger.info("[MonModule] démarré")
logger.warning("[MonModule] cible %s injoignable", cible)
```

- Utilisez le formatage paresseux (`logger.info("… %s", valeur)`), pas
  d'f-string, pour ne pas formater les messages filtrés.
- Préfixez par le nom du composant entre crochets.
- Pas de secret dans les journaux (mots de passe, jetons, lignes de
  commande de notification contenant des identifiants).

`naglog_result()` (`shinken/log.py`) produit les lignes au format Nagios
(`SERVICE ALERT: …`, `HOST NOTIFICATION: …`) qui deviennent des broks `log`
et alimentent l'historique de Livestatus.
