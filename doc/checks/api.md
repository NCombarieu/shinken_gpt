---
title: "Superviser une API ou un service HTTP"
domain: "Shinken"
type: "procedure"
level: "intermediaire"
duration: "15 min"
version: "1.0"
updated: "2026-10-31"
owner: "Administration Supervision"
status: "valid"
order: 15
keywords: [api, http, https, json, rest, health, certificat, check_curl, check_json_api, token]
summary: "Vérifier qu'une application répond correctement : code HTTP et contenu, expiration du certificat, valeur d'un champ JSON avec seuils, jeton d'API hors configuration."
---

# Superviser une API ou un service HTTP

## Objectif

Vérifier qu'une application **répond correctement**, en plus de superviser
la machine qui l'héberge :

- l'URL répond avec le bon code HTTP et le bon contenu ;
- le certificat HTTPS n'expire pas bientôt ;
- une valeur renvoyée par l'API en JSON (état, file d'attente, compteur)
  reste dans les seuils.

## Plugins disponibles dans l'image

| Plugin | Usage |
|---|---|
| `check_curl` (monitoring-plugins-standard) | code HTTP, expression régulière sur le contenu, temps de réponse, certificat, redirections, SNI |
| `check_http` | ancien équivalent, encore utilisé par `check_http_public` / `check_https_public` |
| `check_json_api` (fourni, `$SHINKENPLUGINSDIR$`) | lire un champ JSON et le comparer à une valeur ou à des seuils |

`check_json_api` est installé dans `/usr/local/lib/shinken/plugins`, hors du
volume de données : il est mis à jour avec l'image.

## Commandes fournies (`etc/commands/check_api.cfg`)

| Commande | Arguments | Vérifie |
|---|---|---|
| `check_https_status` | chemin, regex | HTTPS : code 2xx/3xx, contenu, certificat valide (chaîne et nom) |
| `check_http_status` | chemin, regex | même chose en HTTP |
| `check_https_cert` | jours warn, jours crit | expiration du certificat |
| `check_json_api` | URL, chemin JSON, warn, crit | valeur numérique dans les seuils |
| `check_json_api_expect` | URL, chemin JSON, valeur attendue | égalité exacte |
| `check_json_api_token` | URL, chemin, valeur, fichier jeton | idem avec un jeton « Bearer » |

`check_https_status` et `check_https_cert` utilisent l'`address` de l'hôte
comme nom de site (SNI, en-tête Host, nom du certificat) : mettez le **nom
DNS** du site, pas une adresse IP.

## Exemples

```ini
define host{
        use                     generic-host
        host_name               app-portail
        address                 portail.example.org
        check_command           check_tcp!443
        }

; La page /health répond et contient "UP"
define service{
        use                     generic-service
        host_name               app-portail
        service_description     Health
        check_command           check_https_status!/health!UP
        }

; Certificat : WARNING à 30 jours, CRITICAL à 14
define service{
        use                     generic-service
        host_name               app-portail
        service_description     Certificat
        check_command           check_https_cert!30!14
        check_interval          720
        }

; Spring Boot / actuator : {"status":"UP"}
define service{
        use                     generic-service
        host_name               app-portail
        service_description     Actuator
        check_command           check_json_api_expect!https://portail.example.org/actuator/health!status!UP
        }

; File d'attente : {"queue":{"pending":42}} -> WARNING > 100, CRITICAL > 500
define service{
        use                     generic-service
        host_name               app-portail
        service_description     Queue
        check_command           check_json_api!https://portail.example.org/api/metrics!queue.pending!100!500
        }
```

### Chemin JSON

| Réponse | Chemin |
|---|---|
| `{"status": "UP"}` | `status` |
| `{"queue": {"pending": 42}}` | `queue.pending` |
| `{"checks": [{"name": "db", "state": "ok"}]}` | `checks[0].state` |

### Seuils

Plages au format Nagios, comme tous les plugins :

