# Écrire son propre plugin de check

**Public :** administrateur de la supervision, niveau avancé. Aucune
connaissance du code de Shinken n'est nécessaire : un plugin est un simple
programme (shell, Python, Perl…) qui respecte un contrat très court.

## Le contrat d'un plugin

Shinken utilise le même contrat que Nagios ; tout plugin Nagios existant
fonctionne tel quel.

### 1. Le code retour donne l'état

| Code | Service | Hôte |
|---|---|---|
| `0` | OK | UP |
| `1` | WARNING | UP |
| `2` | CRITICAL | DOWN |
| `3` | UNKNOWN | DOWN |

Utilisez `3` (UNKNOWN) quand la mesure est **impossible** (argument manquant,
dépendance absente, réponse illisible), et non `2` : un CRITICAL doit
toujours signifier « la chose surveillée est en panne ».

### 2. La première ligne de sortie est le message

Le plugin écrit sur la **sortie standard**. La première ligne est le
résumé affiché partout (Thruk, notifications) : courte et explicite.

```
DISK WARNING - /var : 12 % libres (seuil 15 %)
```

Les lignes suivantes forment la **sortie longue** (*long output*),
affichée dans le détail du service. La sortie d'erreur (stderr) est
ignorée : n'y mettez rien d'utile.

### 3. Les données de performance (perfdata)

Après un `|` sur la première ligne, des mesures chiffrées au format :

```
'libellé'=valeur[unité];[warn];[crit];[min];[max]
```

séparées par des espaces. Exemple complet :

```
DISK WARNING - /var : 12 % libres|'var_libre'=12%;15;10;0;100 'var_utilise'=8800MB;;;0;10000
```

| Élément | Règle |
|---|---|
| libellé | entre apostrophes s'il contient des espaces ; pas de `=` ni d'apostrophe |
| unité | aucune (nombre), `s`, `ms`, `us`, `%`, `B`, `KB`, `MB`, `GB`, `TB`, ou `c` (compteur) |
| warn, crit, min, max | facultatifs ; laisser vide mais garder les `;` si un champ suivant est rempli |

Ces données alimentent les graphiques (voir [métriques](27-metriques.md)).
Elles sont facultatives mais très utiles.

### 4. Les seuils

Convention des plugins standard pour `-w` et `-c` :

| Seuil écrit | Alerte si la valeur est… |
|---|---|
| `10` | < 0 ou > 10 |
| `10:` | < 10 |
| `~:10` | > 10 |
| `10:20` | < 10 ou > 20 |
| `@10:20` | entre 10 et 20 (inclus) |

### 5. Le temps d'exécution

