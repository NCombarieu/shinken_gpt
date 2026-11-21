# Revue 01 — Qualité du code et du portage Python 3

Branche `modernize/podman-python3` @ `6c25f5a` — périmètre : code Python (shinken/, bin/, modules/, libexec/, cli/), tests, sérialisation inter-daemons.
Aucun fichier du dépôt n'a été modifié : tout a été exécuté sur une copie `git archive HEAD` dans
`<scratch>/code/repo` (venv Python 3.13.18 dans `.../review/code/venv`).

Légende : **[VÉRIFIÉ]** = reproduit par exécution (commande fournie) ; **[LU]** = constaté à la lecture du code, non exécuté ; **[SUPPOSÉ]** = hypothèse plausible non démontrée.

---

## 1. Résumé

**Note : 4/10. Verdict : NON, la branche ne peut pas remplacer en production un Shinken master (Python 2) en l'état.**

Le cœur « nominal » (lecture de conf UTF-8, ordonnancement, checks actifs, broks, échanges HTTP/pickle entre daemons actifs) fonctionne sous Python 3.13 et la suite de tests est verte (668 passés / 0 échec / 7 skippés). Mais une suite verte ne suffit pas ici :

- la suite **masque un vrai crash de production** par un monkeypatch dans `test/conftest.py` (Daterange `int < None`) ;
- plusieurs chemins classiques en production plantent sous Python 3 et ne sont pas couverts par les tests : **conf en latin-1**, **notifications e-mail** (script par défaut), **pollers/reactionners passifs**, **Livestatus avec le logstore-sqlite** activé par le dernier commit, **CLI `shinken`** et **`shinken-discovery`** (erreurs de syntaxe Python 2) ;
- les logs console sont imprimés sous la forme `b'...'` (repr de bytes).

Le travail de portage est sérieux sur les échanges inter-daemons (SafeUnpickler, base64/zlib, bytes HTTP), mais la CI ne voit pas les scripts sans extension `.py` (compileall/ruff) et l'audit de modernisation avale les `SyntaxError`, ce qui donne un faux sentiment de complétude.

| Gravité | Nombre |
|---|---|
| Bloquant | 5 |
| Majeur | 6 |
| Mineur | 10 |

---

## 2. Résultats des tests [VÉRIFIÉ]

Commande officielle (job `legacy-suite` de `.github/workflows/ci.yml`), exécutée depuis `test/` :

```
pip install -e . pytest pytest-timeout requests      # (dans le venv scratchpad)
cd test && python -m pytest -ra --timeout=60 --timeout-method=signal -q -p no:cacheprovider
=> 668 passed, 7 skipped, 865 warnings in 221.37s
```
Log complet : `<scratch>/code/pytest_full.log`

Aucun échec à analyser. Les 7 skips :

| Test | Raison donnée | Analyse |
|---|---|---|
| test_bad_start.py | « daemon startup lifecycle tests are pending Python 3 runtime migration » | **Trou de couverture important** : le démarrage réel des daemons (pid, ports, daemonisation) n'est pas testé. |
| test_scheduler_init.py | « still depends on the legacy daemon harness » | Idem : pas de test d'intégration du scheduler en processus. |
| test_module_as_package.py | import isolation non modernisée | Chargement de modules packagés non testé. |
| test_external_mapping.py | legacy désactivé | libexec non testé. |
| test_db.py / test_db_mysql.py | couche DB retirée | Acceptable si assumé. |
| test_sslv3_disabled.py | pyOpenSSL absent | Dépendance de test manquante ; HTTPS inter-daemons non testé. |

Avertissements : 49 `SyntaxWarning: invalid escape sequence` (dont 38 dans le code livré, voir M-1), 1 `DeprecationWarning: HTTPPOST is deprecated; use MIMEPOST` (pycurl, `shinken/http_client.py`), 2 `maxsplit positional`.

### 2.1 Test sans le monkeypatch de `conftest.py` [VÉRIFIÉ]