| Seuil | Alerte quand la valeur est... |
|---|---|
| `100` | hors de 0 à 100 (donc > 100 ou < 0) |
| `10:` | inférieure à 10 |
| `~:50` | supérieure à 50 |
| `10:20` | hors de 10 à 20 |
| `@10:20` | entre 10 et 20 |

La valeur et le temps de réponse sont renvoyés en perfdata (graphes).

### API protégée par un jeton

Le jeton ne doit apparaître ni dans la configuration ni dans `ps` :

```sh
install -d etc/secrets
printf '%s' 'eyJhbGciOi...' > etc/secrets/portail.token
podman unshare chown 10001:10001 etc/secrets/portail.token
chmod 600 etc/secrets/portail.token
```

```ini
check_command   check_json_api_token!https://portail.example.org/api/status!status!ok!portail.token
```

`etc/secrets/` est ignoré par git. Le jeton n'est jamais renvoyé lors
d'une redirection (vers un autre site ou de https vers http). Pour un autre en-tête (`X-API-Key`...),
créez une commande avec `-H "X-API-Key: ..."`, en sachant que la valeur
devient alors visible dans la configuration.

!!! attention "Guillemets dans les expressions régulières"
    Les arguments sont placés entre guillemets doubles dans la commande :
    n'utilisez pas `"` dans une regex. Écrivez `status.{1,3}UP` plutôt que
    `"status": "UP"`, ou utilisez `check_json_api_expect`.

## Validation

```sh
podman exec shinken_poller_1 /usr/local/lib/shinken/plugins/check_json_api \
    -u https://portail.example.org/actuator/health -p status -e UP
# JSON API OK - status = UP | time=0.043s;;;0;10

podman exec shinken_poller_1 /usr/lib/nagios/plugins/check_curl \
    -H portail.example.org -S --sni -u /health -r UP
```

Options de `check_json_api` : `-h` (méthode, corps POST, statut HTTP
attendu, en-têtes, `-k` pour ignorer un certificat auto-signé, délai).

## Codes retour de `check_json_api`

| Situation | État |
|---|---|
| Valeur conforme | OK |
| Seuil warning/critical dépassé, valeur différente de l'attendue | WARNING / CRITICAL |
| HTTP hors 2xx (ou différent de `-s`), connexion impossible | CRITICAL |
| Réponse non JSON, chemin introuvable, valeur non numérique avec seuils | UNKNOWN |

## Dépannage {#depannage}

| Message | Cause | Action |
|---|---|---|
| `CRITICAL - ... certificate verify failed` | Certificat auto-signé ou CA interne | Ajouter la CA à l'image, ou `-k` dans une commande dédiée (en connaissance de cause) |
| `UNKNOWN - path 'x' not found` | Chemin JSON différent de la réponse réelle | `podman exec shinken_poller_1 /usr/local/lib/shinken/plugins/check_json_api -u <url>` (sans `-p`, affiche la réponse) |
| `HTTP CRITICAL - pattern not found` | La regex ne correspond pas au contenu | Tester la regex sur le contenu réel ; pas de `"` |
| `Name or service not known` | DNS du conteneur | Voir [Configurer Shinken, réseau depuis un container](../configuration.md#reseau-depuis-un-container) |

## Ce qui a été vérifié

`check_json_api` : seuils, valeur attendue, chemins imbriqués et tableaux,
404, réponse non JSON, connexion refusée, contre un vrai serveur HTTP, et
dans Shinken (`check_json_api`, `check_json_api_expect`). Dans la CI, le lab
Podman exécute `check_json_api_expect` depuis l'image. Le mode jeton a été
testé contre un serveur qui vérifie l'en-tête `Authorization` (jeton
valide, invalide, fichier absent). `check_curl` avec regex a été testé ;
`check_https_cert` n'a pas pu l'être contre un vrai service HTTPS.

## Voir aussi

- [Choisir un type de check](README.md)