Un check de service est tué au bout de `service_check_timeout` secondes (60
dans `etc/shinken.cfg`, 30 pour un check d'hôte) et passe CRITICAL avec la
sortie `(Service Check Timed Out)`. Prévoyez votre propre délai, plus court,
pour répondre proprement UNKNOWN :

- `timeout 10 commande` en shell ;
- `socket.setdefaulttimeout(10)` ou `timeout=` des bibliothèques en Python.

### Bonnes pratiques

- **Rapide** : quelques secondes au plus. Des centaines de checks tournent
  en parallèle.
- **Non interactif** : jamais de question, jamais de lecture au clavier.
- **Sans effet de bord** : un check mesure, il ne corrige pas (c'est le
  rôle des [event handlers](14-flapping-et-event-handlers.md)).
- **Sans privilège** : il s'exécute sous l'utilisateur `shinken` (UID 10001),
  sans `sudo`, dans le conteneur poller. Écriture possible seulement dans
  `/tmp` et `/var/lib/shinken`.
- **Texte UTF-8**, sortie limitée à `max_plugins_output_length` (64 Kio).
- **Arguments plutôt que valeurs en dur** : seuils, hôte et port en options,
  pour réutiliser le plugin.

## Exemple en shell

`plugins-local/check_fichier_recent.sh` : alerte si un fichier n'a pas été
modifié récemment (par exemple un export déposé chaque nuit).

```bash
#!/bin/sh
# check_fichier_recent.sh -f <fichier> -w <minutes> -c <minutes>
# OK si le fichier a été modifié il y a moins de <warn> minutes.

usage() { echo "UNKNOWN - usage : $0 -f fichier -w minutes -c minutes"; exit 3; }

while getopts "f:w:c:" opt; do
    case "$opt" in
        f) fichier=$OPTARG ;;
        w) warn=$OPTARG ;;
        c) crit=$OPTARG ;;
        *) usage ;;
    esac
done
[ -n "$fichier" ] && [ -n "$warn" ] && [ -n "$crit" ] || usage

if [ ! -e "$fichier" ]; then
    echo "CRITICAL - $fichier absent"
    exit 2
fi

maintenant=$(date +%s)
modif=$(stat -c %Y "$fichier") || { echo "UNKNOWN - lecture impossible de $fichier"; exit 3; }
age_s=$(( maintenant - modif ))
age=$(( age_s / 60 ))
# perfdata en secondes (unité standard), seuils convertis
perf="'age'=${age_s}s;$(( warn * 60 ));$(( crit * 60 ));0;"

if [ "$age" -ge "$crit" ]; then
    echo "CRITICAL - $fichier modifié il y a $age min|$perf"; exit 2
elif [ "$age" -ge "$warn" ]; then
    echo "WARNING - $fichier modifié il y a $age min|$perf"; exit 1
fi
echo "OK - $fichier modifié il y a $age min|$perf"
exit 0
```

## Exemple en Python

`plugins-local/check_api_sante.py` : interroge une URL JSON de santé
applicative. Bibliothèque standard uniquement (Python 3 est présent dans
l'image).

```python
#!/usr/bin/env python3
"""check_api_sante.py -u URL [-w SECONDES] [-c SECONDES] [-t TIMEOUT]

OK si l'URL répond {"status": "ok"} ; WARNING/CRITICAL sur le temps de réponse.
"""
import argparse
import json
import sys
import time
import urllib.request

OK, WARNING, CRITICAL, UNKNOWN = 0, 1, 2, 3


def sortir(code, message, perfdata=""):
    etat = ("OK", "WARNING", "CRITICAL", "UNKNOWN")[code]
    print("%s - %s%s" % (etat, message, "|" + perfdata if perfdata else ""))
    sys.exit(code)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-u", "--url", required=True)
    parser.add_argument("-w", "--warning", type=float, default=1.0)
    parser.add_argument("-c", "--critical", type=float, default=3.0)
    parser.add_argument("-t", "--timeout", type=float, default=10.0)
    try:
        args = parser.parse_args()
    except SystemExit:
        sortir(UNKNOWN, "arguments invalides")

    debut = time.monotonic()
    try:
        with urllib.request.urlopen(args.url, timeout=args.timeout) as reponse:
            donnees = json.load(reponse)
    except Exception as erreur:  # réseau, HTTP, JSON : l'application ne répond pas
        sortir(CRITICAL, "%s injoignable : %s" % (args.url, erreur))
    duree = time.monotonic() - debut
    perf = "'temps'=%.3fs;%s;%s;0;" % (duree, args.warning, args.critical)

    if donnees.get("status") != "ok":
        sortir(CRITICAL, "statut applicatif %r" % donnees.get("status"), perf)
    if duree >= args.critical:
        sortir(CRITICAL, "réponse en %.2f s" % duree, perf)
    if duree >= args.warning:
        sortir(WARNING, "réponse en %.2f s" % duree, perf)
    sortir(OK, "application saine, réponse en %.2f s" % duree, perf)


if __name__ == "__main__":
    main()
```

## Où déposer le plugin

Les plugins **exécutés par Shinken** (sur le serveur de supervision) vont
dans le dossier `plugins-local/` du dépôt. Il est monté en lecture seule dans
les conteneurs **poller** (checks) et **reactionner** (notifications, event
handlers), sur `/usr/local/lib/shinken/plugins-local`, désigné par la macro
`$LOCALPLUGINSDIR$`.

```bash
cp check_fichier_recent.sh plugins-local/
chmod 755 plugins-local/check_fichier_recent.sh
```

- Le fichier doit être **exécutable** et **lisible par tous** (`755`) : les
  conteneurs tournent sous l'UID 10001, qui n'est pas propriétaire du
  fichier.
- Pas de reconstruction d'image ni de redémarrage nécessaire pour un
  nouveau script : il est visible immédiatement dans les conteneurs.
- Seuls le README et l'exemple de `plugins-local/` sont versionnés dans ce
  dépôt : conservez vos scripts dans votre dépôt de configuration privé.

Les plugins **exécutés sur le serveur supervisé** (via NRPE ou SSH) se
déposent sur ce serveur, pas dans `plugins-local/` : voir les recettes
[Linux par SSH](recettes/linux-ssh.md) et [NRPE](recettes/linux-nrpe.md).

### Besoin d'un paquet supplémentaire

L'image contient Python 3 (bibliothèque standard), Perl avec `Net::SNMP`,
les monitoring-plugins, `snmpget`, `dig`, `ssh`. Si votre plugin a besoin
d'une bibliothèque absente (module Python, client de base de données…),
construisez une image dérivée plutôt que d'installer à la main dans un
conteneur (perdu à chaque recréation) :

```dockerfile
# Containerfile.local
FROM localhost/shinken:latest
USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3-requests \
    && rm -rf /var/lib/apt/lists/*
USER 10001:10001
```

Voir [mise à jour](../exploitation/06-mise-a-jour-retour-arriere.md) pour
taguer et utiliser cette image.

## Déclarer la commande et le service

```
# etc/commands/check_fichier_recent.cfg
define command {
    command_name    check_fichier_recent
    command_line    $LOCALPLUGINSDIR$/check_fichier_recent.sh -f $ARG1$ -w $ARG2$ -c $ARG3$
}
```

```
# etc/services/srv-supervision.cfg
define service {
    use                     generic-service
    host_name               localhost
    service_description     Export nocturne
    check_command           check_fichier_recent!/var/lib/shinken/exports/export.csv!1500!1800
}
```

Puis [vérifier et recharger](01-demarrage-rapide.md#5-vérifier-la-configuration).

## Tester à la main

Toujours tester **dans le conteneur poller**, sous le même utilisateur et
avec le même réseau que Shinken :

```bash
podman-compose exec poller sh -c \
  '/usr/local/lib/shinken/plugins-local/check_fichier_recent.sh -f /etc/hostname -w 5 -c 10; echo "code retour : $?"'
```

Vérifiez :

1. le **code retour** correspond à l'état attendu ;
2. la première ligne est lisible et le perfdata bien formé ;
3. le temps d'exécution reste court (`time` devant la commande) ;
4. les cas d'erreur (argument manquant, cible injoignable) donnent UNKNOWN
   ou CRITICAL avec un message clair.

Pour tester un plugin standard avec les mêmes arguments que Shinken, copiez
la ligne de commande résolue affichée dans Thruk (*Check Command*), ou
remplacez vous-même les macros (`$NAGIOSPLUGINSDIR$` =
`/usr/lib/nagios/plugins`).

## Dépannage

| Symptôme | Cause probable |
|---|---|
| `(No output returned from plugin)` ou UNKNOWN immédiat | fichier non exécutable, mauvais chemin, interpréteur absent (`#!` incorrect), fins de ligne Windows (`\r`) |
| `Permission denied` | droits `700`/`750` : passer en `755` |
| `(Service Check Timed Out)` | plugin trop lent : ajouter un délai interne, vérifier le réseau depuis le poller |
| fonctionne sur le serveur mais pas dans Shinken | le plugin tourne dans le conteneur poller : réseau, DNS et fichiers ne sont pas ceux de l'hôte |
| macro vide dans la commande | faute de frappe ou macro personnalisée non définie (voir [macros](11-macros.md)) |
