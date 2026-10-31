# Revue 05 : audit de la documentation

Dépôt : dépôt local, branche `modernize/podman-python3`. Audit en lecture seule, daté du 2026-10-31.
Périmètre lu : `README`, `README.rst`, les 12 fichiers de `doc/*.md`, `DEPLOYMENT.md`, `DEVELOPMENT.md`, `CONTRIBUTING.rst`, `Changelog`, `manpages/`, les commentaires de `etc/`, `libexec/`, et un échantillon de docstrings dans `shinken/` et `modules/`.

---

## 1. Résumé

**Note globale : 4/10.**

| Axe | Note | Commentaire court |
|---|---|---|
| Exactitude | 3/10 | Les fiches FR (installation, configuration, exploitation, dépannage, Thruk) sont **globalement exactes**. En revanche, `ARCHITECTURE.md`, `DATABASE.md`, `LOGGING.md` (en partie) et `DEVELOPMENT.md` (en partie) décrivent un système qui **n'existe pas** : Pyro5, protobuf, sections INI, logstores MySQL/Oracle, socket unix, `/api/livestatus`, `nagios.cfg`, `configurationmanager.py`… |
| Couverture admin supervision | 2/10 | Aucun contenu sur les concepts (états SOFT/HARD, check passif, flapping, escalades, dépendances, macros, héritage), sur l'écriture d'un plugin, sur les recettes (SNMP, Windows, BDD), sur les notifications, ni de référence des directives. Seul le niveau « débutant/intermédiaire » est traité, et uniquement sous l'angle conteneur. |
| Couverture exploitant | 5/10 | Installation, logs, redémarrage et ack/downtime via Livestatus sont bien traités. Manquent : les variables `SHINKEN_*`, la réécriture de config par l'entrypoint, la sauvegarde, la mise à jour, la rétention d'état, la supervision de la supervision et le durcissement. |
| Couverture développeur | 4/10 | `DEVELOPMENT.md` est utile pour les tests et la CI, mais contient des chemins faux. `depannage.md` est riche en retours d'expérience de portage. Docstrings : 10,5 %. |
| Qualité et forme | 5/10 | Les fiches FR sont bien construites (front-matter, objectif, prérequis, validation, retour arrière). Mais la langue est mélangée FR/EN, 5 pages sont orphelines (absentes de l'index), la syntaxe MkDocs (`!!!`, `{#id}`) s'affiche telle quelle sur GitHub faute de `mkdocs.yml`, et des données personnelles sont mêlées aux exemples génériques. |

**Les cinq problèmes majeurs :**

1. **Quatre documents EN sont largement fictifs** (`doc/ARCHITECTURE.md`, `doc/DATABASE.md`, `doc/LOGGING.md`, `DEVELOPMENT.md` § Database et Plugins). Un administrateur qui suit `DATABASE.md` casse sa configuration : la syntaxe INI n'est pas acceptée par l'arbiter.
2. **Contradiction doc / config / code sur le logstore Livestatus.**
   - `doc/livestatus-thruk.md:70` et `doc/configuration.md:36` annoncent `logstore-null`.
   - `etc/modules/livestatus.cfg:6` référence `logstore-sqlite`.
   - **Aucun module `logstore_sqlite` n'existe** dans `modules/` (seul `modules/logstore_null/` existe).
   - Le commit `6c25f5a`, intitulé « enable SQLite logging », n'a ajouté qu'un fichier `.cfg`.
3. **Les notifications par e-mail ne fonctionnent probablement pas** dans le conteneur, et rien ne le dit.
   - `etc/commands/notify-*-by-email.cfg` appelle `$PLUGINSDIR$/notify_by_email.py`, avec `$PLUGINSDIR$=/var/lib/shinken/libexec` (`etc/resource.d/paths.cfg`).
   - Ni le `Containerfile` ni `setup.py`/`setup.cfg` n'installent `libexec/`.
   - L'envoi passe par un SMTP `-S localhost`, alors que le conteneur n'a pas de MTA.
4. **Le public « administrateur de la supervision » n'est pas servi.** Il n'existe aucun guide pour écrire et déposer un plugin (`$USER1$`, codes retour, perfdata, emplacement dans le conteneur), alors que c'est le besoin n° 1 exprimé.
5. **Des données personnelles se trouvent dans la configuration d'exemple « générique »** :
   - un hôte de test personnel avec une IP publique réelle (`etc/hosts/localhost.cfg:12-20`) ;
   - le serveur personnel avec un compte utilisateur réel (`etc/services/<serveur personnel>.cfg`) ;
   - un e-mail personnel réel (`etc/contacts/webteam.cfg`) ;
   - le domaine personnel et des chemins d'infrastructure privée (`DEPLOYMENT.md`), un fichier cité comme « référence » dans `README.rst:43`.

   Toute personne qui clone et lance la stack va pinguer une IP publique réelle et tenter un SSH vers `host.containers.internal` avec un compte utilisateur réel.

---

## 2. Vérification par sondage : 37 affirmations confrontées au code

✔ = conforme, ✘ = faux, ~ = partiellement faux ou à préciser.

| # | Affirmation (doc:ligne) | Réalité (code:ligne) | Verdict |
|---|---|---|---|
| 1 | Six conteneurs `shinken_<daemon>_1` (`installation.md:82-85`) | `compose.yaml:1` `name: shinken` et 6 services ; profil `experimental-metrics` en plus | ✔ (le profil n'est pas cité dans installation.md) |
| 2 | Ports 8081 (webui) et 50000 (Livestatus) sur 127.0.0.1 (`installation.md:43`) | `compose.yaml:51-52` | ✔ |
| 3 | `curl :8081/healthz` → `ok` (`installation.md:91`) | `modules/status_webui/module.py:71-72` | ✔ |
| 4 | `cap_drop: ALL` et `NET_RAW` seulement sur le poller (`configuration.md:94-101`) | `compose.yaml:15-16, 40-41` | ✔ |
| 5 | `./etc:/etc/shinken:ro,Z` (`configuration.md:27`) | `compose.yaml:18` | ✔, mais incomplet : l'entrypoint **recopie** la config dans `/tmp/shinken-config` et **réécrit** les `address` des daemons ainsi que `modules_dir` (`containers/entrypoint.sh:11-29`). Ce n'est documenté nulle part. |
| 6 | Paquets `nagios-plugins-basic`, `nagios-nrpe-plugin`, `openssh-client` (`installation.md:71-74`) | `Containerfile:22` | ✔ |
| 7 | Options de `shinken-healthcheck` : `--quiet`, `--stale-after`, `--exit-nonzero-on-problem`, `--host`, `--port` (`exploitation.md:77-88`) | `bin/shinken-healthcheck:73-86` | ✔ (`--timeout` et `--no-color` ne sont pas documentés) |
| 8 | `max_service_check_spread` = 5 (`installation.md:137`, `depannage.md:28`) | `etc/shinken.cfg:45` | ✔ |
| 9 | Tout `.cfg` placé sous un `cfg_dir` est chargé (`configuration.md:41-43`) | `etc/shinken.cfg:3-38` | ✔ |
| 10 | `modules livestatus,status-webui` sur le broker (`configuration.md:159`) | `etc/brokers/broker-master.cfg` | ✔ |
| 11 | Livestatus utilise `modules logstore-null` (`livestatus-thruk.md:70`, `configuration.md:36`) | `etc/modules/livestatus.cfg:6` utilise `logstore-sqlite`, un module **absent** de `modules/` | ✘ (3 sources incohérentes) |
| 12 | Syntaxe de `SCHEDULE_FORCED_SVC_CHECK`, `SCHEDULE_SVC_DOWNTIME`, `ACKNOWLEDGE_SVC_PROBLEM` (`exploitation.md:64, 97, 109`) | `shinken/external_command.py:71-72, 335-336, 361-363` | ✔ |
| 13 | `RESTART_PROCESS` est un alias de `RESTART_PROGRAM` (`depannage.md:75-77`) | `shinken/external_command.py:317, 1668` | ✔ |
| 14 | `reload-shinken` lance `pkill -TERM -f shinken-arbiter` (`livestatus-thruk.md:198-203`) | `etc/commands/reload-shinken.cfg` | ✔ côté config. **À vérifier côté image** : `python:3.13-slim` ne contient pas `/usr/bin/pkill` (constaté avec `docker run`). Il n'est disponible que si une dépendance des plugins tire `procps`. |
| 15 | Filtrage Livestatus par `AuthUser` (`livestatus-thruk.md:154`) | `modules/livestatus/livestatus_query.py:176` | ✔ |
| 16 | « Pyro5 (RPC) for daemon-to-daemon » (`ARCHITECTURE.md:20, 63, 182`) | `shinken/pyro_wrapper.py` n'est importé **nulle part**. Le transport réel est HTTP, avec `shinken/http_client.py` (pycurl) et `http_daemon.py` (Cheroot/Bottle) sérialisés en pickle. | ✘ |
| 17 | « Protocol buffers » (`ARCHITECTURE.md:22`) | Aucune occurrence dans le code | ✘ |
| 18 | `shinken/configurationmanager.py` (`ARCHITECTURE.md:39`, `DEVELOPMENT.md:246`) | Fichier inexistant. Le parsing est dans `shinken/objects/config.py`. | ✘ |
| 19 | `modules/livestatus/logstore_sqlite.py` (`ARCHITECTURE.md:132`) | Inexistant | ✘ |
| 20 | Socket `unixsock:///var/run/shinken/livestatus.sock` (`ARCHITECTURE.md:143`, `DATABASE.md:258-267`) | Le socket unix n'est créé que si le paramètre `socket` est défini (`modules/livestatus/module.py:112-118, 339`). Il est absent de `etc/modules/livestatus.cfg`. | ✘ |
| 21 | `curl http://localhost:8080/api/livestatus` (`ARCHITECTURE.md:144`) | Seuls `/`, `/api/status` et `/healthz` existent (`status_webui/module.py:71-80`) | ✘ |
| 22 | Configuration principale `nagios.cfg` et `resource.cfg` (`ARCHITECTURE.md:153-154`, `LOGGING.md:40, 100`) | Les vrais fichiers sont `etc/shinken.cfg` et `etc/resource.d/*.cfg`. `resource_file` est commenté (`shinken.cfg:37`). | ✘ |
| 23 | « If state change: Broker notifies Reactionner » (`ARCHITECTURE.md:124`) | Le scheduler crée les notifications et le reactionner les récupère auprès du scheduler (`schedulerdaemon.py:57 get_checks(... do_actions)`). Le broker ne fait que consommer les broks. | ✘ |
| 24 | Receiver « NSCA-compatible » (`ARCHITECTURE.md:92`) | Aucun module nsca dans `modules/`, et `receiver-master.cfg` déclare `modules` vide | ✘ dans ce fork |
| 25 | `--json-logs`, `--verbose`, `--debug`, `--logfile` (`LOGGING.md:37-101`) | `shinken/bin_utils.py:60-69`, appelé par `bin/shinken-*` | ✔ (absent des manpages ; l'effet sur le logger `Shinken` de `shinken/log.py:241` n'a pas été vérifié à l'exécution) |
| 26 | Variable d'environnement `SHINKEN_JSON_LOGS=1` (`LOGGING.md:46-53`) | Lue nulle part (ni `entrypoint.sh`, ni code) | ✘ |
| 27 | `etc/shinken/logging.cfg` (`LOGGING.md:58`) | Inexistant | ✘ |
| 28 | Syntaxe `[broker_livestatus]`, `logstore_type = …`, `logstore_mysql_*`, `pool_size` (`DATABASE.md:61-142, 293` ; `DEVELOPMENT.md:156-168`) | Syntaxe INI refusée dans les `.cfg` d'objets (`METRICS.md:10-11` le dit d'ailleurs). Aucun module logstore MySQL ou Oracle n'existe. | ✘ (page entière) |
| 29 | `systemctl status shinken-broker`, `/var/log/shinken/broker.log` (`DATABASE.md:248, 264`) | Il n'y a pas de systemd dans le déploiement conteneur, et le fichier de log s'appelle `brokerd.log` (`etc/daemons/brokerd.ini`) | ✘ |
| 30 | Plugins dans `etc/nagios-plugins/` ou `etc/plugins/` (`DEVELOPMENT.md:226-233`) | Ces répertoires n'existent pas. Les plugins sont dans `/usr/lib/nagios/plugins` (`$NAGIOSPLUGINSDIR$`, `etc/resource.d/paths.cfg`). | ✘ |
| 31 | `shinken/modules/` et `containers/ # Dockerfile` (`DEVELOPMENT.md:120, 135`) | `shinken/modules` est inexistant ; le `Containerfile` est à la racine | ✘ |
| 32 | La CI teste Python 3.11 à 3.13, l'image Podman et `podman-lab.sh` (`DEVELOPMENT.md:215-220`) | `.github/workflows/ci.yml:21, 74, 94, 122, 132` | ✔ |
| 33 | Variables d'environnement `SHINKEN_*` de l'entrypoint | `SHINKEN_CONFIG`, `SHINKEN_CONTAINER_DNS`, `SHINKEN_RUNTIME_CONFIG`, `SHINKEN_MODULES_DIR`, `SHINKEN_STATUS_WEBUI` (`entrypoint.sh:6-31`, `compose.yaml:10-12`) | ✘ **aucune n'est documentée** |
| 34 | NRPE : `command_line $PLUGINSDIR$/check_nrpe …`, exemple tiré de `shinken-explorer/sample_config/12-commands.cfg` (`etc/certs/README.md`) | `check_nrpe` se trouve dans `$NAGIOSPLUGINSDIR$` ; le fichier source cité n'existe pas dans le dépôt | ✘ |
| 35 | `certs/` et `ssh_keys/` sont « gitignorés » (`doc/README.md:44`) | `etc/certs/server.key` et `etc/certs/private/cakey.pem` sont **suivis par git** (PKI de démo upstream ; `.gitignore:56` n'a pas d'effet sur des fichiers déjà suivis) | ~ |
| 36 | « after 10s, checks are killed » (`etc/shinken.cfg:48`) | La ligne suivante (`:49`) fixe `service_check_timeout=60` | ✘ (commentaire) |
| 37 | « ping needs CAP_NET_RAW, dropped on purpose by the poller » (`etc/hosts/localhost.cfg:6-7`) | Le poller a bien `NET_RAW` (`compose.yaml:40-41`), ce que confirment la même page ligne 17 et `configuration.md:94-101` | ✘ (commentaire contradictoire) |

**Bilan : 15 ✔, 20 ✘, 2 ~.** Toutes les erreurs graves sont concentrées dans les pages EN (`ARCHITECTURE`, `DATABASE`, `LOGGING`, `DEVELOPMENT`) et dans les commentaires de `etc/`. Ces pages EN ressemblent à du contenu générique produit sans vérification.

### Autres anomalies relevées

#### Liens et rendu

- **Lien faux** : `doc/configuration.md:152` contient « [Configurer l'accès SSH](livestatus-thruk.md) ». Cette page ne parle pas de SSH ; la cible logique est `depannage.md` ou une future page SSH.
- **Ancres `{#id}` non rendues** (`configuration.md:88`, `depannage.md:44`, `exploitation.md:31, 55`). Sans `mkdocs.yml` ni l'extension `attr_list`, GitHub affiche `{#…}` dans le titre. Les liens qui les ciblent sont donc cassés sur GitHub : `presentation.md:92`, `installation.md:133, 139`, `depannage.md:32`.
- **Admonitions `!!! information` et similaires** : elles s'affichent en texte brut sur GitHub.
- **Libellés trompeurs dans `README.rst:23-36`** : ils citent `doc/architecture.md`, `doc/database.md`, etc. en minuscules, alors que les fichiers sont en majuscules. Les cibles sont correctes, mais une copie du libellé échoue sur un système de fichiers sensible à la casse.

#### Index et cohérence entre pages

- **Pages orphelines** : `doc/README.md` (l'index FR) ne référence ni `ARCHITECTURE`, ni `DATABASE`, ni `LOGGING`, ni `METRICS`, ni `QUICKSTART-METRICS`.
- **Contradiction interne sur les logs JSON** : `DEVELOPMENT.md:179` dit « Future work: migrate to structured logging (JSON) », alors que `LOGGING.md` présente la fonction comme livrée et que `bin_utils.py` l'implémente.
- **Incohérence dans `bin_utils.py`** : `add_common_options` (inutilisée) dit que `--verbose` donne le niveau DEBUG (lignes 33-36), alors que `setup_logging_from_options` donne INFO (lignes 92-95).

#### Changelog, version et manpages

- **Changelog** : uniquement upstream, avec une entrée de tête « 3.0.03 - X/X/2017 ». Aucune entrée pour le fork, alors que `pyproject.toml:7` annonce la version `2.4.3`.
- **Manpages** (`manpages/sources/*.rst`) : datées de 2014. Elles ne mentionnent ni `--verbose`, ni `--debug`, ni `--json-logs`, ni `--logfile`, et renvoient à `nagios.cmd`. Elles ne sont pas installées dans l'image.

#### Commentaires et données dans `etc/`

- **Références à des services morts** : `etc/shinken.cfg:132` (« cherrypy3 … swsgiref » ; seul Cheroot existe, `http_daemon.py:67`), `etc/shinken.cfg:136-141` (`kernel.shinken.io`), `etc/packs/readme.cfg` (shinken.io), `etc/templates/generic-host.cfg` (« Look at the wiki »).
- **Contact admin** :
  - `etc/contacts/admin.cfg` utilise `contactgroups admin,users`, alors que seuls `admins` et `users` existent ;
  - son mot de passe est `admin` ;
  - aucune page n'avertit de ces deux points.
- **Hôtes Internet tiers** : `etc/hosts/internet-fun.cfg` supervise `google.fr`, `github.com`, etc. Cela convient pour une démonstration, mais il faut le signaler.
- **Référence absente d'un plugin** : `check_by_ssh_cpu` (`etc/commands/check_by_ssh.cfg`) dépend d'un script distant `check_cpu` qui n'est fourni nulle part.

#### Rétention d'état (probable, à confirmer par l'équipe e2e)

Aucun module de rétention n'est configuré : la ligne `modules` de `etc/schedulers/scheduler-master.cfg` est vide, et aucun module retention n'existe dans `modules/`. Or le rechargement documenté consiste à redémarrer l'arbiter. Les acquittements, downtimes et commentaires seraient donc **perdus à chaque rechargement**. Rien ne le dit à l'administrateur.

#### Commandes de configuration douteuses

- `detailled-host-by-email` a des guillemets cassés (`…$LONGDATETIME$"" -o ""$HOSTSTATE$…`).
- `check_snmp_storage.pl`, `check_snmp_time.pl` et `check_snmp_service` ne sont pas fournis par `nagios-plugins-basic`.
- `check_dig` relève normalement de `-standard`. À vérifier par l'équipe déploiement : le build n'a pas pu être fait ici, faute de réseau dans les conteneurs.

### Informations personnelles mêlées à la doc ou à la config générique

| Emplacement | Contenu |
|---|---|
| `etc/hosts/localhost.cfg:12-20` | hôte de test personnel, IP publique réelle |
| `etc/hosts/<serveur personnel>.cfg`, `etc/services/<serveur personnel>.cfg` | `check_by_ssh_cpu!<compte réel>` |
| `etc/contacts/webteam.cfg` | deux contacts réels, dont un avec son e-mail personnel |
| `DEPLOYMENT.md` (en entier) | le sous-domaine personnel, chemins d'infrastructure privée, comptes du reverse proxy et de Thruk |
| `README.rst:43` | cite `DEPLOYMENT.md` dans la section « Reference » |
| `livestatus-thruk.md:207-217` | anecdotes propres au serveur personnel (reverse proxy, « mot de passe redevient invalide ») présentées comme du dépannage générique |

**Recommandation** : déplacer tout cela dans un répertoire `site/` ou `local/`, ou dans un dépôt d'inventaire privé, et ignorer ce répertoire via `.gitignore`. Ne garder dans `etc/` qu'un exemple neutre (`example.org`, RFC 5737 `192.0.2.x`). Renommer `DEPLOYMENT.md` en `doc/journal/2026-09-deploiement-vps.md`, ou le sortir du dépôt.

---

## 3. Matrice de couverture

Légende : **●** couvert correctement · **◐** partiel ou dispersé · **✘** faux · **○** absent.

### 3.1 Administrateur de la supervision (configuration et plugins, sans code)

| Sujet | Débutant | Avancé | Expert | Où (actuellement) |
|---|---|---|---|---|
| Vue d'ensemble, rôle des daemons | ● | ◐ | ✘ | `presentation.md` ● ; `ARCHITECTURE.md` ✘ |
| Glossaire | ◐ (daemons seulement) | ○ | ○ | `doc/README.md:57-69` |
| Hôte, service, check actif ou passif | ◐ (exemple minimal) | ○ | ○ | `configuration.md` |
| États SOFT/HARD, `max_check_attempts`, `retry_interval` | ○ | ○ | ○ | (commentaires de `generic-service.cfg` seulement) |
| Flapping | ○ | ○ | ○ | (`shinken.cfg:52-58` seulement) |
| Périodes de temps (timeperiods) | ○ | ○ | ○ | `etc/timeperiods/` sans doc |
| Contacts, groupes de contacts, notificationways | ◐ (contact pour Thruk) | ○ | ○ | `livestatus-thruk.md:138-156` |
| Notifications (mail, SMS, webhook) | ○ | ○ | ○ | **cassées par défaut, non signalé** |
| Escalades | ○ | ○ | ○ | `etc/escalations/sample.cfg` |
| Dépendances, parents, impacts | ○ | ○ | ○ | `etc/dependencies/sample.cfg` |
| Groupes d'hôtes et de services | ○ | ○ | ○ | |
| Templates et héritage (`use`, `register 0`, héritage multiple, `+`) | ◐ | ○ | ○ | `configuration.md:77-79` |
| Macros (`$HOSTADDRESS$`, `$ARGn$`, `$USERn$`, `_CUSTOM`) | ○ | ○ | ○ | `etc/resource.d/` sans doc |
| Realms et `poller_tag` | ○ | ○ | ✘ | `ARCHITECTURE.md:164-176` (approximatif) |
| **Écrire un plugin** (codes 0-3, sortie, perfdata, timeout) | ○ | ○ | ○ | **absent** |
| **Intégrer un plugin** (où le déposer, `$USER1$`, droits, rebuild ou montage) | ○ | ✘ | ○ | `DEVELOPMENT.md:224-241` faux |
| Recette Linux via SSH | ◐ | ◐ | ○ | `configuration.md`, `etc/ssh_keys/README.md` |
| Recette Linux et Windows via NRPE/NSClient++ | ◐ (certificats) | ○ | ○ | `etc/certs/README.md` (chemin `$PLUGINSDIR$` faux) |
| Recette SNMP | ○ | ○ | ○ | commandes présentes, plugins absents |
| Recette HTTP/TLS (expiration de certificat, contenu) | ◐ (`check_https_public`) | ○ | ○ | |
| Recette base de données | ○ | ○ | ○ | |
| Downtimes, acquittements, commentaires | ● (ligne de commande Livestatus) | ○ (récurrence, propagation) | ○ | `exploitation.md` |
| Commandes externes (référence) | ◐ (4 commandes) | ○ | ○ | |
| Checks passifs (`PROCESS_SERVICE_CHECK_RESULT`, `send_nsca`, freshness) | ○ | ○ | ○ | `libexec/send_nsca.py` non documenté |
| Packs | ○ | ○ | ○ | `etc/packs/readme.cfg` (shinken.io mort) |
| Thruk / Livestatus | ● | ◐ | ○ | `livestatus-thruk.md` |
| Métriques et perfdata | ◐ (« non disponible ») | ○ | ○ | `METRICS.md` (honnête) |
| Event handlers | ○ | ○ | ○ | |
| Business rules et triggers (spécifiques Shinken) | ○ | ○ | ○ | `etc/sample/triggers.d` |
| Migration depuis Nagios ou Shinken master | ○ | ○ | ○ | |
| FAQ | ○ | | | |
| Dépannage par symptôme | ◐ (journal de bugs du fork) | ◐ | | `depannage.md` |
| Référence complète des directives | ○ | ○ | ○ | |

### 3.2 Exploitant système (hôte Podman)

| Sujet | Débutant | Avancé | Expert | Où |
|---|---|---|---|---|
| Prérequis et installation | ● | | | `installation.md` |
| Démarrage, arrêt, rechargement | ● | ◐ (Thruk reload) | | `exploitation.md`, `livestatus-thruk.md` |
| Logs | ● (`podman logs`) | ✘ (`LOGGING.md`, en partie) | ○ | |
| Variables `SHINKEN_*` et fonctionnement de l'entrypoint | ○ | ○ | ○ | **absent** |
| Volumes, sauvegarde, restauration | ○ | ✘ (`DATABASE.md`) | ○ | |
| Mise à jour de l'image ou du dépôt | ◐ (rebuild) | ○ | ○ | |
| Exposition HTTPS, reverse proxy, authentification | ○ (seulement dans `DEPLOYMENT.md`, version personnelle) | | | |
| Sécurité (pickle, réseau interne, secrets, `cap_drop`) | ◐ | ◐ (`depannage.md`) | ○ | |
| Supervision de la supervision (healthcheck, alerte) | ◐ (`shinken-healthcheck`) | ○ | ○ | |
| Montée en charge, multi-poller, distribution | ○ | ○ | ○ | |
| Rétention d'état | ○ | ○ | ○ | |
| Unités systemd et Quadlet (démarrage au boot en rootless) | ○ | ○ | | |

### 3.3 Développeur

| Sujet | Débutant | Avancé | Expert | Où |
|---|---|---|---|---|
| Environnement de développement et tests | ● | | | `DEVELOPMENT.md:1-104` |
| Architecture du code | ✘ | ✘ | ○ | `ARCHITECTURE.md` (faux) |
| Protocole inter-daemons (HTTP et pickle, `SafeUnpickler`) | ○ | ◐ | ○ | `depannage.md` (sécurité) |
| Écrire un module (`BaseModule`, phases, external ou interne) | ○ | ○ | ○ | docstring de `basemodule.py` uniquement |
| Pièges du portage Python 3 | | ● | | `depannage.md` |
| Contribuer (style, commits, PR) | ◐ | | | `DEVELOPMENT.md`, `CONTRIBUTING.rst` (13 lignes) |
| Changelog du fork | ○ | | | |

---

## 4. Documentation dans le code

### Couverture des docstrings (comptée par AST sur les fonctions et classes)

**Python dans `shinken/` : 203 documentées sur 1934, soit 10,5 %. Dans `modules/` : 25,2 %.**

| Fichier | Documentées / total |
|---|---|
| `shinken/external_command.py` | **0 / 185** (aucune commande n'est décrite, le dictionnaire `commands` n'a pas de commentaires d'arguments) |
| `shinken/daemon.py` | 1 / 77 |
| `shinken/scheduler.py` | 3 / 70 |
| `shinken/objects/host.py` | 3 / 77 |
| `shinken/macroresolver.py` | 1 / 33 |
| `shinken/daemons/brokerdaemon.py` | 1 / 24 |
| `shinken/daemons/arbiterdaemon.py` | 2 / 33 |
| `shinken/objects/config.py` | 9 / 53 (les ~300 propriétés de `Config.properties` n'ont pas de commentaires, alors que c'est la référence naturelle des directives) |
| `shinken/basemodule.py` | 13 / 21, plutôt bon (mais `:69` contient encore `"""TODO: Add some comment about this class for the doc"""`) |
| `shinken/structured_logging.py`, `bin_utils.py`, `pyro_wrapper.py` | bien documentés (code récent) |

### Commentaires obsolètes ou trompeurs hérités de Python 2

- Le nom `cPickle` est conservé comme alias dans 8 modules (`daemon.py:61`, `satellite.py:53`, `objects/config.py:44`…). Le terme induit en erreur sur la sérialisation.
- Le vocabulaire « pyro » apparaît dans 9 commentaires (`satellite.py:245, 862`, « pyro_daemon port »), alors que le transport est HTTP. Ajouté au module mort `pyro_wrapper.py`, c'est probablement ce qui a induit l'erreur de `ARCHITECTURE.md`.
- `shinken/misc/_importlib.py:3` : « code compatible with Python 2.3 ».
- Des appels commentés subsistent : `schedulerdaemon.py:77, 125` (`# return zlib.compress(cPickle.dumps(res), 2)`).
- **7 fichiers contiennent des séquences d'échappement invalides**, qui produisent un `SyntaxWarning` sous Python 3.12+ et deviendront des erreurs : `dependencynode.py:304`, `external_command.py:571`, `macroresolver.py:281`, `objects/config.py:935`, `objects/pack.py:61`, `objects/timeperiod.py:475`, `util.py:582`. Ce sont des regex sans préfixe `r''`. C'est signalé ici parce que cela touche la lisibilité des commentaires et regex ; à transmettre à la revue de code.

### Plugins fournis (`libexec/`)

- `notify_by_email.py` a une aide optparse, mais il n'existe aucune page sur ses options (`-S` SMTP, `-f html`, gabarits) et le script n'est pas installé dans l'image.
- `send_nsca.py`, `notify_by_xmpp.py` et les scripts de mapping (`link_*`, `service_dependency_mapping.py`) n'ont aucune documentation d'usage.

---

## 5. Lacunes priorisées

### P0 : à corriger immédiatement (la doc induit en erreur ou expose des données)

1. **Supprimer ou réécrire `doc/ARCHITECTURE.md`, `doc/DATABASE.md` et `doc/LOGGING.md` §SHINKEN_JSON_LOGS/logging.cfg/nagios.cfg**, ainsi que `DEVELOPMENT.md` § Database, Plugins, Project structure et « configurationmanager ». À défaut, ajouter tout de suite un bandeau « OBSOLÈTE / NON VÉRIFIÉ ».
2. **Trancher la question du logstore** :
   - soit revenir à `logstore-null` dans `etc/modules/livestatus.cfg` ;
   - soit porter réellement `logstore_sqlite`.

   Puis aligner `livestatus-thruk.md:70` et `configuration.md:36`, et documenter que `GET log` (historique et rapports de disponibilité Thruk) dépend de ce choix.
3. **Sortir les données personnelles de `etc/` et de la doc générique** (hôte de test personnel, serveur personnel, contacts réels, `DEPLOYMENT.md`), et retirer `DEPLOYMENT.md` de la section « Reference » du README.
4. **Signaler l'état des notifications** : `notify_by_email.py` est absent de l'image et il n'y a pas de MTA. Donner une page « Notifications » avec une solution qui fonctionne (relais SMTP externe, `libexec` monté ou copié dans l'image).

### P1 : le cœur du besoin de l'administrateur de supervision

5. Guide **« Écrire et intégrer un plugin »** : contrat Nagios (codes 0 à 3, première ligne, perfdata `'label'=val[UOM];warn;crit;min;max`, sortie multiligne), timeouts (`service_check_timeout=60`, `timeout_exit_status=2`), macros `$USER1$`, `$NAGIOSPLUGINSDIR$` et `$PLUGINSDIR$`, **où déposer le script** (montage `./plugins:/var/lib/shinken/libexec:ro`, à prévoir dans `compose.yaml`, ou image dérivée), dépendances (perl, python), test avec `podman exec shinken_poller_1 …`.
6. **Concepts de supervision**, avec un niveau simple et un niveau avancé : SOFT/HARD, actif ou passif, freshness, flapping, timeperiods, contacts et notificationways, escalades, dépendances et parents, groupes, templates et héritage, macros, realms et `poller_tag`, business rules.
7. **Recettes** : Linux via SSH (existe en partie), Linux et Windows via NRPE/NSClient++ (avec le bon chemin), SNMP (avec l'ajout des plugins dans l'image), HTTP/TLS (`check_http -C`), MySQL/PostgreSQL, DNS.
8. **Référence des directives**, éventuellement générée à partir de `Config.properties` et de `Host`/`Service.properties`, et **référence des commandes externes** générée à partir de `ExternalCommandManager.commands`.
9. Documentation de l'**entrypoint et des variables `SHINKEN_*`**, avec un avertissement : les `address` des fichiers `etc/*/xxx-master.cfg` et `modules_dir` sont écrasés quand `SHINKEN_CONTAINER_DNS=1`.

### P2 : exploitation solide

10. Rétention d'état (constat, risque, configuration d'un module), sauvegarde et restauration (`etc/`, volumes `shinken-data` et `shinken-logs`), procédure de mise à jour.
11. Exposition sécurisée (reverse proxy, authentification, ne jamais publier les ports 7768-7773), démarrage au boot (Quadlet ou `podman generate systemd`).
12. Dépannage réorganisé **par symptôme** (« service en PENDING », « (null) output », « notification non reçue », « Thruk vide »), en séparant le journal historique des bugs du fork.
13. Index unique, une seule langue (FR pour admin et exploitation, EN toléré pour les pages dev), `mkdocs.yml` ou conversion des admonitions en blockquotes GitHub (`> [!NOTE]`).

### P3 : finitions

14. Changelog du fork (`CHANGELOG-fork.md`), manpages mises à jour (options de logs), docstrings de `external_command.py` et `config.py`, nettoyage des commentaires `cPickle`/`pyro`, correction des commentaires `etc/shinken.cfg:48, 132, 136` et `localhost.cfg:6`.
15. Migration depuis Nagios ou Shinken 2.x, FAQ, glossaire complet.

---

## 6. Proposition d'arborescence cible pour `doc/`

**Principes :**

- un index par public ;
- préfixes numériques par niveau : `0x` démarrage / simple, `1x` avancé, `2x` expert, `9x` référence ;
- français pour `admin/` et `exploitation/`, anglais possible pour `dev/` ;
- front-matter actuel conservé ;
- `mkdocs.yml` ajouté (Material, `attr_list`, `admonition`), ou bien Markdown GitHub pur.

Statuts : **GARDER** (tel quel ou retouches mineures) · **RÉÉCRIRE** (base existante, à corriger ou déplacer) · **CRÉER**.

```
doc/
├── README.md                         index général : « Je suis admin / exploitant / développeur »
├── glossaire.md
├── faq.md
├── admin/                            ← ADMINISTRATEUR DE LA SUPERVISION (config + plugins, zéro code)
│   ├── README.md
│   ├── 00-presentation.md
│   ├── 01-demarrage-rapide.md
│   ├── 02-concepts-essentiels.md
│   ├── 03-hotes-et-services.md
│   ├── 04-commandes-et-plugins.md
│   ├── 05-contacts-et-notifications.md
│   ├── 06-downtimes-acquittements.md
│   ├── 07-thruk-livestatus.md
│   ├── recettes/
│   │   ├── linux-ssh.md
│   │   ├── linux-windows-nrpe.md
│   │   ├── snmp.md
│   │   ├── http-tls.md
│   │   ├── bases-de-donnees.md
│   │   └── dns-ping-tcp.md
│   ├── 10-templates-heritage-macros.md
│   ├── 11-periodes-et-calendriers.md
│   ├── 12-ecrire-un-plugin.md
│   ├── 13-checks-passifs.md
│   ├── 14-escalades.md
│   ├── 15-dependances-et-impacts.md
│   ├── 16-groupes-et-organisation.md
│   ├── 17-flapping-et-volatilite.md
│   ├── 18-event-handlers.md
│   ├── 20-business-rules.md
│   ├── 21-realms-et-poller-tags.md
│   ├── 22-triggers.md
│   ├── 23-migration-nagios.md
│   ├── 24-metriques-perfdata.md
│   └── 90-reference/
│       ├── directives-shinken-cfg.md
│       ├── objets-host.md, objets-service.md, objets-contact.md, …
│       ├── macros.md
│       ├── commandes-externes.md
│       └── livestatus-colonnes.md
├── exploitation/                     ← EXPLOITANT SYSTÈME (hôte Podman)
│   ├── README.md
│   ├── 01-installation.md
│   ├── 02-operations-courantes.md
│   ├── 03-logs.md
│   ├── 04-depannage-par-symptome.md
│   ├── 10-conteneurs-entrypoint.md
│   ├── 11-sauvegarde-restauration.md
│   ├── 12-mise-a-jour.md
│   ├── 13-exposition-securisee.md
│   ├── 14-demarrage-au-boot.md
│   ├── 15-surveiller-la-supervision.md
│   ├── 20-retention-etat.md
│   ├── 21-distribution-haute-dispo.md
│   └── 22-securite.md
├── dev/                              ← DÉVELOPPEUR (EN accepté)
│   ├── README.md
│   ├── 01-environnement-tests.md
│   ├── 10-architecture.md
│   ├── 11-protocole-inter-daemons.md
│   ├── 12-ecrire-un-module.md
│   ├── 13-livestatus-interne.md
│   ├── 20-portage-python3.md
│   └── 21-contribuer.md
└── journal/                          ← historique, non normatif
    ├── 2026-09-deploiement-vps.md
    └── bugs-corriges-du-fork.md
```

### Contenu attendu et statut, page par page

#### Racine de `doc/`

| Page | Contenu attendu | Statut / source |
|---|---|---|
| `doc/README.md` | Trois parcours (admin, exploitant, dev) × trois niveaux, avec un lien par page. Toutes les pages y figurent, aucune orpheline. | RÉÉCRIRE (`doc/README.md`, à étendre) |
| `glossaire.md` | Termes de supervision (SOFT/HARD, flapping, impact, brok, realm, pack…) en plus des daemons | RÉÉCRIRE (extraire de `doc/README.md:57-69`) |
| `faq.md` | 20 questions courantes : « pourquoi PENDING », « où mettre mon script », « pourquoi pas de mail »… | CRÉER |

#### `admin/` : administrateur de la supervision

| Page | Contenu attendu | Statut / source |
|---|---|---|
| `admin/README.md` | Parcours simple → avancé → expert | CRÉER |
| `00-presentation.md` | Ce que fait Shinken, les daemons en une phrase, ce qui change par rapport à Nagios | GARDER (`presentation.md`, mettre à jour : logstore, 8081) |
| `01-demarrage-rapide.md` | Premier hôte et premier service en 10 minutes : éditer `etc/`, redémarrer, vérifier dans Thruk ou avec `shinken-healthcheck`. Exemples neutres. | RÉÉCRIRE (fusion de `configuration.md` §Ajouter et `exploitation.md` §Appliquer) |
| `02-concepts-essentiels.md` | Hôte et service ; check actif et passif ; états OK/WARN/CRIT/UNKNOWN et UP/DOWN/UNREACHABLE ; **SOFT/HARD** avec un schéma temporel `check_interval` / `retry_interval` / `max_check_attempts` ; notifications ; acquittement ; downtime | CRÉER |
| `03-hotes-et-services.md` | Directives courantes avec des exemples copiables. Organisation des fichiers sous `etc/`. Caractères interdits. Validation avec `shinken-arbiter -v`. | RÉÉCRIRE (`configuration.md` §1-2) |
| `04-commandes-et-plugins.md` | `define command`, `$ARGn$`, `!`, `$NAGIOSPLUGINSDIR$` / `$USER1$` / `$PLUGINSDIR$` (`etc/resource.d/paths.cfg`), liste des plugins réellement présents dans l'image, comment tester un plugin à la main dans le poller | CRÉER |
| `05-contacts-et-notifications.md` | Contacts, groupes, notificationways, options `d,u,r,f,s` / `w,u,c,r`, `notification_interval`. **État réel du mail dans le conteneur** et solutions (relais SMTP, script webhook, SMS). Mot de passe `admin` à changer. | CRÉER |
| `06-downtimes-acquittements.md` | Via Thruk et via Livestatus (snippets actuels), downtimes fixes ou flexibles, propagation, `sticky`/`persistent`. **Avertissement sur la perte en cas de reload sans rétention.** | RÉÉCRIRE (`exploitation.md` §Downtime/Ack) |
| `07-thruk-livestatus.md` | Brancher Thruk, contacts et `AuthUser`, boutons Reload/Restart | GARDER (`livestatus-thruk.md`, corriger le logstore et retirer les anecdotes du serveur personnel) |
| `recettes/linux-ssh.md` | Clé dédiée, `command=` figé, `podman unshare`, script distant exemple fourni | RÉÉCRIRE (`configuration.md` §SSH, `etc/ssh_keys/README.md`) |
| `recettes/linux-windows-nrpe.md` | NRPE v4 / TLS, NSClient++, certificats, commande `check_nrpe` avec le **bon** chemin | RÉÉCRIRE (`etc/certs/README.md`) |
| `recettes/snmp.md` | Plugins SNMP à ajouter à l'image, communauté (`$SNMPCOMMUNITYREAD$`, `etc/resource.d/snmp.cfg`), exemples | CRÉER |
| `recettes/http-tls.md` | `check_http` contenu et code HTTP, `-C 30,14` pour l'expiration de certificat | CRÉER |
| `recettes/bases-de-donnees.md` | `check_mysql`, `check_pgsql`, compte de supervision en lecture seule | CRÉER |
| `recettes/dns-ping-tcp.md` | `check_icmp` et `NET_RAW`, `check_tcp`, `check_dig` | CRÉER |
| `10-templates-heritage-macros.md` | `name`/`register 0`, `use a,b` (ordre), `+` additif, `null`, macros custom `_VAR`, macros on-demand | CRÉER |
| `11-periodes-et-calendriers.md` | Syntaxe des timeperiods, exclusions, jours fériés (`etc/timeperiods/*`) | CRÉER |
| `12-ecrire-un-plugin.md` | **Contrat complet** : codes retour, sortie et perfdata, longue sortie, timeout (`service_check_timeout`), bonnes pratiques (idempotent, rapide, pas d'interactif) ; squelettes bash et Python ; où le déposer (montage proposé `./plugins` → `/var/lib/shinken/libexec`) ; droits sous rootless ; tester | CRÉER |
| `13-checks-passifs.md` | `PROCESS_*_CHECK_RESULT` via Livestatus, `send_nsca.py`, `check_freshness` / `freshness_threshold` ; limites du receiver (pas de module NSCA) | CRÉER |
| `14-escalades.md` | `serviceescalation` / `escalation`, `first_notification`… | CRÉER (à partir de `etc/escalations/sample.cfg`) |
| `15-dependances-et-impacts.md` | `parents`, `servicedependency`, `enable_problem_impacts_states_change` | CRÉER |
| `16-groupes-et-organisation.md` | hostgroups et servicegroups, application de services à des groupes, convention de fichiers | CRÉER |
| `17-flapping-et-volatilite.md` | Seuils, `flap_history`, `is_volatile` | CRÉER |
| `18-event-handlers.md` | Auto-remédiation, `no_event_handlers_during_downtimes` | CRÉER |
| `20-business-rules.md` | `bp_rule`, agrégats (spécifique Shinken) | CRÉER |
| `21-realms-et-poller-tags.md` | Distribution logique (expert) | CRÉER |
| `22-triggers.md` | `etc/sample/triggers.d`, à documenter ou à déclarer non supporté | CRÉER |
| `23-migration-nagios.md` | Ce qui est compatible, ce qui ne l'est pas (`nagios.cfg` → `shinken.cfg`, `resource.cfg`, `command_file`), check-list | CRÉER |
| `24-metriques-perfdata.md` | État honnête (pas d'export) et pistes | RÉÉCRIRE (fusion de `METRICS.md` et `QUICKSTART-METRICS.md`) |
| `90-reference/directives-shinken-cfg.md` | Chaque directive de `shinken.cfg` : défaut, unité, effet | CRÉER (idéalement générée à partir de `shinken/objects/config.py` `properties`) |
| `90-reference/objets-host.md`, `objets-service.md`, `objets-contact.md`, … | Une page par type d'objet | CRÉER (générées depuis `Host.properties`, `Service.properties`…) |
| `90-reference/macros.md` | Toutes les macros | CRÉER (depuis `macroresolver.py` et `Host`/`Service.macros`) |
| `90-reference/commandes-externes.md` | Liste et arguments | CRÉER (générée depuis `ExternalCommandManager.commands`) |
| `90-reference/livestatus-colonnes.md` | Tables et colonnes supportées | CRÉER (depuis `modules/livestatus/mapping.py`) |

#### `exploitation/` : exploitant système

| Page | Contenu attendu | Statut / source |
|---|---|---|
| `exploitation/README.md` | Index | CRÉER |
| `01-installation.md` | Prérequis, build, `up`, validation, retour arrière | GARDER (`installation.md`) |
| `02-operations-courantes.md` | Reload, rebuild, redémarrage d'un daemon, `shinken-healthcheck` | RÉÉCRIRE (`exploitation.md` hors ack/downtime) |
| `03-logs.md` | `podman logs`, fichiers `*d.log`, `log_level` dans `etc/daemons/*.ini`, options `--json-logs`/`--verbose`/`--logfile` (**réelles**) et comment les passer via `command:` dans compose | RÉÉCRIRE (`LOGGING.md` purgé de `SHINKEN_JSON_LOGS` et `logging.cfg`) |
| `04-depannage-par-symptome.md` | Arbre de décision : PENDING, `(null)`, arbiter en boucle, pidfile, permissions, Thruk vide, commande sans effet, notification absente | RÉÉCRIRE (`depannage.md` + `installation.md` §Dépannage) |
| `10-conteneurs-entrypoint.md` | Rôles, **variables `SHINKEN_*`**, copie vers `/tmp/shinken-config`, réécriture des adresses et de `modules_dir`, volumes, UID 10001, `cap_drop`, profil `experimental-metrics` | CRÉER |
| `11-sauvegarde-restauration.md` | `etc/` (git), volumes `shinken-data` et `shinken-logs` (`podman volume export`), ce qui n'est pas persistant | CRÉER |
| `12-mise-a-jour.md` | `git pull`, rebuild, `--force-recreate`, vérifications, retour arrière | CRÉER |
| `13-exposition-securisee.md` | Reverse proxy générique (Caddy ou nginx), authentification, ne jamais exposer 50000 ni 7768-7773 | CRÉER (à partir de `DEPLOYMENT.md` dépersonnalisé) |
| `14-demarrage-au-boot.md` | Quadlet ou systemd rootless, `loginctl enable-linger` | CRÉER |
| `15-surveiller-la-supervision.md` | Healthcheck externe, `--stale-after`, alerte si Shinken est mort | CRÉER |
| `20-retention-etat.md` | Constat (pas de module), conséquences, solution | CRÉER |
| `21-distribution-haute-dispo.md` | Plusieurs pollers, spares, `poller_tag`, pollers distants | CRÉER |
| `22-securite.md` | Pickle et `SafeUnpickler`, réseau interne, secrets (PKI de démo à ne pas utiliser), comptes par défaut | RÉÉCRIRE (`depannage.md` §sécurité + nouveau) |

#### `dev/` : développeur

| Page | Contenu attendu | Statut / source |
|---|---|---|
| `dev/README.md` | Index | CRÉER |
| `01-environnement-tests.md` | Installation `-e .[dev]`, pytest, ruff, CI, `podman-lab.sh` | RÉÉCRIRE (`DEVELOPMENT.md` §1-104 et §181-220, sans §Database ni §Plugins) |
| `10-architecture.md` | Flux **réels** : arbiter → dispatch HTTP ; scheduler ↔ poller/reactionner en pull ; broker qui tire les broks ; modules ; arborescence `shinken/` réelle | RÉÉCRIRE complètement (`ARCHITECTURE.md`) |
| `11-protocole-inter-daemons.md` | Routes HTTP, `http_client`, base64+zlib+pickle, `SafeUnpickler`, ports 7768-7773 | CRÉER |
| `12-ecrire-un-module.md` | `BaseModule`, `properties`, interne ou externe, phases, `get_instance`, exemples `dummy_*` | CRÉER |
| `13-livestatus-interne.md` | Structure de `modules/livestatus/`, logstores, limites | CRÉER |
| `20-portage-python3.md` | Pièges rencontrés (fork deadlock, `copy_reg`, `long`…) et méthode grep | RÉÉCRIRE (sections « bugs » de `depannage.md`) |
| `21-contribuer.md` | Style, commits, docstrings attendues, Changelog du fork | RÉÉCRIRE (`CONTRIBUTING.rst`) |

#### `journal/` : historique, non normatif

| Page | Contenu attendu | Statut / source |
|---|---|---|
| `2026-09-deploiement-vps.md` | Journal brut, **dépersonnalisé**, ou sorti du dépôt | RÉÉCRIRE (`DEPLOYMENT.md`) |
| `bugs-corriges-du-fork.md` | Historique des corrections | RÉÉCRIRE (depuis `depannage.md`) |

**Pages actuelles à supprimer ou fusionner** : `DATABASE.md` (SUPPRIMER, puis réécrire une courte section dans `07-thruk-livestatus.md` quand un logstore réel existera), `QUICKSTART-METRICS.md` (FUSIONNER), `README` (doublon de `README.rst`, à SUPPRIMER ou transformer en lien).

**Hors de `doc/`** :

- `README.rst` : retirer `DEPLOYMENT.md` de la section « Reference » et pointer vers les trois index.
- `CHANGELOG` : créer une section fork.
- `manpages/` : ajouter les options de logs.
- `etc/` : commentaires corrigés et exemples neutres. Créer un `etc/README.md` qui explique chaque répertoire.

---

## 7. Points forts à conserver

- Le gabarit des fiches FR : front-matter, Objectif, Prérequis, Étapes, Résultat attendu, Validation, Retour arrière, Dépannage. Il est très adapté à un public d'exploitation.
- Les avertissements concrets et vécus : `service_description` avec parenthèses, `podman unshare`, `--network` dès la création, `command=` figé côté SSH.
- `METRICS.md` et `QUICKSTART-METRICS.md` assument honnêtement que la fonction n'est pas disponible : c'est le bon ton à généraliser.
- `depannage.md` documente avec précision des correctifs de sécurité réels (`SafeUnpickler`), ce qui a de la valeur pour les développeurs.
