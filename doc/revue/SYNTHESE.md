# Revue de la branche `modernize/podman-python3` — synthèse

*Revue du 31/10/2026, menée par 5 relecteurs en parallèle (code Python 3,
compatibilité master, test réel bout-en-bout, exploitation, documentation).*

**Question posée :** peut-on remplacer en production un Shinken de la branche
`master` officielle (`naparuba/shinken`, commit
`62039bef9bc44fbe1805d66b6d2a9ea8aa9b38b7`, 2.4.4, Python 2) par cette branche ?

## Verdict : NON en l'état — OUI sous conditions, après un lot de correctifs ciblé

| Domaine | Note | Rapport détaillé |
|---|---|---|
| Code et portage Python 3 | 4/10 | [01-code-python3.md](01-code-python3.md) |
| Compatibilité avec Shinken master | 3,5/10 | [02-compat-master.md](02-compat-master.md) |
| Test réel des 6 daemons | 4/10 | [03-e2e.md](03-e2e.md) |
| Exploitation et déploiement | 3/10 | [04-exploitation.md](04-exploitation.md) |
| Documentation | 4/10 | [05-documentation.md](05-documentation.md) |

**Ce qui est solide (vérifié en exécution) :**

- La **configuration** — le cœur du travail de l'administrateur — est conservée.
  La conf d'exemple officielle et une conf « riche » de style master se chargent
  à l'identique (templates, `register 0`, `$USER1$`, `duplicate_foreach`,
  exclusions, `bp_rule`, dépendances, escalades, realms). Seules 2 directives
  2.4.4 manquent.
- Options CLI des daemons, fichiers `.ini`, ports 7768-7773, liste des commandes
  externes : inchangés.
- Les 6 daemons démarrent ; checks, perfdata, SOFT→HARD, event handlers, WebUI,
  arrêt propre par SIGTERM : OK.
- 668 tests passent, le paquet Python se construit et s'installe.

**Ce qui est cassé :** tout ce qui entoure le cœur et fait la vie en production
(rétention, notifications, Livestatus/Thruk, `nagios.cmd`, pollers passifs).
Presque tous les défauts sont des **correctifs localisés**, pas un problème
d'architecture.

## Problèmes bloquants (confirmés par au moins deux relecteurs ou par exécution)

| # | Problème | Où | Effet en production |
|---|---|---|---|
| B1 | Livestatus pointe vers un module `logstore-sqlite` qui n'existe pas (commit `6c25f5a`) | `etc/modules/livestatus.cfg:6`, `modules/livestatus/module.py:169` | Livestatus plante toutes les 5 s : plus de Thruk, plus de commandes externes via Livestatus. La CI était verte. |
| B2 | Rétention : appel à `update_in_checking()` inexistant, `reprocess_state()` non appelé, aucun module de rétention Python 3 livré | `shinken/scheduler.py:1121`, `:1184` | Acks, downtimes, états perdus à chaque redémarrage ou reload ; notifications renvoyées, y compris pendant un downtime. |
| B3 | Notifications mail : `libexec/` non installé (ni image ni wheel), `notify_by_email.py` encore en Python 2 (`email.MIMEImage`, `iteritems`, shebang `python`), pas de MTA/relais | `Containerfile`, `libexec/notify_by_email.py:30,217` | Aucune notification ne part. |
| B4 | Timeperiod avec date fixe passée → `TypeError` (`t < None`) ; masqué par un patch dans `test/conftest.py:70-90` | `shinken/daterange.py:282` (et `:352`) | Plantage du scheduler avec des jours fériés datés. |
| B5 | Fichiers `.cfg` en latin-1 refusés (UTF-8 strict), sans nommer le fichier | `shinken/objects/config.py:880,904,942` | Une conf master existante avec accents peut empêcher l'arbiter de démarrer. |
| B6 | Pollers passifs : `str(bytes)` avant unpickle | `shinken/scheduler.py:892` | Tous les résultats des pollers passifs sont perdus. |
| B7 | `nagios.cmd` : module `named_pipe` absent + code bytes/str cassé | `modules/`, gestion du named pipe | Les scripts qui écrivent dans `nagios.cmd` ne fonctionnent plus (simple warning). |
| B8 | `etc/` livré = configuration personnelle (hôtes réels, e-mail réel, checks vers sites publics, mots de passe `admin`/`guest`) | `etc/hosts/`, `etc/contacts/`, `DEPLOYMENT.md` | Fuite d'informations ; notifications vers de vraies adresses si déployé tel quel. |
| B9 | Pas de migration progressive : master envoie `zlib(pickle)` en PUT, la branche `base64(zlib(pickle))` en POST | protocole inter-daemons | Bascule « big-bang » obligatoire de tous les daemons, spares compris. |

## Problèmes majeurs

