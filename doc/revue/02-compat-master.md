# Revue 02 : compatibilité de `modernize/podman-python3` avec Shinken master (upstream)

- **Branche relue** : `/home/user/shinken_gpt`, branche `modernize/podman-python3`, HEAD `6c25f5a` (« refactor: modernize to Python 3, enable SQLite logging »).
- **Référence upstream** : https://github.com/naparuba/shinken, branche `master`, commit **`62039bef9bc44fbe1805d66b6d2a9ea8aa9b38b7`** (26/04/2024, Python 2, version 2.4.4). Clone `--depth 1` dans `scratchpad/review/upstream`. Ce n'est **pas** le master du fork NCombarieu.
- **Périmètre** : uniquement la compatibilité avec une infra Shinken master existante. Le code Py3 interne, le bout-en-bout, le déploiement et la doc sont couverts par les autres relecteurs.
- **Artefacts de test** : `<scratch>/compat/`. On y trouve le venv, les configurations `local-etc`, `up-etc`, `rich-etc`, `m244-etc` et `pipe-etc`, les journaux `verify-*.log`, ainsi que les scripts `py2pickle.py`, `retention_test*.py` et `macro_test.py`. Les modules externes clonés sont dans `scratchpad/review/ext/`.
- **Aucun fichier du dépôt n'a été modifié.**

Limites de l'environnement :
- Pas d'interpréteur Python 2 disponible.
- L'exécution du code upstream a été refusée par le garde-fou de sécurité de l'environnement. La comparaison upstream est donc **statique** : diff de code et de configuration.
- shinken.io est injoignable : le proxy renvoie 403.
- Le dépôt `mod-retention-file-scheduler` est inaccessible. Le module équivalent `mod-pickle-retention-file-scheduler` a été lu à la place.

---

## 1. Résumé

**Note : 3,5 / 10 en compatibilité drop-in avec master.**

**Verdict : NON, ce n'est pas un remplacement drop-in.** C'est faisable **sous conditions lourdes**, avec une migration « big-bang » de tous les démons et une reconstruction des modules. L'exigence « tout fonctionne toujours avec Shinken » **n'est pas satisfaite** aujourd'hui.

### Points positifs (vérifiés)

