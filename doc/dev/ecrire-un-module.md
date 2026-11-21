# Écrire un module

**Public :** développeur.

Un module ajoute une fonction à un daemon sans modifier le cœur : export de
données, stockage, réception de commandes… Les modules livrés sont dans
`modules/` ; `modules/dummy_*` sont des exemples minimaux.

## Structure

```
modules/mon_module/
├── __init__.py        # peut simplement réexporter properties et get_instance
└── module.py
```

`module.py` expose deux éléments :

```python
from shinken.basemodule import BaseModule
from shinken.log import logger

properties = {
    'daemons': ['broker'],        # daemons qui peuvent le charger
    'type': 'mon_module',         # valeur de « module_type » dans la configuration
    'external': False,            # True : processus séparé
    'phases': ['running'],        # facultatif ; voir ci-dessous
}


def get_instance(mod_conf):
    """Appelée par le gestionnaire de modules avec la définition « define module »."""
    return MonModule(mod_conf)


class MonModule(BaseModule):
    def __init__(self, mod_conf):
        BaseModule.__init__(self, mod_conf)
        # Les paramètres de « define module » sont des attributs de mod_conf
        self.cible = getattr(mod_conf, 'cible', 'localhost')

    def init(self):
        """Appelée une fois, après le chargement."""
        logger.info("[MonModule] initialisé, cible %s", self.cible)

    def manage_service_check_result_brok(self, brok):
        """Appelée pour chaque brok de type service_check_result."""
        data = brok.data
        logger.debug("[MonModule] %s/%s -> %s", data['host_name'],
                     data['service_description'], data['state'])
```

Configuration correspondante :

```
define module {
    module_name     mon-module
    module_type     mon_module
    cible           collecteur.example.com
}
```

puis `modules mon-module` dans la définition du daemon (par exemple
`etc/brokers/broker-master.cfg`).

## Interne ou externe

| | Interne (`external: False`) | Externe (`external: True`) |
|---|---|---|
| exécution | dans le processus du daemon | processus fils (`BaseModule.start()`) |
| interface | méthodes appelées par le daemon (hooks, `manage_brok`) | `main()` ou `do_loop_turn()`, échanges par `self.to_q` / `self.from_q` |
| risque | une exception ou une lenteur bloque le daemon | isolé ; redémarré s'il meurt |
| exemples | `retention_pickle`, `status_webui` | `livestatus`, `named_pipe` |

Un module externe ne doit rien attendre du serveur HTTP hérité du parent
(voir `BaseModule._main()`).

## Points d'accroche (hooks)

Le daemon appelle `hook_<nom>(daemon)` sur chaque module qui la définit
(`Daemon.hook_point`, `Scheduler.hook_point`). Une exception désactive le
module et le programme pour un redémarrage.

| Hook | Daemon | Moment |
|---|---|---|
| `hook_read_configuration` | arbiter | après la lecture de la configuration |
| `hook_early_configuration` / `hook_late_configuration` | arbiter | avant / après la création des objets |
| `hook_load_retention` | scheduler | à la réception d'une configuration |
| `hook_save_retention` | scheduler | périodiquement et à l'arrêt |
| `hook_pre_scheduler_mod_start` | scheduler | avant le démarrage des modules externes |
| `hook_tick` | arbiter, broker, satellites | à chaque tour de boucle |
| `hook_get_new_actions` | scheduler | avant de planifier les nouvelles actions |

Pour un module de broker, `manage_brok(brok)` est appelée pour chaque brok
et redirige vers `manage_<type>_brok` si la méthode existe (types courants :
`initial_host_status`, `host_check_result`, `service_check_result`,
`update_service_status`, `log`, `program_status`).

## Tests

Ajoutez un test `test/test_mod_<nom>.py` (pytest) qui instancie le module
avec un faux `mod_conf` et vérifie son comportement ; voir les tests
existants des modules livrés. Lancez `python -m pytest -q test`.

## Bonnes pratiques

- Python 3 uniquement, bibliothèque standard autant que possible (toute
  dépendance doit être ajoutée à l'image).
- Ne jamais bloquer un module interne : pas d'appel réseau long dans
  `manage_brok`, utiliser une file et un thread, ou un module externe.
- Journaliser avec `shinken.log.logger`, préfixe `[NomDuModule]`.
- Écritures de fichiers atomiques (fichier temporaire puis `os.replace`).
- Désérialisation : jamais de `pickle.loads` sur une donnée externe.
