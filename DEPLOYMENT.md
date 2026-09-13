# Déploiement de Shinken sur ce serveur

Procédure suivie pour faire tourner ce fork (branche `modernize/podman-python3`)
sur ce serveur et l'exposer sur `https://shinken.ncombarieu.fr`.

## 1. Récupération du code

```sh
git clone https://github.com/NCombarieu/shinken_gpt.git
cd shinken_gpt
git checkout modernize/podman-python3
```

C'est la branche la plus à jour (build Podman + portage Python 3 complet),
contrairement à `master` qui n'a qu'un correctif de regex.

## 2. Outillage

Podman était déjà installé, mais pas d'outil compose. Installation de
`podman-compose` via pip (pas de paquet dnf disponible) :

```sh
sudo dnf install -y python3-pip
sudo pip install podman-compose
```

## 3. Conflit de port

Le fichier `compose.yaml` du repo expose le broker (webui) sur
`127.0.0.1:8080`. Ce port était déjà pris par le dashboard du lab réseau
(`/opt/lab-reseau/dashboard/server.py`, process indépendant tournant hors
systemd). Remappé sur `8081` :

```diff
   broker:
     ports:
-      - "127.0.0.1:8080:8080"
+      - "127.0.0.1:8081:8080"
```

## 4. Build et lancement

```sh
podman-compose build
podman-compose up -d
```

La stack lance 6 daemons Shinken (arbiter, scheduler, poller, reactionner,
broker, receiver), chacun dans son propre container, avec 3 volumes
partagés (`./etc` en lecture seule, plus deux volumes nommés pour les
données et logs persistants). Le broker embarque le module web "status"
moderne (lecture seule, `/` + `/api/status` + `/healthz`) et est le seul à
publier un port sur l'hôte.

Vérification :

```sh
podman ps -a --filter name=shinken
curl http://127.0.0.1:8081/healthz   # -> ok
```

## 5. Exposition HTTPS via Caddy

Ce serveur gère déjà plusieurs sous-domaines de `ncombarieu.fr` via Caddy,
un fichier par site dans `/etc/caddy/sites/` (voir
`/opt/lab-reseau/deploy/expose.sh` pour le script qui gère ce pattern pour
le lab). Le DNS de `shinken.ncombarieu.fr` pointait déjà vers l'IP publique
du serveur.

Le webui Shinken n'a pas d'authentification propre : on protège donc
l'accès avec `basic_auth` côté Caddy, comme pour `lab.ncombarieu.fr`.

Génération du mot de passe et de son hash bcrypt :

```sh
PASS=$(openssl rand -base64 18 | tr -d '=+/' | cut -c1-20)
caddy hash-password --plaintext "$PASS"
```

Fichier `/etc/caddy/sites/shinken.ncombarieu.fr.caddy` :

```caddy
shinken.ncombarieu.fr {
	basic_auth {
		noel <hash bcrypt>
	}
	reverse_proxy 127.0.0.1:8081
}
```

Puis :

```sh
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload-or-restart caddy
```

Caddy obtient et renouvelle seul le certificat Let's Encrypt.

## Résultat

- `https://shinken.ncombarieu.fr` → basic_auth (`noel` / mot de passe généré)
  → reverse proxy → broker Shinken sur `127.0.0.1:8081`
- Config Shinken par défaut (un seul host `localhost`) : aucune vraie
  supervision configurée pour l'instant, c'est la prochaine étape si besoin.

## Opérations courantes

```sh
podman-compose ps                 # état des daemons
podman-compose logs -f broker     # logs d'un daemon
podman-compose down               # tout arrêter (garde les volumes)
podman-compose up -d              # relancer
```

Pour changer le mot de passe : régénérer un hash avec
`caddy hash-password`, l'éditer dans le fichier `.caddy` ci-dessus, puis
`sudo systemctl reload caddy`.

## Mise à jour (2026-09-13) : bug bloquant + bascule vers Naemon/Thruk