- **CLI `shinken`** (`bin/shinken`, `bin/shinken-discovery`) : encore en Python 2 → SyntaxError, plus de `shinken install`. La CI ne vérifie pas les scripts sans `.py`, et `integration/modernization_audit.py:50` ignore les SyntaxError.
- **Modules tiers** : 12 des 13 modules Shinken courants (webui, graphite, mongodb, ws-arbiter…) sont en Python 2 ; `shinken.webui.bottlewebui` a été supprimé.
- **Sécurité pickle** : la liste blanche du correctif RCE de master 2.4.4 est relâchée (tout `shinken.*` accepté).
- **Fichier de rétention master** relisible uniquement avec `encoding='utf-8'` : prévoir un script de conversion.
- **Poller tué par `kill -9`** : ses workers orphelins gardent le port 7771, le nouveau poller ne démarre pas.
- **Daemons sans authentification ni TLS** : pendant le test, un autre processus a poussé sa conf sur les ports de test.
- **Logs** : chaque ligne en double (stdout + stderr) et affichée `b'...'` (`shinken/misc/termcolor.py:139`).
- **Conteneurs** : pas de redémarrage après reboot (quadlet/linger), fuseau UTC, image non versionnée (`shinken:dev`, pas de rollback), `COPY etc/` embarque tout secret déposé, plugins `check_dig`/SNMP/perl/`pkill` absents ou incertains, rien pour ajouter ses propres scripts de check, `/healthz` répond toujours `ok`.
- **Installation hors conteneur** incohérente (unités systemd en `/usr/sbin` + user `nagios`, wheel qui installe un paquet top-level `modules`).
- **Reload** : redémarrer l'arbiter ne recharge pas les modules du broker (`brokerdaemon.py:623`), contrairement à `doc/exploitation.md`.
- **38 regex non « raw »** dans 8 fichiers (SyntaxWarning sous 3.12+, erreur à terme).

## Documentation

Les fiches françaises (installation, configuration, exploitation, dépannage,
Thruk) sont exactes. Les pages anglaises `ARCHITECTURE.md`, `DATABASE.md`,
`LOGGING.md` et une partie de `DEVELOPMENT.md` sont largement fausses (20 affirmations fausses
sur 37 vérifiées : Pyro5/protobuf, `SHINKEN_JSON_LOGS`, logstores
MySQL/Oracle…). Pour l'administrateur de supervision, il n'existe presque rien :
concepts, écriture et intégration d'un plugin de check, recettes, référence des
directives, FAQ, guide de migration. Docstrings : 10,5 % du code
(0/185 dans `external_command.py`). Une arborescence cible par public et par
niveau est proposée dans [05-documentation.md](05-documentation.md).

## Plan d'action recommandé

**Lot 1 — rendre la branche exploitable (bloquants, petits correctifs)**

1. Livestatus : revenir à `logstore-null` **ou** livrer un vrai module `logstore-sqlite` Python 3 ; ajouter un test CI qui démarre le broker et interroge le port 50000.
2. Rétention : corriger `scheduler.py:1121/1184`, appeler `reprocess_state()` après chargement, livrer un module `retention-pickle` Python 3 (avec lecture `encoding='utf-8'` des fichiers master) et l'activer dans la conf d'exemple.
3. Notifications : porter `notify_by_email.py` en Python 3, installer `libexec/` dans l'image et le wheel, documenter le relais SMTP.
4. `daterange.py:282/352` : gérer `None` ; supprimer le patch de `conftest.py`.
5. Lecture des `.cfg` : UTF-8 puis repli latin-1, avec le nom du fichier dans l'erreur.
6. `scheduler.py:892` : ne plus convertir en `str` avant unpickle.
7. Livrer le module `named_pipe` (Python 3) pour `nagios.cmd`.
8. Remplacer `etc/` par une conf d'exemple neutre ; déplacer la conf personnelle hors du dépôt ; retirer `DEPLOYMENT.md` du README ; changer les mots de passe par défaut.

**Lot 2 — fiabiliser l'exploitation**

9. Porter `bin/shinken` ; étendre la CI (scripts sans `.py`, SyntaxWarning en erreur, démarrage réel des 6 daemons avec rétention + notification + Livestatus).
10. Image versionnée, `TZ`, quadlets systemd, healthcheck réel, plugins de supervision standard (monitoring-plugins, SNMP, perl), point de montage documenté pour les scripts de check maison.
11. Logs (doublons, `b'...'`), workers orphelins du poller, liste blanche pickle stricte.

**Lot 3 — documentation**

12. Supprimer ou réécrire `ARCHITECTURE.md`, `DATABASE.md`, `LOGGING.md` et corriger les chemins faux de `DEVELOPMENT.md`.
13. Créer `doc/admin/` (simple → avancé → expert, recettes, référence), `doc/exploitation/`, `doc/dev/`, guide de migration depuis master.

## Procédure de bascule recommandée (une fois le lot 1 fait)

1. Déployer la branche **en parallèle** de master, notifications désactivées, même conf.
2. Comparer les états pendant quelques jours (Thruk des deux côtés).
3. Convertir le fichier de rétention master.
4. Couper master, démarrer la branche (bascule de tous les daemons d'un coup).
5. Activer les notifications ; garder master arrêté mais prêt pour un retour arrière.

La checklist complète en 19 étapes se trouve dans [02-compat-master.md](02-compat-master.md),
la checklist de mise en production dans [04-exploitation.md](04-exploitation.md),
et la procédure de recette réutilisable dans [03-e2e.md](03-e2e.md).
