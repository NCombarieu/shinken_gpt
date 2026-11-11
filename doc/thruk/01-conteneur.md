# Thruk : le conteneur

**Public :** exploitant système.

## Quelle image

Thruk n'est pas fourni par ce dépôt. L'image conseillée est **OMD Labs
Edition** de ConSol (projet
[omd-labs-docker](https://github.com/ConSol-Monitoring/omd-labs-docker)),
qui embarque Thruk, Apache et les outils OMD prêts à l'emploi :

| Image | Base |
|---|---|
| `docker.io/consol/omd-labs-debian` | Debian |
| `docker.io/consol/omd-labs-rocky` | Rocky Linux |

Utilisez une **version figée** (étiquette datée ou empreinte `@sha256:`),
jamais `latest` en production : une mise à jour de Thruk se fait alors
volontairement, avec retour arrière possible.

> **Note** — OMD est une distribution complète de supervision : elle
> contient aussi un moteur (Naemon). Ici, seul Thruk sert ; le moteur local
> est désactivé (`CORE none`, voir plus bas) et Thruk interroge Shinken.

## Ce qu'il y a dans le conteneur

OMD organise tout en **sites** : un site est un utilisateur Unix et une
arborescence `/omd/sites/<site>`. L'image crée par défaut le site `demo`
(variable de construction `SITENAME`).

| Chemin dans le conteneur | Contenu |
|---|---|
| `/omd/sites/demo/etc/thruk/thruk_local.conf` | réglages locaux de Thruk |
| `/omd/sites/demo/etc/thruk/thruk_local.d/*.conf` | fragments chargés en plus : on y place la déclaration du backend Shinken |
| `/omd/sites/demo/etc/thruk/cgi.cfg` | rôles et droits (`authorized_for_*`) |
| `/omd/sites/demo/etc/htpasswd` | comptes et mots de passe de Thruk |
| `/omd/sites/demo/etc/apache/conf.d/` | configuration Apache du site (vhosts supplémentaires) |
| `/omd/sites/demo/var/thruk/` | données de Thruk : sessions, favoris, rapports |
| `/root/ansible_dropin/playbook.yml` | playbook exécuté à chaque démarrage (voir plus bas) |

Deux serveurs Apache cohabitent :

| Apache | Écoute | Rôle |
|---|---|---|
| système | 80, **443** (TLS, certificat auto-signé) | point d'entrée, relaie vers le site |
| du site OMD | `127.0.0.1:5000` | sert Thruk |

On publie donc le **443** du conteneur, sur `127.0.0.1` de l'hôte
uniquement ; le reverse proxy s'y connecte.

## Démarrage : ce que fait l'image

Le point d'entrée `/root/start.sh` :

1. si le volume du site est **vide**, crée le site (`omd create`) et tire un
   mot de passe administrateur au hasard ;
2. exécute `/root/ansible_dropin/playbook.yml` **s'il existe** ;
3. démarre `cron`, le site (`omd start demo`) puis l'Apache système ;
4. reste au premier plan (`sleep infinity`).

Le playbook drop-in est **le bon endroit pour tout réglage qui doit
survivre** à une recréation du conteneur : il est rejoué à chaque
démarrage. Écrivez-le **idempotent** (rejouable sans effet de bord).

Exemple de playbook drop-in :

```yaml
- hosts: all
  tasks:
    # Pas de moteur local : Thruk ne sert qu'à afficher Shinken
    - shell: su - {{ SITENAME }} -c 'omd config set CORE none'

    # Mot de passe de l'administrateur OMD (lu dans un secret, jamais en clair ici)
    - shell: su - {{ SITENAME }} -c "set_admin_password \"$(cat /run/secrets/thruk_admin)\""

    # Administrateurs Thruk nominatifs
    - lineinfile:
        path: /omd/sites/{{ SITENAME }}/etc/thruk/cgi.cfg
        regexp: '^authorized_for_admin='
        line: 'authorized_for_admin=omdadmin,alice'

    # Un PID orphelin empêche Apache de redémarrer après un arrêt brutal
    - file:
        path: /omd/sites/{{ SITENAME }}/tmp/run/apache.pid
        state: absent
```

> **Attention** — Ne mettez pas de mot de passe en clair dans le playbook :
> il est lisible par quiconque lit le dépôt de déploiement. Montez-le comme
> secret Podman (`--secret thruk_admin`) et lisez-le dans la tâche.

## Lancer le conteneur

### Avec podman (ou podman-compose)

```bash
podman volume create omd-thruk-site

podman run -d --name omd-thruk \
  --network shinken \
  -p 127.0.0.1:8443:443 \
  -v omd-thruk-site:/omd/sites/demo \
  -v ./thruk/shinken.conf:/omd/sites/demo/etc/thruk/thruk_local.d/shinken.conf:ro,Z \
  -v ./thruk/playbook.yml:/root/ansible_dropin/playbook.yml:ro,Z \
  docker.io/consol/omd-labs-debian:<version>
```

| Option | Pourquoi |
|---|---|
| `--network shinken` | réseau des conteneurs Shinken : `shinken` avec les quadlets fournis, `shinken_default` avec podman-compose (voir [connexion](02-connexion-livestatus.md)) |
| `-p 127.0.0.1:8443:443` | jamais sur `0.0.0.0` : seul le reverse proxy doit joindre Thruk |
| `-v omd-thruk-site:/omd/sites/demo` | **volume nommé** pour tout le site : comptes, sessions, rapports survivent à une recréation |
| `shinken.conf` en lecture seule | déclaration du backend, gérée dans votre dépôt de déploiement |
| `playbook.yml` | réglages rejoués à chaque démarrage |

### En quadlet (démarrage au boot)

`~/.config/containers/systemd/omd-thruk.container`, à côté des quadlets
Shinken (voir [démarrage au boot](../exploitation/04-demarrage-au-boot.md)) :

```ini
[Unit]
Description=Thruk (interface web de Shinken)
After=shinken-broker.service
Wants=shinken-broker.service

[Container]
ContainerName=omd-thruk
Image=docker.io/consol/omd-labs-debian:<version>
Network=shinken.network
PublishPort=127.0.0.1:8443:443
Volume=omd-thruk-site:/omd/sites/demo
Volume=%h/shinken/thruk/shinken.conf:/omd/sites/demo/etc/thruk/thruk_local.d/shinken.conf:ro,Z
Volume=%h/shinken/thruk/playbook.yml:/root/ansible_dropin/playbook.yml:ro,Z

[Service]
Restart=always
TimeoutStartSec=300

[Install]
WantedBy=default.target
```

`TimeoutStartSec=300` : le premier démarrage (création du site) prend
plus d'une minute.

### Droits et capacités

L'image démarre en root **dans** le conteneur (elle bascule ensuite vers
l'utilisateur du site). En Podman rootless, ce root n'a aucun privilège
sur l'hôte. N'ajoutez pas de capacité supplémentaire : Thruk n'en a pas
besoin. (`NET_RAW` n'est utile que si vous gardez un moteur local qui fait
des pings.)

## Ressources

L'image est volumineuse (environ 3,5 Go) mais l'exécution est légère :
quelques centaines de Mo de mémoire pour Apache et Thruk, sans moteur
local. Prévoyez la place disque pour l'image et ses versions précédentes.

## Mettre à jour Thruk

1. Tirer la nouvelle version figée de l'image.
2. Changer l'étiquette dans le quadlet (ou le `podman run`), recharger
   systemd, redémarrer le conteneur.
3. Le volume du site est conservé ; OMD met à jour le site au démarrage si
   nécessaire. Vérifiez la connexion (page *Backends* de Thruk) et la
   connexion d'un compte non administrateur.
4. Retour arrière : remettre l'ancienne étiquette. **Sauvegardez le volume
   du site avant** une mise à jour majeure d'OMD :

```bash
podman volume export omd-thruk-site -o omd-thruk-site-$(date +%F).tar
```

## Hors ligne (serveur sans accès au registre)

Sur une machine connectée :

```bash
podman pull docker.io/consol/omd-labs-debian:<version>
podman save -o omd-thruk-<version>.tar docker.io/consol/omd-labs-debian:<version>
```

puis `podman load -i omd-thruk-<version>.tar` sur le serveur. Un outil de
déploiement (Puppet, Ansible) peut faire de même : voir
[déploiement géré par Puppet](../exploitation/13-deploiement-puppet.md).

## Suite

[2. Connecter Thruk à Shinken](02-connexion-livestatus.md)