En configurant quelques services de test sur le host `localhost`, découverte
d'un bug dans ce fork : le poller ne relance plus jamais ses tentatives de
connexion au scheduler après les 2-3 premiers essais au démarrage (boucle
`do_mainloop` dans `shinken/satellite.py`, processus vivant mais inactif,
aucune erreur loguée même en `DEBUG`). Résultat : aucun check ne s'exécute
jamais, host et services restent bloqués en `PENDING` indéfiniment. Cohérent
avec l'état du fork : les commits du jour sur cette branche portent
justement sur la stabilisation du transport distribué Python 3
(`fix: complete Python 3 distributed transport`, etc.) — pas encore
résolu au moment de ce déploiement.

Suite à une demande de brancher Thruk (interface web) sur ce Shinken :
Thruk ne parle que le protocole MK Livestatus, que ce fork n'implémente pas
(seuls deux scripts utilitaires dans `contrib/livestatus/`, pas de module
broker). Plutôt que de porter ce module ou attendre le fix du poller,
**`shinken.ncombarieu.fr` sert maintenant Naemon + Thruk + Livestatus**
(image `consol/omd-labs-debian`, site OMD "demo"), qui fonctionne
réellement (checks exécutés, résultats corrects, confirmé via
`unixcat tmp/run/live`).

La stack Shinken de ce repo n'est pas supprimée : conteneurs et volumes sont
conservés, juste arrêtés (`podman-compose stop` dans `~/shinken_gpt`), au
cas où le bug se règle plus tard côté fork.

### Stack Naemon/Thruk (hors de ce repo, infra serveur)

```sh
podman volume create omd-thruk-site
podman run -d --name omd-thruk \
  -p 127.0.0.1:8443:443 -p 127.0.0.1:8082:80 \
  -v omd-thruk-site:/omd/sites/demo \
  -v ~/omd-thruk/ansible_dropin:/root/ansible_dropin:Z \
  --cap-add=NET_RAW \
  --restart unless-stopped \
  docker.io/consol/omd-labs-debian:latest
```

- `--cap-add=NET_RAW` : nécessaire pour `check_icmp`/`check-host-alive`
  (contrairement au compose Shinken, pas de `cap_drop: ALL` ici).
