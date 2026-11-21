# Recette : API HTTP/REST (JSON)

**Principe :** le poller appelle l'API comme le ferait un client, puis
vérifie **le contenu** de la réponse : un champ qui doit valoir une valeur
précise, ou un nombre qui ne doit pas franchir un seuil. Aucun agent sur la
cible.

Deux outils, selon le besoin :

| Besoin | Outil |
|---|---|
| L'API répond, avec le bon code HTTP, et la réponse contient un texte donné | `check_http` (monitoring-plugins), voir [HTTP/HTTPS](http-tls.md) |
| Lire **un champ précis** du JSON et le comparer à une valeur ou à des seuils | `check_api_json.py`, fourni avec Shinken (`$PLUGINSDIR$`) |

## 1. Cas simple : `check_http` suffit

Une page de santé qui renvoie `{"status":"ok"}` :

```
define command {
    command_name    check_api_sante
    command_line    $NAGIOSPLUGINSDIR$/check_http -H $HOSTADDRESS$ -S --sni -u $ARG1$ -e 200 -r '"status" *: *"ok"' -w 2 -c 5 -t 10
}
```

| Option | Rôle |
|---|---|
| `-e 200` | seul le code HTTP 200 est accepté |
| `-r '<regex>'` | la réponse doit contenir ce motif (tolère les espaces de mise en forme) |
| `-k 'Accept: application/json'` | ajoute un en-tête (répétable) |
| `-j POST -P '<données>' -T application/json` | appel en `POST` avec un corps JSON |
| `-a utilisateur:motdepasse` | authentification Basic (secret dans une macro de ressource) |
| `-w 2 -c 5` | WARNING au-delà de 2 s, CRITICAL au-delà de 5 s |

> **Note** — Dans l'image, `check_http` est la nouvelle implémentation
> fondée sur libcurl (`check_curl`). Les options sont les mêmes ; la
> liste complète : `podman exec shinken-poller /usr/lib/nagios/plugins/check_http --help`.

La limite de cette approche : une regex sur du JSON est fragile (ordre des
clés, imbrication, valeurs numériques). Dès qu'il faut lire un champ ou
comparer un nombre, passez à `check_api_json.py`.

## 2. Lire un champ : `check_api_json.py`

Le script n'utilise que la bibliothèque standard Python : il fonctionne
dans le conteneur poller sans rien installer. Il est livré dans
`libexec/` et installé dans l'image sous `$PLUGINSDIR$`
(`/usr/local/lib/shinken/libexec`).

### Désigner un champ

Le champ se désigne par un **chemin à points** ; un nombre désigne un
élément de liste :

```json
{
  "status": "ok",
  "queue": {"depth": 42},
  "nodes": [{"name": "a", "state": "up"}, {"name": "b", "state": "down"}],
  "quota": {"remaining": 5}
}
```

| Chemin | Valeur |
|---|---|
| `status` | `ok` |
| `queue.depth` | `42` |
| `nodes.1.state` | `down` |
| `quota.remaining` | `5` |

### Trois modes de comparaison

| Mode | Options | CRITICAL quand… |
|---|---|---|
| valeur attendue | `-e ok` | le champ ne vaut pas exactement `ok` |
| seuils maximums | `-w 50 -c 100` | la valeur atteint 100 (WARNING à 50) : latence, file d'attente, erreurs |
| seuils minimums | `--min -w 10 -c 2` | la valeur descend à 2 (WARNING à 10) : quota restant, nœuds actifs |
| aucun | — | jamais : le check affiche simplement la valeur (OK) |

### Ce que rend le script

| Situation | État | Exemple de sortie |
|---|---|---|
| tout va bien | OK | `API OK - status='ok' en 0.04s \| time=0.035s;;;0;10` |
| valeur différente | CRITICAL | `API CRITICAL - nodes.1.state='down', attendu 'up'` |
| seuil franchi | WARNING / CRITICAL | `API WARNING - queue.depth=42 (seuil 40) \| … 'queue.depth'=42;40;100` |
| code HTTP d'erreur (4xx, 5xx) | CRITICAL | `API CRITICAL - HTTP 503 Service Unavailable sur https://…` |
| réponse qui n'est pas du JSON | CRITICAL | `API CRITICAL - HTTP 200, réponse non JSON` |
| injoignable, délai dépassé, TLS invalide | CRITICAL | `API CRITICAL - injoignable : timed out` |
| champ absent | UNKNOWN | `API UNKNOWN - champ 'queue.size' absent de la réponse` |
| valeur non numérique avec des seuils | UNKNOWN | `API UNKNOWN - status='ok' n'est pas un nombre` |

Le temps de réponse est toujours fourni en perfdata (`time`), ainsi que la
valeur comparée quand des seuils sont donnés : de quoi tracer des courbes
(voir [métriques](../27-metriques.md)).

### Commandes fournies

`etc/commands/check_api_json.cfg` :

| Commande | Arguments |
|---|---|
| `check_api_json_value` | `!<URL>!<champ>!<valeur attendue>` |
| `check_api_json_threshold` | `!<URL>!<champ>!<warning>!<critical>` |
| `check_api_json_minimum` | `!<URL>!<champ>!<warning>!<critical>` |
| `check_api_json_token` | `!<URL>!<champ>!<valeur attendue>!<fichier du jeton>` |

