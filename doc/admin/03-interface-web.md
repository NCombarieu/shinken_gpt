# Lire l'interface web

**Public :** administrateur de la supervision, niveau simple.

Shinken n'embarque pas d'interface web complète. Deux possibilités :

| Interface | Ce qu'elle offre | Accès par défaut |
|---|---|---|
| **Page d'état intégrée** (module `status-webui` du broker) | Tableau en lecture seule des hôtes et services, API JSON. Aucune action possible, aucune authentification. | `http://127.0.0.1:8081/` sur le serveur |
| **Thruk** (logiciel séparé, recommandé) | Interface complète : vues par problème, historique, acquittements, downtimes, forçage de checks, rapports. | à installer, se connecte à Livestatus (port 50000) |

## La page d'état intégrée

Elle est publiée sur l'hôte en `127.0.0.1:8081` (port 8080 dans le
conteneur broker) :

| URL | Contenu |
|---|---|
| `/` | tableau HTML des hôtes et services |
| `/api/status` | le même contenu en JSON, pour des scripts |
| `/healthz` | répond `ok` : sert au test de vie du conteneur |

Pour la consulter depuis votre poste, passez par un tunnel SSH
(`ssh -L 8081:127.0.0.1:8081 serveur-supervision`) ou par un reverse proxy
avec authentification (voir [exposition sécurisée](../exploitation/10-reverse-proxy-tls.md)).

## Brancher Thruk

[Thruk](https://www.thruk.org) est une interface web compatible Nagios qui
interroge Shinken par le protocole **Livestatus** (module `livestatus` du
broker, port TCP 50000). Il s'installe à côté de Shinken : paquets officiels
pour Debian, Ubuntu et RHEL (voir le site de Thruk), ou image conteneur.

### 1. Vérifier que Livestatus répond

```bash
printf 'GET status\nColumns: program_version\n\n' | nc 127.0.0.1 50000
```

ou, sans `nc` :

```bash
podman-compose exec broker shinken-healthcheck --quiet
```

### 2. Déclarer Shinken comme backend de Thruk

Dans `thruk_local.conf` (par exemple `/etc/thruk/thruk_local.conf`) :

```
<Component Thruk::Backend>
    <peer>
        name   = Shinken
        type   = livestatus
        <options>
            peer = 127.0.0.1:50000
        </options>
    </peer>
</Component>
```

Si Thruk tourne dans un conteneur relié au réseau Podman de Shinken,
utilisez `peer = broker:50000`. Le réseau doit être choisi **à la création**
du conteneur Thruk (`--network shinken_default` avec podman-compose,
`--network shinken` avec les quadlets) : en mode rootless, il ne peut
généralement pas être ajouté après coup.

### 3. Comptes et droits

Thruk gère ses propres comptes (fichier `htpasswd` de Thruk). Deux règles :

1. **Le login Thruk doit être identique à un `contact_name` Shinken.**
   Livestatus ne montre à un utilisateur que les hôtes et services dont il
   est contact (directement ou par un groupe). Un login sans contact
   correspondant voit une interface **vide**, sans message d'erreur.
2. Les droits d'administration de Thruk (envoyer des commandes, voir la
   configuration) se règlent dans le `cgi.cfg` de Thruk, par exemple
   `authorized_for_all_services=admin` et
   `authorized_for_all_service_commands=admin`.

Pour qu'un utilisateur ait accès sans recevoir de notification, créez un
contact sans notification (modèle : `etc/contacts/guest.cfg`).

## Lire une page de détail

Sur la page d'un service, Thruk affiche notamment :

| Champ | Signification |
|---|---|
| *Current Status* | OK, WARNING, CRITICAL, UNKNOWN (UP, DOWN, UNREACHABLE pour un hôte), et depuis combien de temps. |
| *Status Information* | la ligne de texte renvoyée par le plugin. |
| *Performance Data* | les mesures chiffrées (perfdata). |
| *Current Attempt* | par exemple `2/3 (SOFT state)` : problème pas encore confirmé (voir [concepts](02-concepts.md)). |
| *Last Check Time* / *Next Scheduled Check* | dernier check et prochain prévu. |
| *Is This Service Flapping?* | état de la détection du flapping. |
| *In Scheduled Downtime?* | maintenance en cours. |

Les vues les plus utiles au quotidien :

- *Problems → Service Problems / Host Problems* : seulement ce qui ne va
  pas, avec le filtre *Unhandled* pour masquer ce qui est déjà acquitté ou
  en maintenance ;
- *Tactical Overview* : synthèse chiffrée ;
- *Event Log* et *Notifications* : historique (fourni par le module
  `logstore-sqlite`, voir [Livestatus](26-livestatus.md)).

## Actions depuis Thruk

Depuis la page d'un hôte ou d'un service, le panneau *Commands* permet de :

- **forcer un check** (*Re-schedule the next check*), utile juste après un
  rechargement pour ne pas attendre l'étalement des premiers checks ;
- **acquitter** et **planifier un downtime** (voir
  [la page dédiée](04-acquitter-et-planifier-un-downtime.md)) ;
- désactiver temporairement les checks ou les notifications.

Le bouton *Restart the monitoring process* (page *Process Info*) recharge la
configuration : il exécute la commande `restart-shinken`
(`etc/commands/restart-shinken.cfg`), qui redémarre l'arbiter.

> **Note** — Thruk masque la ligne de commande exacte des checks aux
> utilisateurs sans rôle de configuration. Pour l'afficher à tous :
> `show_full_commandline = 2` dans `thruk_local.conf`.