`test/conftest.py:70-90` (fixture `preserve_python2_daterange_none_semantics`, `autouse=True`) **remplace du code de production** (`Daterange.get_next_valid_time_from_t`) pendant les tests, pour contourner une comparaison `int < None` qui marchait en Python 2. Relance de la suite avec cette fixture désactivée (copie scratchpad uniquement) :

```
4 failed, 664 passed, 7 skipped
FAILED test_timeperiods.py::TestTimeperiods::test_simple_timeperiod - TypeError
FAILED test_timeperiods.py::TestTimeperiods::test_simple_timeperiod_with_exclude
FAILED test_timeperiods.py::TestTimeperiods::test_simple_with_multiple_time
FAILED test_timeperiods.py::TestTimeperiods::test_simple_with_multiple_time_mutltiple_days
```
Ces 4 échecs sont des **vrais bugs de production** (pas des tests cassés) : la suite de tests elle-même démontre le crash dès qu'on retire le patch.

=> Voir B-1. Un test qui patche le code testé ne prouve rien sur ce code.

---

## 3. Problèmes

### BLOQUANTS

#### B-1 — Crash `TypeError: '<' not supported between 'int' and 'NoneType'` dans les timeperiods avec une date fixe passée [VÉRIFIÉ]
- **Fichier** : `shinken/daterange.py:276-282` (`get_next_valid_time_from_t`), même motif `shinken/daterange.py:346-352` (`get_next_invalid_time_from_t`, [LU]).
- **Cas réel** : toute timeperiod contenant une plage calendaire échue (ex. exclusions de jours fériés `2023-12-25 00:00-24:00`, maintenances datées) — très courant en production.
- **Preuve** :
  ```
  python - <<'EOF'
  import time
  from shinken.objects.timeperiod import Timeperiod
  t = Timeperiod(); t.timeperiod_name='past'
  t.resolve_daterange(t.dateranges, '2010-01-01 - 2010-02-01 00:00-24:00')
  t.resolve_daterange(t.dateranges, 'monday 08:00-17:00')
  t.get_next_valid_time_from_t(time.time())
  EOF
  -> shinken/daterange.py:282  if t < t_day:  TypeError: '<' not supported between instances of 'int' and 'NoneType'
  ```
- **Masqué par** : `test/conftest.py:70-90` (monkeypatch autouse de la méthode de production).
- **Correctif** : déplacer le correctif du conftest dans le code : après `t_day = self.get_next_valid_day(t)`, `if t_day is None: return None` ; idem `t_day = self.get_next_invalid_day(t)` dans `get_next_invalid_time_from_t` (et protéger `get_next_future_timerange_*(t_day2)` contre `None`). Supprimer ensuite la fixture du conftest.