- Le drop-in Ansible (`~/omd-thruk/ansible_dropin/playbook.yml`) fixe le mot
  de passe `omdadmin` au démarrage (sinon mot de passe aléatoire, cf. doc de
  l'image).
- Config Naemon custom dans le volume nommé :
  `etc/naemon/conf.d/localhost.cfg` (host `localhost` + 4 services : Load,
  Disk /, Users, HTTP Thruk) et `etc/naemon/conf.d/contacts.cfg`
  (contactgroup `admins` = noel + guillaume). Reload : `su - demo -c "omd
  reload naemon"` dans le conteneur.
- Comptes ajoutés dans `etc/htpasswd` du site (`htpasswd -b etc/htpasswd
  <user> <pass>`) : `omdadmin`, `noel`, `guillaume`.
- Forcer un check immédiat (au lieu d'attendre l'étalement initial, jusqu'à
  10 min) : écrire dans `tmp/run/naemon.cmd`, ex. `[<epoch>]
  SCHEDULE_FORCED_SVC_CHECK;localhost;Load;<epoch>`.

### Caddy

`shinken.ncombarieu.fr` fait maintenant : `basic_auth` (noel/guillaume,
même mot de passe que leur compte Thruk) → redirection `/` vers
`/demo/thruk/` → `reverse_proxy https://127.0.0.1:8443` avec
`tls_insecure_skip_verify` (Apache du site OMD force HTTPS avec un
certificat auto-signé, uniquement en loopback). La `basic_auth` Caddy est
redondante avec celle de Thruk (double authentification pour l'instant) —
à simplifier plus tard si la double confirmation gêne.

L'ancien reverse_proxy vers `127.0.0.1:8081` (broker Shinken) n'est plus
utilisé, mais le port reste dispo si la stack Shinken est relancée.

## Mise à jour (2026-09-13, suite) : page inaccessible, double auth + port 8443 qui fuit

Deux bugs corrigés après la bascule vers Naemon/Thruk :

1. **Retiré le `basic_auth` Caddy redondant.** Le double niveau
   d'authentification (Caddy + Thruk) provoquait des re-demandes de mot de
   passe en boucle côté navigateur (les requêtes AJAX de Thruk ne
   renvoyaient pas systématiquement l'auth Caddy). Thruk a sa propre
   authentification par utilisateur (`etc/htpasswd` du site OMD), donc une
   seule couche suffit — même pattern que `portail.ncombarieu.fr`.

2. **Le vrai bug bloquant** : la page de login de Thruk (`login.cgi`)
   redirigeait vers `https://shinken.ncombarieu.fr:8443/...` — le port
   *interne au conteneur* (mappé uniquement sur `127.0.0.1:8443` côté
   hôte), jamais ouvert publiquement. Un vrai navigateur ne pouvait donc
   jamais charger la page de login. Cause : l'Apache "système" de l'OMD
   (`etc/apache/proxy-port.conf`) construit ses URLs de redirection à
   partir du header `X-Forwarded-Port` s'il est déjà présent dans la
   requête, sinon de son propre `SERVER_PORT`. Fix : forcer explicitement
   les bons headers côté Caddy plutôt que de laisser Apache deviner :

   ```caddy
   reverse_proxy https://127.0.0.1:8443 {
       header_up X-Forwarded-Port "443"
       header_up X-Forwarded-Proto "https"
       transport http {
           tls_insecure_skip_verify
       }
   }
   ```

Config finale de `/etc/caddy/sites/shinken.ncombarieu.fr.caddy` : plus de
`basic_auth`, juste le `redir /` + `reverse_proxy` ci-dessus.

## Mise à jour (2026-09-13, suite 2) : URL "/demo/thruk/" visible

Retiré le `redir / /demo/thruk/ 302` (redirection HTTP visible, changeait
la barre d'adresse) au profit d'un `rewrite / /demo/thruk/` (réécriture
interne, transparente pour le navigateur) dans
`/etc/caddy/sites/shinken.ncombarieu.fr.caddy`. Le premier chargement de
`https://shinken.ncombarieu.fr/` reste donc sur cette URL.

Tenté de renommer le site OMD "demo" en "shinken" (`omd mv demo shinken`)
pour faire disparaître complètement `/demo/` des URLs internes de Thruk :
échoue avec `OSError: Device or resource busy`, parce que le volume
persistant est monté directement à la racine du site
(`/opt/omd/sites/demo`), et `omd mv` fait un `os.rename()` qui ne peut pas
déplacer un point de montage. Un vrai renommage demanderait de sortir les
données du volume, refaire le rename hors mount, recréer un volume nommé
`shinken`, ET rejouer l'enregistrement système du site (utilisateur Linux,
alias Apache global) qui ne vit pas dans le volume persistant — trop
risqué à chaud pour un gain purement cosmétique. Laissé tel quel : une
fois dans Thruk, les liens internes de l'appli pointent toujours vers
`/demo/thruk/...` (c'est `url_prefix` dans `etc/thruk/thruk.conf`, pas un
redirect Caddy). À refaire proprement plus tard si besoin, en construisant
une image avec `SITENAME=shinken` au build (mécanisme documenté par
l'image `consol/omd-labs-debian`) plutôt qu'en renommant un site existant.

## Mise à jour (2026-09-13, correction majeure) : retour à Shinken + vrai Livestatus

**Le diagnostic "le poller est bloqué à jamais" (mise à jour du 2026-09-13
plus haut) était faux.** Le vrai bug : `BaseModule._main()`
(`shinken/basemodule.py`) appelait `shinken.http_daemon.daemon_inst.shutdown()`
dans le processus forké d'un module externe, ce qui bloque indéfiniment en
attendant des threads qui n'existent que dans le process parent — exactement
la même classe de bug déjà corrigée pour `Worker` dans `shinken/worker.py`
(commit du jour sur cette branche), juste jamais appliquée à
`BaseModule`. Un simple test resté sans interruption pendant plus de
4 minutes a confirmé que les checks Shinken s'exécutent bel et bien tout
seuls (le service Load a changé de valeur après ~240s, correspondant au
`check_interval` configuré) — mon impatience à redémarrer les containers
la veille avait empêché ce délai de s'écouler.

Ce fix de fork, plus le vrai module Livestatus de Shinken
(`shinken-monitoring/mod-livestatus`, jamais inclus dans ce repo mais
distribué séparément comme tous les modules shinken.io — voir
`modules/livestatus/`), portés ensemble en Python 3, permettent à
**`shinken.ncombarieu.fr` de servir maintenant le vrai Shinken via Thruk**,
plus Naemon. La stack Naemon/OMD (container `omd-thruk`) reste utilisée
uniquement comme distribution Thruk/Apache — sa configuration
(`etc/thruk/thruk.conf`) pointe son backend Livestatus vers
`broker:50000` (le vrai Shinken), pas vers son propre Naemon local.

### Bugs corrigés pour faire fonctionner Livestatus + les commandes externes

- `shinken/basemodule.py` : fix fork/HTTP-shutdown ci-dessus (déblocage de
  **tous** les modules externes, pas que Livestatus).
- `shinken/util.py` : `safe_print()` et `get_customs_values()` avaient des
  restes Python 2 (`str.decode()`, `dict.values()` non sérialisable JSON).
- `shinken/objects/satellitelink.py` : `get_external_commands()` faisait
  `cpickle.loads(str(tab))` sur des bytes Python 3 → exception avalée
  silencieusement par un `except:` nu → les commandes externes (force
  check, ack, downtime) envoyées par Thruk/Livestatus n'arrivaient jamais
  au scheduler. Le format réel de `tab` est du pickle brut (pas de
  base64/zlib comme pour `get_broks`).
- `shinken/daemons/brokerdaemon.py` : le Broker n'avait **jamais** de
  méthode `get_external_commands()` (Poller/Reactionner l'ont
  gratuitement via `Satellite`/`BaseSatellite`, le Broker a sa propre
  hiérarchie de classes qui ne l'hérite pas). Ajoutée, même pattern que
  `shinken/satellite.py`.
- `modules/livestatus/` : nombreux restes Python 2 corrigés (`raise "x", y`,
  `.__func__` sur méthodes non liées, bytes/str aux limites socket,
  hack `__bases__` runtime remplacé par un vrai héritage direct de
  `queue.LifoQueue`).
- `etc/contacts/webteam.cfg` : ajout de contacts réels `noel`/`guillaume`
  (groupe `admins`) — sans ça, le filtrage `AuthUser` de Livestatus cache
  tout aux comptes qui ne sont pas des contacts Shinken exacts.

### Vérifié de bout en bout sur le vrai Shinken

`GET hosts`/`GET services` (bruts et via Thruk), `SCHEDULE_FORCED_SVC_CHECK`,
`SCHEDULE_SVC_DOWNTIME`, `ACKNOWLEDGE_SVC_PROBLEM` — tous confirmés
fonctionnels (résultats de checks frais, downtime visible dans
`scheduled_downtime_depth`, commandes loguées par l'arbiter).

### Configuration Livestatus

- `etc/modules/livestatus.cfg` : module `livestatus`, port TCP 50000,
  sous-module `logstore-null` (pas de logs historiques nécessaires).
- `etc/brokers/broker-master.cfg` : `modules livestatus,status-webui`.
- `compose.yaml` : port `127.0.0.1:50000:50000` publié sur le broker.
- Le container `omd-thruk` a été rattaché au réseau podman du compose
  Shinken (`podman network connect` ne marche pas avec le mode réseau
  "pasta" par défaut de podman rootless — il a fallu recréer le
  container avec `--network shinken_default` dès le `podman run`).

## Mise à jour (2026-09-13, suite 3) : hostname et check command absents dans Thruk

Deux bugs distincts, tous deux corrigés :

1. **Hostname absent** : `Host.display_name` restait toujours `''` dans
   Shinken (contrairement à `Service`, qui a un vrai fallback vers
   `service_description` dans `service.py`). Ajouté le même fallback vers
   `host_name` dans `Host.fill_predictive_missing_parameters()`
   (`shinken/objects/host.py`).

2. **"Check Command" absent des pages de détail Thruk** : masqué par
   `show_full_commandline = 1` dans `etc/thruk/thruk.conf`, qui ne montre
   la commande qu'aux utilisateurs ayant le rôle Thruk
   `authorized_for_configuration_information` — un rôle géré côté Thruk
   (cgi.cfg/contactgroups), pas quelque chose que Livestatus expose (pas
   de colonne `is_admin` pour les contacts dans ce module, c'est une
   extension Nagios/Shinken hors du schéma MK Livestatus standard).
   Plutôt que de construire tout un mapping de rôles pour 2 utilisateurs,
   passé `show_full_commandline = 2` (visible pour tout le monde) —
   `share/thruk/lib/Thruk/Authentication/User.pm`'s
   `check_show_command_line_permissions()` retourne vrai immédiatement
   dans ce cas, sans vérifier de rôle.

`etc/contacts/webteam.cfg` a aussi reçu `is_admin 1` sur noel et
guillaume (sans effet direct sur ce point précis vu l'absence de colonne
Livestatus, mais cohérent avec le contact "admin" préexistant et utile
si d'autres fonctionnalités Thruk s'appuient dessus plus tard).

## Mise à jour (2026-09-13, suite 4) : procédure d'exploitation — appliquer une conf modifiée

**Fichiers `.cfg` sous `etc/`** (host, service, template, contact...) : pas
de rebuild nécessaire, `./etc` est monté en bind-mount (`compose.yaml`).
Éditer le fichier puis relancer l'arbiter suffit — il relit sa config au
démarrage et la redistribue lui-même à tous les autres daemons :

```sh
podman restart shinken_arbiter_1
```

**Code Python** (`shinken/*.py`, `modules/*.py`) : là il faut rebuild
l'image (copiée dedans au build) :

```sh
podman-compose build
podman-compose up -d --force-recreate
```

### Reload/Restart depuis Thruk (côté exploitant, sans toucher au serveur)

Les commandes `reload-shinken`/`restart-shinken` (`etc/commands/`)
pointaient vers `/etc/init.d/shinken reload|restart` — un script qui
n'existe pas dans ce déploiement conteneurisé (chaque daemon est son
propre container, pas de service SysV unique). Le bouton "Reload"/
"Restart" de Thruk (page Process Info, commandes `RELOAD_CONFIG`/
`RESTART_PROGRAM`) échouait donc silencieusement.

Corrigé : ces deux commandes font maintenant `pkill -TERM -f
shinken-arbiter`. Shinken n'a pas de reload à chaud façon SIGHUP (aucun
handler dans `shinken/daemon.py`), donc "reload" et "restart" reviennent
de toute façon à la même chose ici : tuer le process arbiter fait sortir
tini (PID 1 du container), et `restart: unless-stopped` dans
`compose.yaml` relance le container tout seul, qui relit `etc/` et
redistribue la config aux autres daemons. Testé via `RELOAD_CONFIG` en
Livestatus brut : le container arbiter redémarre bien (~14s après la
commande).

Donc pour l'admin supervision au quotidien : ajouter un template
d'hôte, sauvegarder, puis cliquer "Reload" dans Thruk (Process Info) —
ou `podman restart shinken_arbiter_1` en ligne de commande, équivalent.

## Mise à jour (2026-09-13, suite 5) : bouton "Restart" de Thruk sans effet

Le bouton "Restart the Monitoring process" de Thruk (Process Info,
`cmd_typ=13`) envoie littéralement la commande `RESTART_PROCESS`
(`share/thruk/templates/cmd/cmd_typ_13.tt`), pas `RESTART_PROGRAM`.
Shinken (`shinken/external_command.py`) ne reconnaissait que
`RESTART_PROGRAM`/`RELOAD_CONFIG` -> le clic ne faisait rigoureusement
rien (aucune erreur visible, la commande est juste absente du
dictionnaire de commandes reconnues). Ajouté `RESTART_PROCESS` comme
alias direct de `RESTART_PROGRAM`. Testé via Livestatus brut : le
container arbiter redémarre bien après la commande.

Rappel important lié : le fichier `.cfg` doit avoir été modifié **avant**
le dernier redémarrage de l'arbiter pour être pris en compte -- éditer
un fichier puis interroger Thruk sans avoir relancé/rechargé
l'arbiter (bouton Reload/Restart, ou `podman restart shinken_arbiter_1`)
ne change rien, logique mais facile à oublier.