- **Le langage de configuration est quasi identique.** Le diff automatique des propriétés `*Prop()` de `shinken/objects/*` et `shinken/*` ne montre que 2 directives absentes, toutes deux issues de la 2.4.4.
- **La configuration d'exemple upstream (`etc/` du commit 62039be) passe `shinken-arbiter -v`** : « Things look okay ».
- **Une configuration « riche » de style master se charge et se résout correctement.** Elle couvre :
  - templates, `register 0`, `use` ;
  - macros `$USER1$` et `$_HOSTxxx$`, `resource_file` ;
  - continuation de ligne `\` ;
  - `duplicate_foreach` ;
  - `hostgroup_name A|B` avec exclusion `!host` ;
  - business rules `bp_rule` ;
  - dépendances, escalades, realms imbriqués ;
  - timeperiods avancées.
- **Les options CLI des démons, les fichiers `.ini`, les ports 7768-7773 et la liste des commandes externes sont conservés.** La commande `RESTART_PROCESS` est ajoutée.

### Points bloquants

1. **La rétention d'état est cassée.** `restore_retention_data()` plante sur une méthode inexistante, même avec les données de la branche elle-même. Aucun module de rétention n'est fourni. Les états, downtimes, acks et commentaires sont donc perdus à chaque redémarrage.
2. **Les modules Shinken habituels, installés via `shinken install`, ne fonctionnent pas en Python 3.** Sont concernés : named-pipe, retention-*, graphite, simple-log, ws-arbiter, logstore-sqlite, webui (non testé), etc. Le CLI `shinken` lui-même ne se lance pas (SyntaxError Python 2).
3. **Aucune cohabitation n'est possible avec des démons master** : le protocole HTTP (verbes et encodage) et le format pickle sont différents. La migration progressive est impossible.
4. **Le code de la branche part d'un état antérieur à 2.4.4** (pyproject `2.4.3`, Changelog « 3.0.03 »). Il manque des correctifs de master. Le plus important est le recalcul de l'état downtime/ack après rétention.
5. **Une configuration en latin-1** (cas courant sur les vieilles installations Nagios/Shinken françaises) **fait crasher l'arbiter** avec `UnicodeDecodeError`, sans indiquer le fichier fautif.

---

## 2. Tableau de compatibilité par domaine

| Domaine | Statut | Commentaire (V = vérifié par exécution, S = supposé / statique) |
|---|---|---|
| Objets et propriétés de configuration | **OK / Écart** | V : diff des propriétés, seuls `conflict_policy` et `enable_problem_impacts_states_reprocessing` manquent (2.4.4). Ces directives sont acceptées avec un simple warning, mais **ignorées**. |
| Parsing (`cfg_dir`, `cfg_file`, `\`, templates, `use`, `register 0`, `duplicate_foreach`, exclusions, `bp_rule`) | **OK** | V : la conf riche passe ; macros résolues et objets corrects. |
| Encodage des fichiers `.cfg` | **Rupture** | V : un fichier latin-1 dans `cfg_dir` provoque un crash. Master Py2 l'acceptait via `six.u()`. |
| Configuration d'exemple upstream `etc/` | **OK** | V : `-v` OK, 0 erreur. |
| `etc/` livré par la branche | **Écart** | S/V : il est spécifique au conteneur et à l'infra personnelle de l'auteur (voir M-8). |
| CLI des démons | **OK / Écart** | V : `-c -d -r --debugfile -p -v -a -m -n` acceptés ; **`--dump_conf` (2.4.4) absent** de l'arbiter. |
| Fichiers `.ini` des démons | **OK** | V : identiques à upstream (`diff` vide). `http_backend=wsgiref` est ignoré en silence (Cheroot imposé). |
| Ports, pid, logs par défaut | **OK** | V : 7768 à 7773 identiques ; chemins `/var/run/shinken`, `/var/log/shinken` identiques dans les `.ini`/`.cfg`. |
| Commandes externes (liste) | **OK** | V : diff de `external_command.py`, seul ajout `RESTART_PROCESS`. |
| `nagios.cmd` (named pipe) | **Rupture** | V : `command_file=` génère un module `named_pipe` **introuvable** (simple WARNING). Le module upstream est en Python 2. |
| API des modules (`BaseModule`, `ModulesManager`) | **OK** | S : API inchangée ; le chargement « bare `module.py` » est même conservé. |
| Modules tiers `shinken install` | **Rupture** | V (statique) : 12 sur 13 modules courants contiennent des constructions Python 2 ; `shinken.webui.bottlewebui` a été supprimé (ws-arbiter). |
| Modules intégrés | **Écart** | V : livestatus (porté), status_webui (nouveau, ≠ webui2), logstore_null. `logstore-sqlite` est référencé mais **non implémenté**. |
| CLI `shinken` / shinken.io | **Rupture** | V : `bin/shinken` et `bin/shinken-discovery` provoquent `SyntaxError` en Python 3 (upstream `bin/shinken` est compatible Py3 via six). shinken.io n'a pas pu être testé. |
| Rétention (pickle produit par master) | **Rupture** | V : le pickle Py2 simulé ne se charge pas sans `encoding=` explicite ; le restore plante toujours (`update_in_checking`). |
| Protocole inter-démons (mix master/branche) | **Rupture** | V (statique) : PUT + `zlib(pickle)` côté master contre POST multipart + `base64(zlib(pickle))` côté branche. |
| Plugins de check, `$USER1$`, `resource.cfg` | **OK** | V : résolution identique ; même gestion de timeout (statut 3, « Check Timed Out »). |
| Notifications (`notify_by_email.py`) | **Écart** | V : shebang `python` (absent des distributions récentes) ; correctifs 2.4.4 manquants ; script absent de l'image conteneur. |
| Sécurité de la désérialisation | **Régression** | V : la liste blanche stricte de master (correctif RCE 2.4.4) est remplacée par « tout `shinken.*` ». |
| Paquetage et installation | **Écart** | V : `setup.py` n'installe plus `/etc/shinken`, `/var/lib/shinken`, libexec, l'utilisateur, ni les unités systemd/init (`bin/systemd/` supprimé). |

---

## 3. Problèmes

### BLOQUANTS

#### B-1. Le chargement de la rétention plante systématiquement : perte des états, downtimes, acks et commentaires

- **Fichiers** : `shinken/scheduler.py:1121` et `shinken/scheduler.py:1184` appellent `h.update_in_checking()` et `s.update_in_checking()`. Cette méthode n'existe nulle part dans la branche (`grep -rn update_in_checking` ne trouve que ces 2 appels), ni dans upstream.
- **Preuve (V)** : `compat/retention_test2.py` sur `test/etc/shinken_1r_1h_1s.cfg`, avec l'aller-retour natif de la branche `get_retention_data()` → pickle → `restore_retention_data()` :
  ```
  RESTORE FAIL: AttributeError 'Host' object has no attribute 'update_in_checking'
  ```
  Aucun test du dépôt ne couvre `restore_retention_data`.
- **Correctif** : reprendre la logique upstream, c'est-à-dire `restore_object_retention_data()` puis `o.reprocess_state()` pour chaque objet (upstream `shinken/scheduler.py`, fonction `restore_retention_data`). Supprimer les appels à `update_in_checking`. Ajouter un test d'aller-retour de rétention.

#### B-2. Aucun module de rétention n'est utilisable en Python 3

- **Constat** : aucun module de rétention n'est livré dans `modules/`. Les modules master courants sont en Python 2 :
  - `mod-pickle-retention-file-scheduler/module/module.py:28` fait `import cPickle` et utilise `except (...), exp:` ;
  - idem pour `pickle-retention-file-generic`, `retention-mongodb` et `retention-redis`.
- **Conséquence** : `etc/schedulers/scheduler-master.cfg` ne cite ces modules qu'en commentaire. Sans module, `hook_point('load_retention')` ne fait rien et l'état repart de zéro à chaque redémarrage.
- **Correctif** : livrer un module `pickle-retention-file` porté en Python 3 (écriture avec `protocol=2`, lecture avec `encoding='utf-8'`, voir B-3) avec un test.

#### B-3. Un fichier de rétention produit par master (Py2) n'est pas relisible tel quel

- **Preuve (V)** : `compat/py2pickle.py` émet à la main les opcodes que produit `cPickle.dump(..., protocol=2)` en Py2 : `SHORT_BINSTRING` pour `str`, et `NEWOBJ` + `BUILD` pour `Downtime`, `Acknowledge` et `Comment`.

  | Méthode de chargement | Résultat |
  |---|---|
  | `pickle.loads()` par défaut | `UnicodeDecodeError 'ascii'` |
  | `SafeUnpickler.loads()` | même `UnicodeDecodeError` |
  | `encoding='bytes'` | `KeyError 'id'` (les clés deviennent des `bytes`, ce qui casse `__setstate__`) |
  | `encoding='latin1'` | chargement OK mais **mojibake** : `'hÃ´te injoignable'`, `'Maintenance prÃ©vue'` |
  | `encoding='utf-8'` | **OK** : `'hôte injoignable'`, downtime, ack, commentaire et contacts restaurés (en contournant B-1) |

- **Résultat complémentaire** : même avec `encoding='utf-8'`, on obtient `scheduled_downtime_depth=0` et `problem_has_been_acknowledged=False` alors que downtime et ack sont présents. Voir M-1.
- **Correctif** : outil de migration `py2-retention → py3` qui charge avec `encoding='utf-8'` (repli `latin1`) puis réécrit en protocole Py3. Le module de rétention Py3 doit utiliser ce mode de lecture.

#### B-4. Le named pipe `nagios.cmd` n'est pas disponible

- **Fichier** : `shinken/objects/config.py:1833-1846` génère `NamedPipe-Autogenerated` (type `named_pipe`) ; aucun module de ce type n'existe.
- **Preuve (V)** : `compat/verify-pipe.log`, avec `command_file=` ajouté à la conf upstream :
  ```
  WARNING Module NamedPipe-Autogenerated was autogenerated
  WARNING The module type named-pipe for NamedPipe-Autogenerated was not found in modules!
  ... Things look okay
  ```
  Le pipe n'est donc **jamais créé**, sans erreur bloquante. Le module upstream `mod-named-pipe/module/module.py:79` utilise `os.mkfifo(..., 0660)`, une syntaxe Python 2 invalide en Py3.
- **Impact** : scripts maison, NRPE/NSCA-to-cmd, Thruk configuré en mode « cmd file », `check_mk`, etc. Seule la commande `COMMAND` de Livestatus reste disponible.
- **Correctif** : porter `named-pipe` en Python 3 et l'intégrer à `modules/`. Le code mort `ExternalCommandManager.open()` doit lui aussi être corrigé (voir m-4).

#### B-5. Le CLI `shinken` (install, search, inventory, desc) est inutilisable

- **Fichiers** : `bin/shinken:252` contient `print ''`. Le fichier importe aussi `ConfigParser`, `StringIO`, `urllib` et `imp` (Python 2). `bin/shinken-discovery:121` contient `print "Macros", raw_macros`.
- **Preuve (V)** : `python bin/shinken --help` donne `SyntaxError: Missing parentheses in call to 'print'`. **Régression par rapport à upstream** : `bin/shinken` du commit 62039be est compatible Py3 via `six` (ast OK).
- **Impact** : plus de `shinken install <module>` ni de `shinken inventory`. De plus, shinken.io n'a pas pu être joint ici (403 proxy, SUPPOSÉ hors service depuis longtemps).
- **Correctif** : repartir de `bin/shinken` upstream (déjà compatible six) et porter `shinken-discovery`.

#### B-6. Pas de migration progressive possible : le protocole inter-démons est incompatible

Vérifié de manière statique :

| | Master 62039be | Branche |
|---|---|---|
| Envoi de données (`put_conf`, `push_broks`, `push_actions`, `put_results`, `run_external_commands`) | `PUT` avec corps `zlib(pickle(HIGHEST_PROTOCOL))` (`shinken/serializer.py`, `http_client.put`) | `POST` multipart avec un champ par argument `base64(zlib(cPickle.dumps(v)))` (`shinken/http_client.py:165-191`, `shinken/http_daemon.py:200-208`), routes en `method='post'` |
| Réponses (`get_checks`, `get_broks`, `get_returns`) | `serialize(res)` brut, `encode='raw'` | `base64.b64encode(zlib.compress(cPickle.dumps(res), 2))` (`shinken/daemons/schedulerdaemon.py:76,124`, `shinken/satellite.py:191`) |
| Contenu du pickle | `str` Py2 | protocole Py3 (≥ 4) que Py2 ne sait pas lire |

En plus du format, les objets ne correspondent pas : chaînes `bytes`/`str` différentes et le module `shinken.serializer` n'existe plus côté branche.

- **Conséquence** : un poller, broker ou receiver master face à un scheduler ou arbiter de la branche, ou l'inverse, obtient des erreurs 405, des erreurs de désérialisation ou des données corrompues. **Tous les démons de tous les realms (spares compris) doivent être basculés en même temps.**
- **Correctif** : aucun à prévoir ; c'est à documenter comme migration « big-bang ».

### MAJEURS

#### M-1. Correctif 2.4.4 « Enforced downtime state after retention load » absent

- **Fichiers** : `reprocess_state()` est défini (`shinken/objects/schedulingitem.py:890`) mais **jamais appelé** par `shinken/scheduler.py:1085 restore_retention_data`. Upstream l'appelle pour chaque objet.
- **Preuve (V)** : après restauration (en contournant B-1), un hôte avec un downtime actif et un ack donne `sdd=0 ackd=False`.
- **Conséquence** : des notifications partent pendant un downtime ou sur un problème acquitté après chaque redémarrage du scheduler.
- **Correctif** : B-1 avec appel à `o.reprocess_state()`.

#### M-2. Fichiers de configuration non UTF-8 : crash de l'arbiter

- **Fichiers** : `shinken/objects/config.py:880`, `:904`, `:942` utilisent `io.open(..., encoding='utf8')` en mode strict. Seule l'exception `IOError` est rattrapée, pas `UnicodeDecodeError`.
- **Preuve (V)** : `compat/rich-etc/latin1.cfg.off`, remis dans `cfg_dir`, donne :
  ```
  CRITICAL ... UnicodeDecodeError: 'utf-8' codec can't decode byte 0xe9 in position 100
  ```
  Le traceback n'indique pas le nom du fichier. Master Py2 lisait les `cfg_dir` via `six.u()` (décodage `unicode_escape`, tolérant à latin-1).
- **Correctif** :
  - essayer utf-8 puis basculer en latin-1 avec un WARNING qui nomme le fichier ;
  - ou au minimum rattraper l'erreur, la signaler avec le chemin et marquer `conf_is_correct=False` ;
  - documenter `iconv -f latin1 -t utf8`.

#### M-3. Modules tiers courants non compatibles Python 3

Comptage statique (VÉRIFIÉ par grep et ast) sur les dépôts `shinken-monitoring/*` clonés dans `ext/` :

| Module | Constat |
|---|---|
| graphite | syntaxe Py2 |
| livestatus (externe) | 7 fichiers en syntaxe Py2, 10 avec API Py2 |
| logstore-sqlite | syntaxe Py2 |
| named-pipe | syntaxe Py2 |
| pickle-retention-file-generic / -scheduler | syntaxe Py2 |
| retention-mongodb / -redis | API Py2 (`cPickle`, `iteritems`…) |
| simple-log | syntaxe Py2 |
| ws-arbiter | syntaxe Py2, et importe `shinken.webui.bottlewebui`, **supprimé** de la branche |
| booster-nrpe | API Py2 |
| webui (mod-webui 2.x) | la syntaxe passe mais 9 fichiers utilisent une API Py2 ; il embarque son propre `md5crypt` |
| NSCA, ui-graphite | pas de construction Py2 détectée (SUPPOSÉ fonctionnels, non exécutés) |

- **Conséquence** : un broker master typique (`modules webui2, livestatus, graphite2, simple-log, ...`) ne fait qu'émettre des WARNING « module type ... not found » au démarrage. Les fonctions disparaissent **en silence**.
- **Correctif** :
  - fournir les ports Py3 des modules indispensables ;
  - restaurer `shinken/webui/bottlewebui.py` (ou porter ws-arbiter) ;
  - faire échouer `-v` (ou au moins renvoyer un code ≠ 0) quand un module référencé est introuvable.

#### M-4. `logstore-sqlite` référencé mais absent

- **Fichiers** : `etc/modules/livestatus.cfg` (`modules logstore-sqlite`) et `etc/modules/logstore-sqlite.cfg` (`module_type logstore_sqlite`). Aucune implémentation n'existe dans `modules/` (`grep -rl logstore_sqlite` ne renvoie que des configurations, de la doc et `contrib/`).
- **Origine** : le dernier commit `6c25f5a` annonce « enable SQLite logging » mais n'ajoute que de la configuration.
- **Conséquence** : l'historique Livestatus (requêtes `GET log` de Thruk) est indisponible.
- **Correctif** : porter `logstore-sqlite` ou revenir à `logstore-null` dans `livestatus.cfg`.

#### M-5. Régression de sécurité de la désérialisation (correctif RCE 2.4.4 de master annulé)

- **Fichier** : `shinken/safepickle.py:50-53` (et `:75`) contient :
  ```python
  if module.startswith('shinken.'):
      __import__(module); return getattr(sys.modules[module], name)
  ```
  Master 62039be applique une liste blanche **stricte**, classe par classe (`PICKLE_SAFE`).
- **Preuve (V)** : `SafeUnpickler.loads(b"cshinken.misc.importlib\nimport_module\n.")` renvoie `<function import_module>`. N'importe quel callable importé dans un module `shinken.*` est accepté, ce qui fournit des briques de base pour une RCE sur les ports 7768-7773 non authentifiés. La RCE complète n'a pas été démontrée.
- **Correctif** : restaurer la liste blanche exhaustive d'upstream (avec les alias `copy_reg` et `__builtin__`).

#### M-6. Paquetage hors conteneur : plus d'installation système

- **Fichiers** : `setup.py` est réduit à `setup(packages=find_packages())` et `pyproject.toml` ne déclare rien de plus. Ne sont plus installés : `/etc/shinken`, `/var/lib/shinken/{modules,libexec}`, `/var/log/shinken`, l'utilisateur `shinken`, les unités systemd et `/etc/default/shinken-*`. Le répertoire `bin/systemd/` (présent upstream) a été **supprimé**. Seuls les scripts listés dans `setup.cfg [options] scripts` sont installés.
- **Impact** : remplacer une installation `pip install shinken` ou paquet distribution en place exige de recréer à la main toute l'arborescence et les unités.
- **Correctif** : fournir un script `install-system.sh` ou des unités systemd dans `contrib/`, et documenter.

#### M-7. Notifications par e-mail

- `libexec/notify_by_email.py:1` utilise le shebang `#!/usr/bin/env python`. Sur Debian 12+, RHEL 9 et autres distributions sans `python`, le script échoue avec le code 127 et **aucune notification n'est envoyée**. `libexec/external_mapping.py` a le même problème.
- Correctifs 2.4.4 manquants dans ce script :
  - en-têtes `Precedence: bulk` et `Auto-Submitted` (#2014) ;
  - mode texte `MIMEText(txt_content, 'text')` en `:228`, qui produit `text/text` (#1986, V) ;
  - couleurs des cellules HTML.
- Dans l'image conteneur, ni `libexec/` ni `/usr/bin/mail` ne sont présents (`Containerfile`). Les commandes `notify-*-by-email` par défaut échouent (S, à confirmer par le relecteur déploiement).
- **Correctif** : shebang `python3`, rétroportage des correctifs, installation de libexec.

#### M-8. Le `etc/` livré n'est pas la configuration Shinken de référence

- `etc/commands/reload-shinken.cfg` et `restart-shinken.cfg` sont remplacés par `pkill -TERM -f shinken-arbiter` (logique de conteneur), au lieu de `/etc/init.d/shinken reload`.
- `etc/hosts/localhost.cfg` a pour check `check_local_http!broker!8080` et contient un hôte **`KIKI 158.69.204.23`**.
- `hosts/this-vps.cfg`, `internet-fun.cfg`, `contacts/webteam.cfg`, `etc/ssh_keys/` et `etc/grafana` sont spécifiques à l'infra de l'auteur.
- **Risque** : si l'admin copie ce `etc/` sur son infra, il obtient des checks erronés et un comportement de reload différent.
- **Correctif** : séparer `etc/` (référence upstream) et `containers/etc-overlay/`.

#### M-9. Fonctions et directives 2.4.4 de master absentes (régression de version)

- **`conflict_policy=strict`** (upstream `shinken/objects/config.py:123`) n'est que « guessed » puis ignoré. V : `compat/verify-m244.log` montre qu'un doublon d'hôte est **accepté** (« using lastly defined ») là où master strict refuse la configuration.
- **`enable_problem_impacts_states_reprocessing`** est absent.
- **`--dump_conf`** de l'arbiter est absent. V :
  ```
  shinken-arbiter: error: Does not accept any argument
  ```
  Le message est d'ailleurs trompeur.
- **Correctif** : rebaser sur 62039be ou rétroporter le Changelog 2.4.4. La branche se déclare `2.4.3` (`pyproject.toml:7`).

### MINEURS

- **m-1. Sortie console des journaux en `bytes`.** `shinken/misc/termcolor.py:139-141` encode en utf-8 avant `print`, ce qui affiche `b'[...] INFO: ...'`. V : 139 lignes de ce type dans `verify-local.log`. Toutes les lignes sont en outre doublées (handler couleur + handler structuré). Cela gêne les admins qui parsent la sortie de `-v` ou le journal systemd.
- **m-2. `http_backend` ignoré.** `http_backend=wsgiref|cherrypy` est ignoré (Cheroot imposé, `shinken/http_daemon.py:125-150`) ; pyOpenSSL n'est plus utilisé (adaptateur SSL builtin). `hard_ssl_name_check` n'a plus d'effet côté serveur. À re-tester avec les certificats existants (S).
- **m-3. Endpoint `/inject` supprimé** (`Injector.inject` de l'ordonnanceur). C'est une amélioration de sécurité, mais tout outillage qui l'utilisait casse. Des routes en tirets (`/get-checks`…) ont été ajoutées.
- **m-4. Code mort `ExternalCommandManager.open()`.** `shinken/external_command.py:460` et `:2061` utilisent `os.mkfifo(path, 660)` au lieu de `0o660`. V : le mode obtenu est `p-w--w-r-T`, d'où `PermissionError` pour un utilisateur non-root. `open(path, 'w+', os.O_NONBLOCK)` lève `io.UnsupportedOperation` en Py3 même en root. Ce code n'est appelé nulle part aujourd'hui, mais servira de base au portage de named-pipe (B-4).
- **m-5. Sortie de plugin non UTF-8.** Elle est décodée en `utf8` avec `errors='ignore'` (`shinken/util.py:968-973`) : les accents latin-1 disparaissent. Master Py2 perdait le bloc entier (`no_block_read` qui renvoie `''`), donc c'est plutôt un mieux, mais le comportement diffère (S).
- **m-6. Sortie partielle en cas de timeout.** Lors d'un timeout, la branche analyse la sortie partielle du plugin avant que le scheduler ne la remplace par « (Service Check Timed Out) » (`shinken/action.py:153-162`). Effet visible probablement nul (S).
- **m-7. Changelog incohérent.** Il annonce « 3.0.03 - X/X/2017 » alors que `pyproject` annonce 2.4.3 ; c'est ambigu pour l'admin.
- **m-8. `-v` renvoie `rc=0` avec des modules introuvables.** La vérification passe même quand des modules référencés manquent (voir B-4 et M-3) ; c'est hérité d'upstream, mais plus grave ici puisque presque tous les modules tiers manquent.

---

## 4. VÉRIFIÉ et SUPPOSÉ

**VÉRIFIÉ (exécuté dans le venv Python 3.13 + `requirements.txt`)** :

- `shinken-arbiter -v` sur :
  - le `etc/` de la branche : rc 0, 7 hôtes ;
  - le `etc/` upstream 62039be : rc 0, « Things look okay » ;
  - la conf riche : rc 0 ;
  - la conf riche avec latin-1 : crash ;
  - la conf avec `command_file` : module introuvable ;
  - la conf avec les directives 2.4.4 : ignorées.
- Résolution des macros, `duplicate_foreach`, parents et realms (`macro_test.py`).
- `--help` de tous les démons ; `--dump_conf` refusé.
- Rétention : plantage de l'aller-retour natif, comportements du pickle de type Py2 (`retention_test.py`, `retention_test2.py`), `sdd=0` et `ack=False` après restauration.
- `SafeUnpickler` accepte `shinken.misc.importlib.import_module`.
- Mode du FIFO `660` et échec non-root ; `MIMEText(..., 'text')` donne `text/text`.
- `bin/shinken` et `bin/shinken-discovery` : `SyntaxError` en Py3 (upstream `bin/shinken` OK).
- Diffs : propriétés, commandes externes, méthodes de l'API HTTP, `.ini`, `etc/`, ports.

**SUPPOSÉ (statique ou non exécutable ici)** :

- Le comportement exact de master sur les mêmes configurations : le code upstream n'a pas pu être exécuté (refus de l'environnement, pas de Py2). Les écarts sont déduits du diff de code.
- L'incompatibilité runtime du mix de démons, déduite des verbes HTTP et des formats ; aucun démon master n'a été lancé.
- Le pickle de rétention Py2 est **émulé** opcode par opcode et non produit par un vrai CPython 2.7.
- Pour les modules tiers, seuls l'analyse syntaxique et un grep d'API Py2 ont été faits, sans exécution. La disponibilité de shinken.io n'a pas été testée (proxy).
- La parité fonctionnelle de Livestatus et status_webui avec mod-livestatus et webui2 relève du relecteur E2E.

---

## 5. Checklist de migration master (Py2) → `modernize/podman-python3`

**Avant (sur l'infra master)**

1. [ ] Inventorier les modules : `grep -rh "modules\b" /etc/shinken/{arbiters,schedulers,brokers,receivers,pollers,reactionners}` et `ls /var/lib/shinken/modules`. Pour chacun, vérifier qu'il existe un équivalent Py3 (aujourd'hui seuls livestatus, status_webui et logstore_null). **Sans retention, named-pipe ni webui portés, ne pas migrer.**
2. [ ] Vérifier l'encodage des fichiers de configuration : `find /etc/shinken -name '*.cfg' -exec file -i {} + | grep -v 'utf-8\|us-ascii'`, puis convertir avec `iconv -f latin1 -t utf-8`.
3. [ ] Retirer ou noter les directives 2.4.4 non supportées (`conflict_policy`, `enable_problem_impacts_states_reprocessing`, `--dump_conf` dans les unités) et vérifier l'absence de doublons d'objets si `conflict_policy=strict` était utilisé.
4. [ ] Sauvegarder `/etc/shinken`, `/var/lib/shinken` (fichier de rétention, par ex. `retention.dat`) et la configuration des modules.
5. [ ] Exporter les downtimes et acks en cours (Thruk ou Livestatus `GET downtimes` / `GET comments`) **sous forme de commandes externes**, pour pouvoir les réinjecter : c'est le plan B si la rétention n'est pas relue.
6. [ ] Lancer `shinken-arbiter -v -c /etc/shinken/shinken.cfg` de la branche sur une **copie** de la configuration, et lire **tous** les WARNING « module type ... not found » et « Guessing the property ».

**Bascule (big-bang obligatoire, B-6)**

7. [ ] Arrêter **tous** les démons master de tous les realms, spares compris. Aucune cohabitation n'est possible.
8. [ ] Convertir la rétention : charger avec `pickle.load(f, encoding='utf-8')` (repli `latin1`), puis réécrire avec le module de rétention Py3. **Prérequis : correctifs B-1 et M-1.**
9. [ ] Recréer l'arborescence et l'utilisateur, faute d'installation système (M-6) :
   - `/etc/shinken`, `/var/lib/shinken/{modules,libexec}`, `/var/log/shinken`, `/var/run/shinken` ;
   - utilisateur `shinken` (UID 10001 dans l'image conteneur, contre un UID système avant) : `chown` des volumes ;
   - unités systemd : reprendre `bin/systemd/*.in` d'upstream ; les options `-d -c` sont compatibles.
10. [ ] Adapter `modules_dir` (`/usr/local/lib/shinken/modules` dans le conteneur, au lieu de `/var/lib/shinken/modules`).
11. [ ] Installer libexec et corriger les shebangs (`notify_by_email.py` → `python3`). Vérifier `$PLUGINSDIR$` et `$USER1$` dans `resource.d/` et la présence de `mail` ou d'un SMTP.
12. [ ] **Ne pas** reprendre `etc/` de la branche tel quel (hôtes et commandes reload spécifiques, M-8) : garder sa propre configuration.
13. [ ] Remplacer `nagios.cmd` par la commande `COMMAND` de Livestatus (port 50000) tant que named-pipe n'est pas porté ; adapter Thruk, les scripts et les receivers NSCA.
14. [ ] Remplacer webui2 par status_webui (fonctions réduites) ou par Thruk via Livestatus ; remplacer graphite et simple-log par les équivalents de la branche (`broker-timeseries.cfg`, journalisation structurée), après validation.
15. [ ] SSL inter-démons : re-tester les certificats (adaptateur builtin, `hard_ssl_name_check` sans effet côté serveur).

**Après**

16. [ ] Contrôler qu'aucune notification ne part pour les hôtes en downtime ou acquittés (M-1), puis réinjecter les downtimes et acks exportés à l'étape 5 si besoin.
17. [ ] Vérifier que le `shinken.log` et Livestatus `GET log` sont alimentés (M-4).
18. [ ] Ne plus utiliser `shinken install` (B-5) : gérer les modules à la main ou dans l'image.
19. [ ] Garder l'infra master arrêtée mais intacte (configuration et rétention d'origine) pour un retour arrière. Le retour arrière perd l'état acquis côté branche, car les formats sont incompatibles dans les deux sens.

**Correctifs minimaux à demander avant de déclarer la branche « compatible master »** : B-1 et M-1, un module de rétention Py3 capable de lire les pickles Py2 (B-2 et B-3), named-pipe Py3 (B-4), `bin/shinken` Py3 (B-5), tolérance latin-1 (M-2), liste blanche pickle (M-5), rétroportage de la 2.4.4 (M-9), et un `etc/` de référence séparé de l'overlay conteneur (M-8).
