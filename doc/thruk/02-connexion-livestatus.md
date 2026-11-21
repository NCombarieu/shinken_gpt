# Thruk : connecter Thruk à Shinken

**Public :** exploitant système.

Thruk ne parle pas aux daemons Shinken : il interroge le **module
Livestatus du broker**, sur le port TCP **50000**. Connecter Thruk, c'est
donc (1) lui permettre de joindre ce port, (2) le déclarer comme backend.

## 1. Le chemin réseau

### Cas recommandé : même réseau Podman

Le conteneur Thruk est attaché au réseau privé des conteneurs Shinken et
joint le broker **par son nom** :

| Déploiement de Shinken | Réseau | Nom du broker sur ce réseau |
|---|---|---|
| quadlets fournis (`deploy/quadlet/`) | `shinken` | `shinken-broker` (et l'alias `broker` si vous l'ajoutez) |
| `podman-compose` (`compose.yaml`, projet `shinken`) | `shinken_default` | `broker` |
| conteneurs gérés par un outil (Puppet…) | celui que l'outil crée | nom ou alias déclaré |

Pour connaître le réseau et les noms réels :

```bash
podman network ls
podman inspect shinken-broker --format '{{range $n, $v := .NetworkSettings.Networks}}{{$n}} {{$v.Aliases}}{{"\n"}}{{end}}'
```

> **Attention** — En Podman rootless, le réseau d'un conteneur se choisit
> **à sa création** (`--network`, ou `Network=` du quadlet). Avec le mode
> réseau par défaut (pasta), `podman network connect` sur un conteneur
> existant échoue ou n'a pas d'effet : il faut **recréer** le conteneur
> Thruk. Son volume nommé conserve comptes et réglages.

Avantages : le port 50000 n'a pas besoin d'être publié sur l'hôte, et
Livestatus (qui n'a pas d'authentification) reste invisible hors du
réseau des conteneurs.

### Autre cas : Thruk installé sur l'hôte (paquet)

Thruk installé par paquet sur le serveur lui-même joint Livestatus par le
port publié sur l'hôte : `127.0.0.1:50000` (`SHINKEN_LIVESTATUS_PORT`
dans `.env`, publié par `compose.yaml`). Vérifiez que ce port est bien
publié dans votre déploiement : un déploiement qui ne publie que la page
d'état (8081) ne permet **pas** cette variante.

### Thruk sur une autre machine

À éviter : Livestatus n'a ni chiffrement ni authentification. Si c'est
indispensable, faites passer le flux par un tunnel SSH ou un tunnel TLS
authentifié (stunnel, `socat` avec certificats) et restreignez la source
avec `allowed_hosts` dans `etc/modules/livestatus.cfg`.

## 2. Déclarer le backend

Un fichier dans `thruk_local.d/`, monté en lecture seule (voir
[le conteneur](01-conteneur.md)) :

```
<Component Thruk::Backend>
  <peer>
    name   = shinken
    type   = livestatus
    <options>
      peer = broker:50000
    </options>
  </peer>
</Component>
```

| Champ | Rôle |
|---|---|
| `name` | nom affiché dans Thruk (sélecteur de backends, colonne *Site*) |
| `type = livestatus` | protocole Livestatus, en TCP ici |
| `peer` | `<nom ou adresse>:<port>` vu **depuis le conteneur Thruk** |

Si OMD a laissé un backend local vers son propre moteur (fichier
`thruk_local.conf` d'origine), retirez-le ou désactivez le moteur
(`omd config set CORE none`) : sinon Thruk affiche un second backend en
erreur.

Redémarrez Thruk pour prendre en compte le fichier :

```bash
podman exec omd-thruk su - demo -c 'omd reload apache'
```

(ou redémarrez le conteneur.)

## 3. Tester, du plus bas au plus haut

**a. Livestatus répond, vu du broker :**

```bash
podman exec shinken-broker shinken-healthcheck --quiet && echo OK
```

**b. Le port est joignable, vu de Thruk :**

```bash
podman exec omd-thruk getent hosts broker
podman exec omd-thruk timeout 5 bash -c \
  'exec 3<>/dev/tcp/broker/50000; printf "GET status\nColumns: program_version\n\n" >&3; head -1 <&3'
```

La seconde commande doit afficher la version du programme (par exemple
`2.4.3`). Le Livestatus de Shinken garde la connexion ouverte après sa
réponse : d'où `head -1` et `timeout`, sans quoi la commande ne rend pas la
main. `Name or
service not known` : pas sur le même réseau ou mauvais nom.
`Connection refused` : le module Livestatus n'est pas chargé ou écoute
ailleurs (journal du broker).

**c. Thruk voit le backend :** dans Thruk, menu *Config Tool* ou icône des
backends en haut de page : le backend `shinken` doit être vert. En ligne
de commande :

```bash
podman exec omd-thruk su - demo -c 'thruk -l'
```

**d. Un compte voit des objets :** se connecter avec un compte qui est
contact Shinken (voir [comptes et droits](03-comptes-et-droits.md)). Un
compte qui n'est pas contact voit une interface **vide**, sans erreur.

## Ce qui transite par Livestatus

| Thruk fait… | Requête Livestatus |
|---|---|
| afficher les hôtes, services, problèmes | `GET hosts`, `GET services` avec `AuthUser: <login>` |
| afficher l'historique, les rapports de disponibilité | `GET log` (module `logstore-sqlite`, voir [Livestatus](../admin/26-livestatus.md#historique--logstore-sqlite)) |
| forcer un check, acquitter, poser un downtime | `COMMAND [horodatage] …` (commande externe) |
| *Restart the monitoring process* | `COMMAND … RESTART_PROGRAM` → l'arbiter exécute `restart-shinken` |

Les commandes partent du broker vers l'arbiter puis le scheduler : voir
[comment un check est exécuté](../admin/05-execution-des-checks.md#le-check-passif).
Il faut une à quelques secondes avant que leur effet soit visible.

## Plusieurs Shinken, un seul Thruk

Thruk sait agréger plusieurs backends : déclarez un `<peer>` par instance
Shinken (un par broker, chacun avec son `name`). Le sélecteur de backends
permet ensuite de filtrer. Pour beaucoup de backends ou de gros volumes,
OMD fournit **LMD** (cache Livestatus) : voir le fichier
`thruk_local.d/lmd.conf` de l'image et la documentation d'OMD.

## Suite

[3. Comptes et droits](03-comptes-et-droits.md)
