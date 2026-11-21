# Pièges du portage Python 3 (historique)

**Public :** développeur. Problèmes réels rencontrés et corrigés pendant le
portage ; utile avant de toucher au cœur des daemons ou à Livestatus. Les
corrections ultérieures sont listées dans le [Changelog](../../Changelog).

## Deadlock au fork des modules externes

`BaseModule._main()` arrêtait, dans le processus fils d'un module externe,
le serveur HTTP hérité du parent ; l'arrêt attendait des threads qui
n'existent que dans le parent et bloquait indéfiniment. Symptôme : le module
annonce son démarrage puis ne fait plus rien. Le fils abandonne désormais sa
copie inerte du serveur sans l'arrêter. Même classe de bug corrigée dans
`shinken/worker.py`.

## Commandes externes perdues en silence

- `satellitelink.get_external_commands()` faisait `loads(str(octets))` sur
  des `bytes` : l'exception était avalée par un `except:` nu.
- Le broker n'avait pas de méthode `get_external_commands()` (il n'hérite
  pas de `Satellite`).
- Thruk envoie `RESTART_PROCESS`, inconnu : ajouté comme alias de
  `RESTART_PROGRAM`.

Leçon : pas de `except:` nu autour d'une désérialisation ; journaliser.

## Désérialisation non protégée

Six points d'entrée réseau utilisaient `pickle` directement au lieu de
`SafeUnpickler` (résultats des pollers, broks, configuration poussée,
actions, commandes externes). Les brancher a révélé un second bug dans la
protection : les noms de modules Python 2 (`copy_reg`, `__builtin__`)
étaient importés tels quels ; une table d'alias les traduit
(`copyreg`, `builtins`).

## Restes de Python 2 sur des chemins rarement exécutés

- `long(value)` dans les commandes `CHANGE_*_MODATTR` ;
- `sys.maxint` dans la découverte ;
- `os.errno.EINTR` dans Livestatus (l'erreur masquait l'erreur d'origine) ;
- `Host.display_name` sans valeur par défaut (colonne vide dans Thruk).

Recherche systématique :

```bash
grep -rnE "\.iteritems\(|\.itervalues\(|basestring|sys\.maxint|os\.errno|raw_input\(|__metaclass__|\blong\(" \
    shinken/ modules/ --include='*.py'
```

Vérifier chaque résultat : des alias de compatibilité existent encore
(`cPickle` comme nom de `pickle`, par exemple).

## `bytes` et `str`

Les frontières réseau (sockets, HTTP, sous-processus des plugins) manipulent
des `bytes` ; le reste du code des `str`. Décoder une seule fois, à la
frontière, en UTF-8 avec une politique d'erreur explicite. La sortie des
plugins est décodée en UTF-8 en ignorant les octets invalides
(`shinken/util.py`).

## Expressions régulières

Les motifs sans préfixe `r''` contenant `\d`, `\s`… produisent un
`SyntaxWarning` depuis Python 3.12 et deviendront des erreurs : toujours
écrire `re.compile(r"…")`.