L'URL est complète (schéma, nom, port, chemin) : une API est souvent servie
ailleurs qu'à l'adresse de l'hôte qui la porte.

### Exemples de services

```
define host {
    use                 generic-host
    host_name           api-commandes
    address             api.example.com
    check_command       check_tcp!443
}

define service {
    use                     generic-service
    host_name               api-commandes
    service_description     API santé
    check_command           check_api_json_value!https://api.example.com/health!status!ok
}

define service {
    use                     generic-service
    host_name               api-commandes
    service_description     API file d'attente
    check_command           check_api_json_threshold!https://api.example.com/metrics!queue.depth!500!2000
}

define service {
    use                     generic-service
    host_name               api-commandes
    service_description     API quota restant
    check_command           check_api_json_minimum!https://api.example.com/v1/quota!remaining!1000!100
}
```

> **Attention** — Le caractère `!` sépare les arguments dans
> `check_command` : une URL qui en contient doit passer par une commande
> dédiée. Les caractères `?` et `&` sont acceptés : la commande est alors
> exécutée via un shell, et les guillemets simples de la définition
> protègent l'URL.

## 3. API authentifiée

### Jeton (Bearer)

Ne mettez **jamais** un jeton dans `check_command` ni dans une macro : il
apparaîtrait dans Thruk (*Expanded Command*), dans les journaux et dans la
liste des processus du conteneur. Mettez-le dans un **fichier**, que le
script lit lui-même :

```bash
# sur le serveur de supervision, depuis la racine de la configuration
printf '%s' 'le-jeton' > etc/certs/api-commandes.token
podman unshare chown 10001:10001 etc/certs/api-commandes.token
podman unshare chmod 400 etc/certs/api-commandes.token
```

`etc/certs/` est monté dans les conteneurs sous `/etc/shinken/certs/` et
n'est pas versionné. `podman unshare` est nécessaire en mode rootless : voir
[les comptes et les clés](../06-checks-a-distance.md#qui-est-qui--les-comptes-en-jeu).

```
define service {
    use                     generic-service
    host_name               api-commandes
    service_description     API santé (authentifiée)
    check_command           check_api_json_token!https://api.example.com/v1/health!status!ok!/etc/shinken/certs/api-commandes.token
}
```

Créez côté API un jeton **dédié à la supervision**, en lecture seule, sur
les seuls points d'accès de santé.

### Autres schémas

| Schéma | Comment |
|---|---|
| en-tête maison (`X-API-Key`) | `check_api_json.py -H 'X-API-Key: …'` : la valeur reste visible dans la ligne de commande ; préférez une variante du script qui lit l'en-tête dans un fichier |
| Basic | `check_http -a utilisateur:motdepasse`, le mot de passe dans une macro de ressource (`etc/resource.d/`) : invisible dans Thruk, mais visible dans la liste des processus |
| certificat client (mTLS) | `check_http -J cert.pem -K cle.pem` avec les fichiers dans `etc/certs/` |
| OAuth2 (jeton à obtenir d'abord) | écrire un plugin qui obtient le jeton puis appelle l'API (voir [écrire un plugin](../16-ecrire-un-plugin.md)) |

## 4. Certificat TLS de l'API

`check_api_json.py` vérifie le certificat avec les autorités du conteneur
(paquet `ca-certificates`). Pour une API interne signée par une autorité
privée, ajoutez l'autorité à l'image dérivée (voir
[besoin d'un paquet supplémentaire](../16-ecrire-un-plugin.md#besoin-dun-paquet-supplémentaire))
plutôt que d'utiliser `--insecure`, qui désactive toute vérification.

Pour surveiller l'expiration du certificat, ajoutez un service
`check_https_certificate` (voir [HTTP/HTTPS](http-tls.md)).

## 5. Tester depuis le poller

```bash
podman exec shinken-poller /usr/local/lib/shinken/libexec/check_api_json.py \
    -u https://api.example.com/health -k status -e ok
echo "code retour : $?"
```

Pour voir le JSON brut et trouver le bon chemin :

```bash
podman exec shinken-poller python3 -c \
  'import json,urllib.request; print(json.dumps(json.load(urllib.request.urlopen("https://api.example.com/health")), indent=2))'
```

(avec podman-compose : `podman-compose exec poller …`.)

## Dépannage

| Message | Cause |
|---|---|
| `injoignable : [Errno -2] Name or service not known` | le nom ne se résout pas **depuis le conteneur** (voir [DNS des conteneurs](../../exploitation/02-configuration.md#résolution-dns-depuis-les-conteneurs)) |
| `injoignable : [SSL: CERTIFICATE_VERIFY_FAILED]` | autorité inconnue du conteneur, ou nom ne correspondant pas au certificat |
| `HTTP 401` / `HTTP 403` | jeton absent, expiré, ou sans droit sur ce point d'accès |
| `jeton illisible : Permission denied` | droits du fichier : refaire `podman unshare chown 10001:10001` |
| `champ '…' absent de la réponse` | chemin faux : afficher le JSON brut (ci-dessus) ; attention aux listes (`items.0.state`) |
| `(Service Check Timed Out)` | l'API met plus de 60 s : réduire `-t` pour obtenir un message plus parlant |