#### B-2 — Fichier de configuration non UTF-8 (latin-1) => l'arbiter plante au démarrage [VÉRIFIÉ]
- **Fichier** : `shinken/objects/config.py:880`, `:904`, `:942` — `io.open(..., encoding='utf8')` strict ; seul `IOError` est intercepté.
- **Régression vs master** : Shinken Py2 lisait en octets et décodait avec perte (`replace`) — les confs historiques en latin-1 (accents dans `alias`, `notes`, commentaires) chargeaient.
- **Preuve** : ajout d'un `hosts/latin1.cfg` contenant `alias Serveur d\xe9di\xe9` dans une copie de `etc/` puis `shinken-arbiter -v -c shinken.cfg` :
  ```
  File "shinken/objects/config.py", line 943, in read_config
      res.write(fd.read())
  UnicodeDecodeError: 'utf-8' codec can't decode byte 0xe9 in position 72
  ```
  (traceback brut, pas de message d'erreur de conf).
- **Correctif** : `io.open(path, encoding='utf-8', errors='replace')` (ou tentative UTF-8 puis repli `latin-1` avec avertissement indiquant le fichier) ; ajouter un test avec un fichier latin-1.

#### B-3 — Script de notification e-mail par défaut inutilisable [VÉRIFIÉ]
- **Fichier** : `libexec/notify_by_email.py:30` (`from email.MIMEImage import MIMEImage`, module Py2), plus `:217` et `:290` (`shinken_var.iteritems()`).
- **Impact** : les commandes livrées `notify-host-by-email` / `notify-service-by-email` (`etc/commands/*.cfg`, utilisées par `etc/notificationways/email.cfg`) échouent à chaque notification => **aucune alerte e-mail**.
- **Preuve** :
  ```
  python libexec/notify_by_email.py -t -n service -S localhost -r a@b.c -f txt -c "PROBLEM,,web01,,10.0.0.1,,now" -o "HTTP,,CRITICAL,,down,,5m"
  ModuleNotFoundError: No module named 'email.MIMEImage'
  ```
- **Correctif** : `from email.mime.image import MIMEImage` / `email.mime.text` / `email.mime.multipart`, `.items()` au lieu de `.iteritems()`, shebang `python3` ; ajouter un test en mode `-t`.

#### B-4 — Résultats des pollers/reactionners passifs toujours perdus [VÉRIFIÉ]
- **Fichier** : `shinken/scheduler.py:890-898`.
  ```python
  results = con.get('get_returns', {...}, wait='long')   # bytes (pickle brut)
  try:
      results = str(results)        # Py3 : "b'\\x80\\x04...'" -> repr textuel !
  ...
  results = SafeUnpickler.loads(results)   # -> UnpicklingError, loggé puis `continue`
  ```
- **Preuve** :
  ```
  python -c "import pickle; from shinken.safepickle import SafeUnpickler; SafeUnpickler.loads(str(pickle.dumps([])))"
  -> UnpicklingError: unpickling stack underflow
  ```
  Tous les résultats de checks d'un poller `passive 1` sont jetés (« Cannot load passive results from satellite »). Le même bug a été corrigé dans `shinken/objects/satellitelink.py:378-384` (commentaire explicite) mais pas ici. Le bloc reactionner (`scheduler.py:930-935`) est correct.
- **Correctif** : supprimer le bloc `str(results)` / `encode` ; passer directement les bytes à `SafeUnpickler.loads`. Ajouter un test HTTP passif.

#### B-5 — Livestatus casse avec la conf livrée par le dernier commit (logstore-sqlite inexistant) [VÉRIFIÉ]
- **Commit** `6c25f5a` : `etc/modules/livestatus.cfg` passe de `logstore-null` à `logstore-sqlite`, et ajoute `etc/modules/logstore-sqlite.cfg` (`module_type logstore_sqlite`). **Aucun module `logstore_sqlite` n'existe dans `modules/`** (`ls modules` : dummy_*, livestatus, logstore_null, status_webui) ; le `Containerfile` ne copie que `modules/`. Le message du commit (« enable structured event logging to SQLite ») ne correspond pas au contenu : il supprime aussi `shinken/misc/md5crypt.py` (non référencé, sans impact) et ne contient aucun code SQLite. Le broker livré charge `livestatus` (`etc/brokers/broker-master.cfg:41`).
- **Preuve** (reproduction des étapes de `LiveStatus_broker.main()`, `modules/livestatus/module.py:212-233`) :
  ```
  WARNING: The module type logstore-sqlite for logstore-sqlite was not found in modules!
  WARNING: The module type logstore-sqlite for LogStore was not found in modules!
  File "modules/livestatus/module.py", line 169, in add_compatibility_sqlite_module
      self.modules_manager.instances[0].load(self)
  IndexError: list index out of range
  ```
  L'exception survient avant le `try` de `main()` => le processus externe Livestatus meurt, le broker le relance en boucle ; Thruk/clients Livestatus sans données. (Le chargement complet dans un broker réel n'a pas été lancé — l'enchaînement est reproduit à l'identique hors broker.)
- **Correctif** : revenir à `logstore-null`, ou porter réellement le module `logstore_sqlite` (Python 3, `sqlite3` stdlib) avec tests ; dans `add_compatibility_sqlite_module`, vérifier `instances` non vide avant `[0]`.

### MAJEURS

