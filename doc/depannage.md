---
title: "Dépanner Shinken"
domain: "Shinken"
type: "guide"
level: "avance"
duration: "15 min"
version: "1.0"
updated: "2026-09-13"
owner: "Administration Supervision"
status: "valid"
order: 7
keywords: [depannage, bugs, python3, podman, pickle, securite]
summary: "Bugs réels déjà rencontrés et corrigés dans ce fork, pour ne pas relancer une enquête déjà faite."
---

# Dépanner Shinken

Cette fiche liste des bugs **réels, déjà identifiés et corrigés** dans ce
fork, découverts en le faisant tourner en conditions réelles. Avant de
relancer une investigation longue sur un symptôme qui y ressemble, vérifier
ici d'abord.

## "Les checks ne s'exécutent jamais"

Deux causes possibles, très différentes :

!!! depannage "Cause la plus probable : patience, pas un bug"
    Shinken étale ses checks initiaux sur `max_service_check_spread`
    minutes (5 par défaut, `etc/shinken.cfg`) après un (re)démarrage, pour
    éviter un pic de charge. Attendre 5 minutes sans toucher aux containers
    avant de conclure à un blocage — chaque redémarrage relance ce délai.
    Voir [Forcer un check](exploitation.md#forcer-un-check) pour ne pas
    attendre.

!!! depannage "Cause réelle trouvée une fois : deadlock au fork des modules externes"
    `shinken/basemodule.py` (`BaseModule._main()`) appelait
    `shinken.http_daemon.daemon_inst.shutdown()` dans le process forké d'un
    **module externe** (livestatus, etc.), ce qui bloque indéfiniment en
    attendant des threads qui n'existent que dans le process parent. Corrigé
    en Python 3 en ne cherchant plus à arrêter le serveur hérité côté enfant.
    Si un module externe se lance ("is now started ; pid=...") mais ne fait
    plus jamais rien ensuite, chercher ce symptôme.

## "Configuration is incorrect, sorry, I bail out" en boucle {#caracteres-interdits}

Vérifier d'abord les `service_description` : Shinken rejette purement et
simplement les caractères `(` et `)`
(`My service_description got the character ( that is not allowed`), et fait
planter **l'arbiter entier** au chargement, pas juste ce service en
particulier. `CPU (SSH)` → `CPU via SSH`.

!!! information "Piège de diagnostic"
    Si ce crash survient juste après avoir testé une toute nouvelle
    fonctionnalité (un check SSH par exemple), il est tentant d'accuser
    cette fonctionnalité. Vérifier d'abord les logs complets de l'arbiter
    (`podman logs shinken_arbiter_1 | grep -i "not allowed\|incorrect"`)
    avant de creuser ailleurs.

## Les commandes externes (force check, ack, downtime) n'ont aucun effet

Deux bugs distincts trouvés et corrigés dans ce fork :

- `shinken/objects/satellitelink.py` : `get_external_commands()` faisait
  `cpickle.loads(str(tab))` sur des bytes Python 3 — l'exception était
  avalée silencieusement par un `except:` nu, donc rien ne semblait se
  passer, sans erreur visible. Le format réel de la réponse est du pickle
  brut, pas du base64+zlib+pickle comme pour `get_broks`.
- `shinken/daemons/brokerdaemon.py` : le **Broker** n'avait tout simplement
  jamais de méthode `get_external_commands()` (Poller/Reactionner
  l'héritent gratuitement de `Satellite`/`BaseSatellite`, le Broker a sa
  propre hiérarchie de classes qui ne l'inclut pas).

Si une commande externe reste sans effet après ces correctifs, vérifier que
le nom de la commande envoyée est bien reconnu par
`shinken/external_command.py` — Thruk envoie par exemple `RESTART_PROCESS`
pour son bouton "Restart", alors que seul `RESTART_PROGRAM` existait dans le
code : ajouté comme alias.

## Régression de sécurité : désérialisation pickle non protégée

`shinken/safepickle.py` (`SafeUnpickler`) existe précisément pour rejeter
des payloads pickle non sûrs — ajouté suite à un vrai historique de CVE où
un payload forgé envoyé au port interne d'un daemon pouvait exécuter du
code (voir le fichier `Changelog`, rapport de l'équipe Dailymotion). Six
points d'entrée réseau contournaient cette protection en important
`pickle` brut via `shinken.imports.cpickle` :

- `shinken/scheduler.py` (résultats passifs des pollers/reactionners)
- `shinken/daemons/brokerdaemon.py` (broks reçus des schedulers)
- `shinken/daemons/arbiterdaemon.py` (conf poussée à un arbiter de secours)
- `shinken/daemons/schedulerdaemon.py` (conf poussée au scheduler — le
  chemin principal de dispatch de config, sollicité à chaque reload)
- `shinken/satellite.py` (checks/actions récupérés par poller/reactionner)
- `shinken/objects/satellitelink.py` (commandes externes)

Tous corrigés pour utiliser `SafeUnpickler.loads()`.

!!! information "Pourquoi ça n'avait jamais été branché"
    Le corriger a immédiatement fait planter le scheduler avec
    `ModuleNotFoundError: No module named 'copy_reg'` — un second bug, **dans
    la protection elle-même** : `SafeUnpickler.find_class()` reconnaissait
    les noms de modules Python 2 (`copy_reg`, `__builtin__`) que les flux
    pickle référencent encore, mais essayait de les importer sous ces noms
    exacts, absents de Python 3. Corrigé avec une table d'alias
    (`copy_reg`→`copyreg`, `__builtin__`→`builtins`). C'est probablement
    *pourquoi* `SafeUnpickler` n'avait jamais été branché sur ces six points
    pendant le portage — ça plantait instantanément.

## Un container reste bloqué en boucle de redémarrage

```
valid pidfile exists (pid=2) and not forced to replace. Exiting.
```

Le container tourne, se relance via `restart: unless-stopped`, mais un
pidfile périmé l'empêche de redémarrer proprement à chaque tentative. Sortir
de la boucle avec un cycle complet plutôt qu'un simple restart :

```bash
podman stop <container>
podman rm <container>
podman-compose up -d <service>
```

Si **plusieurs** containers de la stack sont affectés simultanément, faire
le cycle complet sur toute la stack (`podman-compose down` puis `up -d`)
plutôt que container par container.

## Permissions d'un secret monté (clef SSH, certificat) refusées côté container

Sous Podman rootless, les UID à l'intérieur d'un container sont **remappés**
par rapport à l'hôte (`podman unshare cat /proc/self/uid_map` pour voir le
mapping exact). Un `chown`/`chmod` classique sur le fichier monté cible le
mauvais UID réel côté hôte.

```bash
podman unshare chown 10001:10001 etc/ssh_keys/ma_clef
podman unshare chmod 600 etc/ssh_keys/ma_clef
podman restart <container concerné>   # souvent necessaire pour que le montage reprenne le nouvel etat
```

Symptôme typique si ignoré : `stat`/`cat` renvoie `Permission denied` sur le
fichier depuis le container, alors que les permissions semblent correctes
vues de l'hôte.

## Pour aller plus loin

- [Configurer Shinken](configuration.md)
- [Exploiter Shinken au quotidien](exploitation.md)
- [Brancher Thruk via Livestatus](livestatus-thruk.md)
