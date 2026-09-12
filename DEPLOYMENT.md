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
