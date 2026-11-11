# Comment un check est exécuté et récolté

**Public :** administrateur de la supervision, niveau simple à avancé. Cette
page explique ce qui se passe **entre** la définition d'un service et
l'affichage de son état : qui décide, qui exécute, par où passe le résultat.
Pour les notions d'état (OK, SOFT/HARD…), lisez d'abord les
[concepts essentiels](02-concepts.md).

## En une phrase

Le **scheduler** décide *quand* vérifier, le **poller** *exécute* le plugin,
le scheduler *interprète* le résultat, le **broker** le *publie* (Thruk,
page d'état). Pour un check passif, rien n'est exécuté : le résultat arrive
de l'extérieur et rejoint le même circuit au niveau du scheduler.

```
                 ┌────────────────────── check ACTIF ──────────────────────┐
                 │                                                          │
  configuration  │  Scheduler ──(1) crée le check à l'heure prévue          │
  (arbiter) ────►│     │                                                    │
                 │     │  (2) le poller vient chercher le travail          │
                 │     ▼      GET /get_checks                               │
                 │  Poller ── worker ── (3) lance le plugin (sous-processus)│
                 │     │                                                    │
                 │     │  (4) renvoie le résultat  POST /put_results        │
                 │     ▼                                                    │
                 │  Scheduler ── (5) consomme : état, SOFT/HARD,           │
                 │     │             notifications, event handler           │
                 └─────┼────────────────────────────────────────────────────┘
                       │  (6) broks (changement d'état)
                       ▼
                    Broker ──► Livestatus ──► Thruk
                       ▲                         │
                       │ commande externe        │  PROCESS_SERVICE_CHECK_RESULT
                       └──────── check PASSIF ◄──┘  (script, Thruk, outil tiers)
```

## Le check actif, étape par étape

### 1. Le scheduler planifie

Au chargement de la configuration, le scheduler calcule pour chaque hôte et
service l'heure de son premier check. Pour éviter que tout parte à la même
seconde, ces premiers checks sont **étalés** sur
`max_service_check_spread` minutes (5 dans `etc/shinken.cfg`).

> **Note** — C'est pour cela qu'après un démarrage ou un rechargement, les
> services restent **PENDING** jusqu'à 5 minutes. Ce n'est pas une panne :
> attendez, ou forcez un check depuis Thruk. Ne redémarrez pas en boucle,
> chaque redémarrage relance l'étalement.

Ensuite, chaque check suivant est placé :

- `check_interval` minutes après le précédent en temps normal ;
- `retry_interval` minutes après pendant un état SOFT ;
- jamais en dehors de la `check_period` (le check est repoussé au début de
  la plage suivante).

L'unité est la minute parce que `interval_length` vaut 60 secondes.

Au moment voulu, le scheduler crée un objet *check* qui contient la ligne
de commande **déjà résolue** : toutes les macros (`$HOSTADDRESS$`,
`$ARG1$`, `$USER1$`, `$SSHKEY$`…) sont remplacées par le scheduler. Le
poller ne voit jamais une macro, seulement la commande finale.

Le check passe par les états internes suivants, visibles dans les journaux
en mode debug :

| État | Signification |
|---|---|
| `scheduled` | créé, en attente de son heure |
| `inpoller` | pris par un poller, en cours d'exécution |
| `waitconsume` | résultat revenu, pas encore interprété |
| `zombie` | interprété, sera supprimé |

### 2. Le poller vient chercher le travail

Le poller **tire** le travail : toutes les `polling_interval` secondes (1
par défaut), il appelle `GET /get_checks` sur chaque scheduler qu'il sert.
Le scheduler lui donne les checks dont l'heure est arrivée.

Deux filtres décident quel poller reçoit quel check :

- le **realm** : un poller ne sert que les schedulers de son realm ;
- les **poller_tags** : un service qui porte `poller_tag DMZ` n'est confié
  qu'à un poller déclaré avec `poller_tags DMZ`. Un service sans tag va à
  un poller qui accepte `None` (valeur par défaut). C'est ainsi qu'on fait
  exécuter certains checks depuis un poller placé dans une autre zone
  réseau (voir [architecture distribuée](20-architecture-distribuee.md)).

> **Note** — Un poller déclaré `passive 1` fonctionne à l'envers : c'est le
> scheduler qui lui pousse le travail (`/push_actions`) et vient chercher
> les résultats (`/get_returns`). Utile quand le poller est derrière un
> pare-feu qui interdit les connexions sortantes vers le scheduler.

### 3. Un worker lance le plugin

Dans le poller, les checks sont répartis entre des **workers** : des
processus enfants dont chacun exécute jusqu'à `processes_by_worker` (256)
plugins en parallèle. Le nombre de workers est fixé par `max_workers` dans
la définition du poller (`etc/pollers/`) ; `0` signifie « un par
processeur ». Ils sont tous créés au démarrage et maintenus à ce nombre.

Pour chaque check, le worker lance un sous-processus :

- **sans shell** si la commande ne contient aucun caractère spécial : la
  ligne est découpée comme le ferait un shell (guillemets respectés) et le
  programme est exécuté directement ;
- **avec `/bin/sh -c`** si elle contient l'un des caractères
  ``! $ ^ & * ( ) ~ [ ] | { } ; < > ? ` ``. Une redirection, un pipe ou une
  variable d'environnement fonctionnent donc, au prix d'un shell
  supplémentaire.

Le plugin hérite de l'environnement du conteneur poller : utilisateur
`shinken` (UID 10001), `HOME=/var/lib/shinken`, répertoire de travail du
daemon. Il ne reçoit **aucun terminal** : un plugin qui demande un mot de
passe ou une confirmation reste bloqué jusqu'au timeout.

Le worker lit la sortie standard (et la sortie d'erreur si la sortie
standard est vide) au fil de l'eau, jusqu'à `max_plugins_output_length`
octets (8 192).

### 4. Délais dépassés et codes retour anormaux

| Situation | Ce que fait Shinken | État affiché |
|---|---|---|
| Le plugin dépasse `service_check_timeout` (60 s) ou `host_check_timeout` (30 s) | tue **tout le groupe de processus** du plugin (lui et ses enfants) | `timeout_exit_status` (2 = CRITICAL) avec la sortie `(Service Check Timed Out)` |
| Code retour 0, 1, 2 ou 3 | normal | OK, WARNING, CRITICAL, UNKNOWN |
| Code retour hors de 0 à 3 (126 « non exécutable », 127 « introuvable », 255 erreur SSH…) | ramené à 3 | UNKNOWN, avec le message d'erreur du plugin ou `Abnormal termination with code: N` |
| Erreur de syntaxe du shell (guillemet non fermé) | ramené à 3 | UNKNOWN |
| Aucune sortie | — | sortie vide, l'état suit le code retour |

> **Attention** — Le timeout du plugin et celui de Shinken sont deux choses
> différentes. `check_by_ssh -t 15` abandonne au bout de 15 s et rend
> lui-même UNKNOWN ou CRITICAL avec un message clair ; si vous l'oubliez, le
> plugin peut attendre jusqu'aux 60 s de Shinken et vous n'aurez que
> `(Service Check Timed Out)`. Donnez toujours au plugin un délai plus court
> que celui de Shinken.

### 5. Le résultat revient au scheduler

Le worker dépose le résultat dans une file ; le poller les renvoie par lot
au scheduler (`POST /put_results`). Si un poller meurt avec des checks en
cours, le scheduler les considère **orphelins** après un délai et les
replanifie.

### 6. Le scheduler interprète

C'est là, et seulement là, que le résultat devient un état :

1. la sortie est découpée : première ligne = message (*Status
   Information*), texte après `|` = **perfdata**, lignes suivantes =
   *long output* ;
2. le code retour donne l'état ; le compteur de tentatives est mis à jour
   (SOFT 1/3, 2/3, puis HARD) ;
3. si l'état change : **event handler** éventuel, détection de
   **flapping** ;
4. si l'état est HARD et notifiable : création d'une **notification**,
   confiée au **reactionner** exactement comme un check l'est au poller ;
5. pour un hôte en échec : vérification des **parents** (DOWN ou
   UNREACHABLE) ; pour un service : prise en compte des **dépendances** ;
6. émission d'un **brok** (message d'état) que le broker récupère.

### 7. Le broker publie

Le broker vient chercher les broks (`GET /get_broks`) et les donne à ses
modules : **Livestatus** (que lit Thruk), la page d'état intégrée,
l'historique SQLite. Thruk n'interroge jamais le scheduler : il voit ce que
Livestatus sait, donc avec un décalage d'une à deux secondes.

## Le check passif

Un check passif est un résultat **soumis** à Shinken au lieu d'être mesuré
par lui. Le chemin, du point de vue du code :

```
Script / Thruk / outil tiers
   │  COMMAND [horodatage] PROCESS_SERVICE_CHECK_RESULT;hôte;service;code;sortie|perfdata
   ▼
Broker (module Livestatus, port 50000)
   │  l'arbiter interroge le broker : GET /get_external_commands
   ▼
Arbiter : trouve le scheduler qui gère cet hôte
   │  POST /run_external_commands
   ▼
Scheduler : traite le résultat EXACTEMENT comme un résultat de poller
            (étape 6 ci-dessus : SOFT/HARD, notifications…)
```

Points importants :

- **Rien n'est exécuté**, donc ni poller, ni plugin, ni timeout. Le code
  retour et la sortie sont ceux que l'émetteur a choisis.
- Le service doit accepter les résultats passifs
  (`passive_checks_enabled 1`, valeur par défaut) ; on désactive en général
  les checks actifs (`active_checks_enabled 0`).
- Un service passif dont l'émetteur s'arrête ne change **jamais d'état**
  tout seul. C'est le rôle de la **fraîcheur** (*freshness*) : avec
  `check_freshness 1` et `freshness_threshold` (secondes), si aucun résultat
  n'est arrivé à temps, le scheduler exécute **activement** la
  `check_command` du service, typiquement
  `check_dummy!2!Aucun résultat depuis 26 h`. Un service passif sans
  freshness est un angle mort.
- La commande peut arriver par Livestatus (port 50000), par le tube nommé
  `nagios.cmd` (module `named-pipe`) ou depuis un bouton de Thruk
  (*Submit passive check result*). Ces canaux n'ont **pas
  d'authentification** : ne les exposez jamais hors du serveur.

Procédure complète, exemple de sauvegarde nocturne et soumission à
distance par SSH : [checks passifs et commandes externes](15-checks-passifs-commandes-externes.md).

### Actif ou passif : que choisir ?

| Situation | Choix |
|---|---|
| Shinken peut joindre la cible et y lancer une mesure | **actif** (cas normal) |
| Le résultat n'existe qu'à la fin d'un traitement (sauvegarde, batch, synchro) | **passif** + freshness |
| La cible ne peut pas être jointe depuis le serveur (réseau isolé, NAT) | **passif** poussé par la cible, ou **poller** placé dans ce réseau |
| Un logiciel tiers détecte déjà le problème (antivirus, application) | **passif** |
| Vous voulez un « battement de cœur » d'une application | **passif** + freshness courte |

## Le cas des hôtes

Un hôte se vérifie comme un service (sa `check_command`, souvent
`check_host_alive` ou `check_tcp!22`), avec trois particularités :

- un hôte n'a pas d'état WARNING : code 1 = UP, 2 et 3 = DOWN ;
- un hôte sans `check_command` est **supposé UP** (check interne
  `_internal_host_up`, sortie `Host assumed to be UP`) ;
- quand un service d'un hôte passe en erreur, Shinken peut vérifier
  l'hôte **à la demande** pour savoir si c'est le service ou la machine
  entière qui est en panne.

## Où regarder quand un check ne se comporte pas comme prévu

| Question | Où regarder |
|---|---|
| Quelle commande exacte a été lancée ? | Thruk, page du service, carte *Check Command* / *Expanded Command* (voir [Thruk : comptes et droits](../thruk/03-comptes-et-droits.md) pour l'afficher) |
| Le plugin marche-t-il à la main ? | relancer la commande **dans le conteneur poller** : `podman exec shinken-poller <commande>` |
| Quand a-t-il tourné, quand tournera-t-il ? | Thruk : *Last Check Time*, *Next Scheduled Check* |
| Le poller exécute-t-il quelque chose ? | journal du poller ; latence dans *Performance Info* de Thruk |
| Un résultat passif est-il arrivé ? | journal de l'arbiter puis du scheduler (commande externe reçue) |

## Suite

- [Superviser à distance : SSH, NRPE, HTTPS, API](06-checks-a-distance.md) :
  qui se connecte où, avec quel compte et quelle clé.
- [Écrire son propre plugin](16-ecrire-un-plugin.md).
- [Performances](24-performances.md) : workers, latence, dimensionnement.