#### M-1 — CLI `bin/shinken` et `bin/shinken-discovery` : erreurs de syntaxe Python 2 [VÉRIFIÉ]
- `bin/shinken:252` (`print ''`, `raw_input`), `bin/shinken-discovery:121` (`print "Macros", raw_macros`). `bin/shinken` est installé comme script (`setup.cfg:10`).
- **Preuve** : `python bin/shinken --help` -> `SyntaxError: Missing parentheses in call to 'print'` ; idem `shinken-discovery`.
- **Pourquoi la CI ne le voit pas** : `compileall` ne compile que les `*.py`, ruff ignore les fichiers sans extension, et `integration/modernization_audit.py:50` fait `except (OSError, SyntaxError, UnicodeDecodeError): return []` => les fichiers non parsables sont **silencieusement** ignorés.
- **Correctif** : porter les deux scripts ; dans la CI, ajouter `python -c "import ast,sys; [ast.parse(open(f).read(), f) for f in sys.argv[1:]]" bin/shinken*` ; faire échouer l'audit sur `SyntaxError`.

#### M-2 — Tous les logs console affichés en `b'...'` [VÉRIFIÉ]
- `shinken/misc/termcolor.py:139-141` : `if isinstance(text, unicode): text = text.encode("utf-8")` puis `print(colored(text,...))` => repr de bytes. Idem `shinken/log.py:89` (`print(msg.encode('ascii','ignore'))`).
- **Preuve** : `python -c "from shinken.log import logger; logger.setLevel('INFO'); logger.info('hello')"` -> `[95mb'[1793446028] INFO: [Shinken] hello'[0m`. Visible aussi dans toute la sortie de `shinken-arbiter -v`.
- **Impact** : `podman logs`, journald, agrégateurs : lignes polluées, `\t` littéraux, accents en `\xc3\xa9`.
- **Correctif** : supprimer l'encodage dans `cprint` ; dans `ColorStreamHandler`, ne coloriser que si `stream.isatty()`.

#### M-3 — Logs dupliqués (stdout + stderr) depuis le logging « structuré » [VÉRIFIÉ]
- `shinken/structured_logging.py:92-108` ajoute un handler sur le **logger racine** ; le logger `Shinken` (`shinken/log.py:238-245`) a déjà son handler et `propagate=True`. Chaque ligne sort deux fois, dans deux formats.
- **Preuve** : `setup_logging('x', level='WARNING'); logger.setLevel('INFO'); logger.info('hello-info')` -> 2 lignes (`b'... INFO: [Shinken] hello-info'` sur stdout, `[INFO    ] Shinken (log:info:223) hello-info` sur stderr). Le niveau `WARNING` par défaut du racine ne filtre rien (les handlers sont `NOTSET`).
- **Correctif** : soit `logging.getLogger('Shinken').propagate = False`, soit faire du handler structuré l'unique handler du logger `Shinken`. Après daemonisation (`-d`), le handler stderr pointe vers un fd fermé/redirigé [SUPPOSÉ : « --- Logging error --- »].

#### M-4 — Rechargement gracieux (`graceful_enabled`) : configuration lue en mode texte [VÉRIFIÉ]
- `shinken/daemon.py:420-422` : `raw_config = sys.stdin.read()` (str décodé) puis `SafeUnpickler.loads` (ré-encodage latin-1) => pickle corrompu.
- **Preuve** : `python -c "import pickle,sys; sys.stdout.buffer.write(pickle.dumps({'a':[1,'é']}))" | python -c "import sys; from shinken.safepickle import SafeUnpickler; SafeUnpickler.loads(sys.stdin.read())"` -> `UnicodeEncodeError: 'latin-1' codec can't encode character '\udc80'` (en locale UTF-8 stricte : `UnicodeDecodeError` dès la lecture).
- Option désactivée par défaut (`graceful_enabled` BoolProp default False) => Majeur et non Bloquant.
- **Correctif** : `sys.stdin.buffer.read()`.

