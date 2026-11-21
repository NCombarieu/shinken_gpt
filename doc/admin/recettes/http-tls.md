# Recette : site web HTTP/HTTPS et certificat TLS

**Principe :** le poller interroge le site comme le ferait un navigateur,
avec `check_http` (monitoring-plugins).

## 1. Déclarer le site

Le plus simple est un hôte par site, dont l'adresse est le **nom DNS** : il
sert à la fois à la connexion et comme nom virtuel (en-tête `Host` et SNI
TLS), indispensable sur un serveur qui héberge plusieurs sites.

```
define host {
    use                 generic-host
    host_name           www.example.com
    address             www.example.com
    check_command       check_tcp!443
    hostgroups          web
}
```

`check_tcp!443` remplace le ping, souvent filtré devant un site web.

## 2. Commandes fournies

`etc/commands/check_http.cfg` :

| Commande | Vérifie |
|---|---|
| `check_http!<URL>` | la page répond en HTTP (code 2xx ou 3xx) |
| `check_https!<URL>` | idem en HTTPS, avec SNI |
| `check_https_certificate!<jours warn>,<jours crit>` | délai avant expiration du certificat |

```
define service {
    use                     generic-service
    hostgroup_name          web
    service_description     HTTPS
    check_command           check_https!/
}

define service {
    use                     generic-service
    hostgroup_name          web
    service_description     Certificat TLS
    check_command           check_https_certificate!30,14
    check_interval          1440
    retry_interval          60
}
```

Avec `30,14`, le service passe WARNING 30 jours avant l'expiration et
CRITICAL à 14 jours : de quoi renouveler sans urgence. Un check par jour
suffit.

## 3. Aller plus loin

`check_http` offre de nombreuses options ; créez vos propres commandes :

| Besoin | Options |
|---|---|
| vérifier un contenu | `-s "texte attendu"` (CRITICAL si absent), `-r <regex>` |
| code HTTP précis | `-e "HTTP/1.1 200"` |
| temps de réponse | `-w 2 -c 5` (secondes) |
| suivre les redirections | `-f follow` |
| authentification HTTP | `-a utilisateur:motdepasse` (mettre le secret dans une macro de ressource) |
| autre port | `-p 8443` |

Exemple : page de santé applicative qui doit contenir `"status":"ok"` et
répondre en moins de 2 s :

```
define command {
    command_name    check_https_sante
    command_line    $NAGIOSPLUGINSDIR$/check_http -H $HOSTADDRESS$ -S --sni -u $ARG1$ -s '"status":"ok"' -w 2 -c 5 -t 10
}
```

Pour une logique plus riche (analyse JSON, plusieurs étapes), écrivez un
plugin : voir l'exemple Python de [écrire un plugin](../16-ecrire-un-plugin.md).

## 4. Tester

```bash
podman-compose exec poller /usr/lib/nagios/plugins/check_http \
    -H www.example.com -S --sni -C 30,14
```

> **Note** — Le site doit être résolu et joignable **depuis le conteneur
> poller**. Un nom présent seulement dans le `/etc/hosts` du serveur n'est
> pas connu des conteneurs (`podman-compose exec poller getent hosts
> www.example.com` pour vérifier).
