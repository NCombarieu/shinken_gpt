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