#### M-5 — Gestion du named pipe (`command_file` / nagios.cmd) non portée [VÉRIFIÉ partiellement]
- `shinken/external_command.py:470-474` : `os.read()` renvoie des bytes, concaténés à `self.cmd_fragments = ''` (str). **Preuve** : FIFO créée et alimentée à la main -> `TypeError: can only concatenate str (not "bytes") to str`.
- `shinken/external_command.py:460-463` : `open(self.pipe_path, 'w+', os.O_NONBLOCK)` lève `io.UnsupportedOperation` (sous-classe d'OSError) puis le handler appelle `self.error(...)` qui n'existe pas -> `AttributeError` [VÉRIFIÉ]. `os.mkfifo(path, 660)` est en décimal (=0o1224), bug hérité.
- En pratique l'arbiter délègue le pipe à un module `named_pipe` (`config.py:1833-1845`), **absent de `modules/`** [VÉRIFIÉ par `ls`] : `command_file=` d'une conf master ne produit qu'un avertissement et les commandes externes via nagios.cmd ne sont pas reçues. Pour un remplacement « compatible Nagios » c'est une perte fonctionnelle (à recouper avec la revue compatibilité).
- **Correctif** : `cmd_fragments = b''` + décodage UTF-8 `errors='replace'` par ligne, `os.mkfifo(path, 0o660)`, `logger.error` ; porter/fournir le module `named_pipe` ou documenter l'alternative (Livestatus `COMMAND`, receiver HTTP).

#### M-6 — Interopérabilité de sérialisation avec un cluster Python 2 impossible [LU]
- Le protocole inter-daemons reste du pickle d'objets Python (`satellite.py:134,175,191`, `http_client.py:170`, `config.py:1332-1405`) avec `HIGHEST_PROTOCOL` (5) et modules `builtins`/`copyreg` : un daemon master Py2 ne peut pas lire ces flux, et inversement les noms de classes/attributs ont pu évoluer. => **pas de migration progressive daemon par daemon** : bascule complète obligatoire (point à transmettre à la revue compatibilité/déploiement).

### MINEURS

| # | Fichier:ligne | Constat | Preuve | Correctif |
|---|---|---|---|---|
| m-1 | `shinken/objects/timeperiod.py` (13), `config.py` (10), `macroresolver.py` (5), `external_command.py` (4), `util.py` (3), `dependencynode.py`, `objects/pack.py`, `libexec/external_mapping.py` | **38 `SyntaxWarning: invalid escape sequence`** dans 8 fichiers livrés (regex non raw, ex. `config.py:935` `"\.cfg$"`, `util.py:582-624`, `timeperiod.py:475-567`). Deviendra `SyntaxError` dans une future version de Python. Confirme le signalement de l'audit doc. | [VÉRIFIÉ] `compile()` avec `warnings.simplefilter('always')` sur shinken/ modules/ bin/ libexec/ cli/ | Préfixer `r''` ; ajouter `ruff --select W605` en CI. |
| m-2 | `shinken/safepickle.py:24-27`, `shinken/imports.py:3`, `config.py:44`, `satellite.py:53`, `daemon.py:61` | Alias `cPickle` résiduels : `try: import cPickle` (branche morte en Py3) et `pickle as cpickle` réimporté sous le nom `cPickle`. Sans impact fonctionnel, lisibilité trompeuse. Confirme le signalement de l'audit doc. | [LU] | `import pickle` direct. |
| m-3 | `libexec/link_vmware_host_vm.py:113`, `libexec/discovery/windows_shares_discovery_runner.py:48`, `vmware_discovery_runner.py`, `dump_vmware_hosts.py` | L'adaptateur argparse (`shinken/cli_compat.py`) ne traduit pas `%default` d'optparse => `--help` plante. | [VÉRIFIÉ] `python libexec/link_vmware_host_vm.py --help` -> `TypeError: %d format: a real number is required, not dict` | Dans `add_option`, remplacer `%default` par `%(default)s`. |
| m-4 | `shinken/cli_compat.py:43-45` | `parse_args` = `parse_known_args` : options inconnues renvoyées comme « arguments ». Les daemons les rejettent (`if args: parser.error`) mais avec un message trompeur ; les scripts libexec qui ne testent pas `args` les ignorent silencieusement. Valeurs par défaut `store_true` = `False` (optparse : `None`). | [VÉRIFIÉ] `shinken-arbiter -c x --bogus` -> « Does not accept any argument » | Utiliser `parse_args` strict, ou lister les options inconnues dans l'erreur. |
| m-5 | `shinken/http_daemon.py:310-311` | `except select.error as exc: errnum, _ = exc` — en Py3 `select.error` est `OSError`, non dépaquetable => `TypeError` qui masque l'erreur réelle (EINTR est de toute façon relancé automatiquement, PEP 475). | [LU] | `if exc.errno == errno.EINTR`. |
| m-6 | `shinken/misc/datamanager.py:40-59` | `hname.decode('utf8', ...)` sur des `str` => `AttributeError`. Appelé par `modules/livestatus/log_line.py:241-248` (requêtes sur la table `log` avec résolution hôte/service). | [LU] | Supprimer les `.decode`. |
| m-7 | `shinken/timeseries_adapter.py:240` | `datetime.utcnow().timestamp()` : datetime naïf interprété en heure locale => horodatage décalé si TZ≠UTC ; `utcnow` déprécié 3.12 ; `*1e9` perd la précision. Module non branché actuellement. | [LU] | `time.time_ns()`. |
| m-8 | `shinken/objects/item.py:377`, `shinken/satellite.py:429` | `if tpl_cv is not {}` / `if ret is not []` : toujours vrai (ruff F632). Hérité de master, sans régression. | [VÉRIFIÉ] ruff F632 | `if tpl_cv:` |
| m-9 | `shinken/macroresolver.py:139-147`, `shinken/util.py:33-38`, `objects/item.py:33`, `commandcall.py:28` | Shims `PY3`/`basestring`/`unicode`/`my_sort` encore présents (branches Py2 mortes, `unicode(value, 'utf8', errors=...)` = `str(bytes,...)`). Pas de bug, dette. | [LU] | Nettoyer. |
| m-10 | `shinken/http_client.py:190` | `HTTPPOST` déprécié par pycurl (avertissement à chaque POST). | [VÉRIFIÉ] warning pytest | `MIMEPOST`. |

Autres constats, sans gravité :
- ruff (règles F/B/E722 sur le code livré) : 80 imports inutilisés, 32 variables inutilisées, 17 arguments par défaut mutables (B006, ex. `http_client.get(args={})`), 7 redéfinitions (F811). Aucune erreur fatale E9/F7/F82 (job `lint` de la CI vert) [VÉRIFIÉ].
- Exceptions avalées : 50 `except:`/`except Exception:` nus dans shinken/bin/modules, dont 13 suivis de `pass` ; `satellitelink.get_external_commands` (`objects/satellitelink.py:385-396`) renvoie `[]` sans log pour toute exception — c'est exactement ce qui avait masqué le bug `str(bytes)` corrigé là. Niveau comparable à master, mais à journaliser.
- `libexec/*.py` gardent le shebang `#!/usr/bin/env python` (absent des distributions récentes sans `python-is-python3`).

---

## 4. Robustesse pickle et échanges inter-daemons

**Vérifié OK** [VÉRIFIÉ] — script `<scratch>/code/scripts/pickle_roundtrip.py` : pour 4 configurations de test (`1r_1h_1s`, `dispatcher`, `business_correlator`, `triggers`), sérialisation des confs de realm en protocole 0 et 5, de la conf complète, des checks et broks (pickle + zlib + base64 comme `get_checks`/`get_broks`), puis relecture via `SafeUnpickler.loads` : **tout passe**. La conf par défaut `etc/` (chemins redirigés) passe `shinken-arbiter -v` (« Things look okay »).

- `SafeUnpickler` (`shinken/safepickle.py`) : liste blanche `builtins.{object,set}`, `copyreg._reconstructor` + alias Py2 ; accepte bytes et str (latin-1). Correct pour les flux produits par le code. Le commit `d26e867` a corrigé 6 `pickle.loads` réseau qui contournaient le filtre : tous les `loads` réseau passent désormais par `SafeUnpickler` [VÉRIFIÉ par grep : `http_daemon.py:208`, `satellite.py:765`, `scheduler.py:900,935`, `brokerdaemon.py:359`, `schedulerdaemon.py:383`, `arbiterdaemon.py:614`, `satellitelink.py:384`, `brok.py:56`, `daemon.py:422`].
- Réserve [SUPPOSÉ, hérité de master] : tout attribut d'un module `shinken.*` est autorisé (`find_class` fait `getattr` sur n'importe quel `shinken.*`), y compris des réexports comme `shinken.misc.importlib.import_module` [VÉRIFIÉ présent] et `Trigger` (dont `eval()` fait `exec` du code compilé, `objects/trigger.py:66`). Les endpoints HTTP inter-daemons n'ont pas d'authentification : le modèle de confiance reste « réseau interne sûr », comme sur master. Restreindre à une liste explicite de classes serait plus sûr.
- `SafeUnpickler.find_class` (API historique, `safepickle.py:72-87`) n'applique pas les alias `copy_reg -> copyreg` contrairement à `_RestrictedUnpickler` : incohérence mineure.
- HTTP : `http_daemon` renvoie bytes => `application/octet-stream`, sinon JSON ; `http_client.get` tente JSON puis renvoie les bytes bruts. Cohérent. Les arguments GET sont passés par `urlencode(str(list))` ; les tests `'fork' in "dict_keys(['fork'])"` ne fonctionnent que par sous-chaîne (comportement identique à Py2, fragile : `poller_tags=['None']` vs tag `No`).

---

## 5. Revue des refactors récents (`git log --stat -10`)

| Commit | Constat |
|---|---|
| `6c25f5a` « modernize to Python 3, enable SQLite logging » | Voir **B-5** : active un module absent ; message de commit trompeur. `discoverymanager.py` : `string.split` -> `str.split` correct. Suppression `md5crypt.py` : aucun import restant (grep) — mais `bin/shinken-discovery`, consommateur de discoverymanager, ne compile pas (M-1). |
| `53ef6f9` daemon_kwargs | Correct (les clés de logging sont retirées avant le constructeur ; `shinken-arbiter --version/--help` OK [VÉRIFIÉ]). |
| `943e0ee` structured logging | Introduit **M-3** (doublons). `LogContext` est un faux context manager (renvoie un adapter, ne pose rien dans un contexte, `__exit__` vide) ; `create_daemon_logger` inutilisé. |
| `69f74da` argparse adapter | Fonctionne pour les daemons ; **m-3/m-4** ; `bin/shinken` et `bin/shinken-discovery` modifiés par ce commit restent en syntaxe Py2 (M-1). |
| `a7bf7ae`/`e113f7f` retrait de `six` | `a7bf7ae` avait écrasé `host.py` et `service.py` par un même contenu de 60 059 octets ; `e113f7f` les a restaurés — l'état final ne diffère de l'état d'avant que par le retrait de six/metaclass [VÉRIFIÉ par `git diff a7bf7ae~1 e113f7f`]. Montre que des commits intermédiaires cassés ont été poussés. |
| Commits « remove six from test/... » | Pas d'impact production. |

---

## 6. Ce qui a été vérifié vs supposé

- **Exécuté** : suite complète (2 fois, avec/sans monkeypatch daterange), ruff, compilation de tous les fichiers Python (y compris scripts sans extension), `shinken-arbiter -v` sur la conf livrée et sur une conf latin-1, round-trip pickle de confs/checks/broks, reproduction isolée de B-1, B-4, B-5, M-1 à M-5, m-3, smoke `--help` de tous les scripts libexec.
- **Non exécuté** : cluster multi-daemons réel (HTTP réel, poller passif bout-en-bout, broker + Livestatus en processus), daemonisation `-d`, HTTPS (pyOpenSSL absent), modules externes (named_pipe, logstore_sqlite, webui) — couverts par d'autres relecteurs ou à faire.
