---
title: "Superviser par NRPE (Linux et Windows NSClient++)"
domain: "Shinken"
type: "procedure"
level: "intermediaire"
duration: "30 min"
version: "1.0"
updated: "2026-10-31"
owner: "Administration Supervision"
status: "valid"
order: 13
keywords: [nrpe, nsclient, windows, check_nrpe, tls, certificats, powershell, alias]
summary: "Interroger un agent NRPE : nagios-nrpe-server sous Linux, NSClient++ sous Windows (alias de checks intégrés ou scripts PowerShell), avec TLS mutuel."
---

# Superviser par NRPE (Linux et Windows NSClient++)

## Objectif

Le poller interroge un **agent** installé sur la machine (port 5666) :
`nagios-nrpe-server` sous Linux, **NSClient++** sous Windows. Shinken envoie
un **nom** de commande ; l'agent exécute la commande correspondante, avec
des seuils définis chez lui.

```
poller --TLS 5666--> NSClient++ / nrpe
  check_nrpe -c alias_cpu        -> check_cpu "warn=load gt 80" "crit=load gt 90"
  "OK: CPU load is ok." <--------
```

## Deux façons de définir les checks

| | Alias / commandes sur l'agent (recommandé) | Arguments envoyés par Shinken |
|---|---|---|
| Où sont les seuils | dans `nsclient.ini` / `nrpe.cfg` | dans la configuration Shinken |
| Réglage agent | `allow arguments = false` | `allow arguments = true` (ou `dont_blame_nrpe=1`) |
| Risque | aucun : le client ne choisit qu'un nom | le client choisit les paramètres : risque d'injection si l'agent est mal réglé |
| Commande Shinken | `check_nrpe!alias_cpu` | `check_nrpe_3args!check_drivesize!drive=C:!warn=used gt 85%!crit=used gt 95%` |

Préférez les alias. Les arguments ne se justifient que pour beaucoup de
variantes d'un même check sur beaucoup de machines.

## Sécurité du transport : TLS mutuel

`check_nrpe` chiffre toujours la connexion. Avec des **certificats**, en
plus :

- Shinken vérifie qu'il parle au bon agent (certificat signé par votre CA) ;
- l'agent n'accepte que Shinken (certificat client exigé).

Commande Shinken : `check_nrpe_ssl` (fichiers dans `etc/certs/`).
Commande sans certificats : `check_nrpe`. Elle n'authentifie pas
l'agent ; avec un agent récent la connexion reste chiffrée, mais un ancien
agent en mode « insecure » (chiffrement anonyme ADH) est refusé par
OpenSSL 3 : passez-le en certificats.

!!! attention "Certificats d'exemple du dépôt"
    `etc/certs/` contient historiquement des certificats et clés
    d'**exemple** de Shinken (`server.key`, `private/cakey.pem`...), publics
    puisque le dépôt l'est. Ne les utilisez jamais : générez votre propre CA
    (ci-dessous).

### Générer la CA et les certificats (une fois)

Sur le serveur Podman, dans `etc/certs/` (fichiers ignorés par git) :

```sh
cd etc/certs
openssl req -x509 -newkey rsa:3072 -nodes -days 3650 -subj "/CN=Supervision CA" \
    -keyout ca.key -out ca.crt
# certificat client de Shinken (nom historique attendu par check_nrpe_ssl)
openssl req -newkey rsa:3072 -nodes -subj "/CN=shinken" -keyout shinken-server.key -out shinken-server.csr
openssl x509 -req -days 825 -in shinken-server.csr -CA ca.crt -CAkey ca.key -CAcreateserial -out shinken-server.crt
# certificat d'un agent (un par machine, ou un commun)
openssl req -newkey rsa:3072 -nodes -subj "/CN=srv-win01" -keyout nrpe-server.key -out nrpe-server.csr
openssl x509 -req -days 825 -in nrpe-server.csr -CA ca.crt -CAkey ca.key -CAcreateserial -out nrpe-server.crt
# la clé de Shinken doit être lisible par le poller (uid 10001)
podman unshare chown 10001:10001 shinken-server.key
```

Gardez `ca.key` hors du serveur une fois les certificats signés. Copiez
`ca.crt`, `nrpe-server.crt` et `nrpe-server.key` sur l'agent.

## Windows : NSClient++

### 1. Installer

Installer NSClient++ (MSI depuis nsclient.org). Pendant l'installation, ne
cochez que le serveur NRPE ; la configuration se fait ensuite dans
`C:\Program Files\NSClient++\nsclient.ini`.

### 2. Configurer

Partir de `contrib/checks/nsclient/nsclient.ini`, qui contient :

- `allowed hosts` : l'adresse du serveur Podman **vue depuis Windows** ;
- le serveur NRPE en TLS mutuel (`insecure = false`,
  `verify mode = peer-cert`), `allow arguments = false`,
  `allow nasty characters = false` ;
- des **alias** prêts à l'emploi : `alias_cpu`, `alias_mem`, `alias_disk`,
  `alias_disk_c`, `alias_services` (services automatiques arrêtés),
  `alias_spooler`, `alias_uptime`, `alias_evt_sys` (erreurs du journal
  Système sur la dernière heure) ;
- un **script PowerShell** déclaré dans `wrapped scripts`.

Copier `ca.crt`, `nrpe-server.crt`, `nrpe-server.key` dans
`C:\Program Files\NSClient++\security\` (`${certificate-path}`), puis :

```powershell
net stop nscp; net start nscp
New-NetFirewallRule -DisplayName "NRPE Shinken" -Direction Inbound -Protocol TCP -LocalPort 5666 -RemoteAddress 192.0.2.10 -Action Allow
```

### 3. Les alias

Syntaxe des filtres NSClient++ : `warn=used gt 85%`, `crit=load gt 90`.
Écrivez `gt`, `lt`, `ge`, `le` et jamais `>`/`<` : ce sont des « nasty
characters » que l'agent refuse, et que Shinken passerait de toute façon au
shell comme des redirections.

Ajouter un alias :

```ini
[/settings/external scripts/alias]
alias_sql = check_service "service=MSSQLSERVER"
alias_d   = check_drivesize "drive=D:" "warn=free lt 20G" "crit=free lt 10G"
alias_pdh = check_pdh "counter=\\Processor(_total)\\% Processor Time" "warn=value gt 80" "crit=value gt 95"
```

### 4. Les scripts PowerShell maison

Modèle : `contrib/checks/nsclient/check_example.ps1` (âge de la dernière
sauvegarde). Le contrat est celui de tout plugin Nagios : **une ligne**
`ETAT - texte | perfdata` et un code de sortie 0/1/2/3.

1. Copier le script dans `C:\Program Files\NSClient++\scripts\`.
2. Le déclarer avec ses arguments **fixes** :
   ```ini
   [/settings/external scripts/wrapped scripts]
   check_backup = check_example.ps1 -MaxAgeHours 26
   ```
3. Shinken l'appelle par son nom : `check_nrpe_ssl!check_backup`.

Le fichier fourni définit le « wrapping » `ps1` avec
`-ExecutionPolicy Bypass` : le script s'exécute quelle que soit la politique
d'exécution PowerShell de la machine.

!!! attention "Commentaires dans nsclient.ini"
    NSClient++ ne gère pas les commentaires en fin de ligne
    (`CheckSystem = enabled ; ...` désactive le module). Mettez chaque
    commentaire sur sa propre ligne.

### 5. Côté Shinken

```ini
define host{
        use                     nrpe-ssl-host
        host_name               srv-win01
        address                 srv-win01.example.lan
        }
define service{
        use                     generic-service
        host_name               srv-win01
        service_description     CPU
        check_command           check_nrpe_ssl!alias_cpu
        }
define service{
        use                     generic-service
        host_name               srv-win01
        service_description     Disk C
        check_command           check_nrpe_ssl!alias_disk_c
        }
define service{
        use                     generic-service
        host_name               srv-win01
        service_description     Backup
        check_command           check_nrpe_ssl!check_backup
        }
```

`nrpe-ssl-host` vérifie l'hôte avec `check_nrpe_ssl_alive` (l'agent répond
par sa version, en présentant le certificat client). Pour un agent sans
vérification de certificat, utilisez `nrpe-host` et `check_nrpe`.

!!! information "Non testé avec NSClient++"
    Les commandes Shinken et la configuration TLS mutuelle ont été testées
    contre un vrai `nrpe` 4.1 sous Linux. La configuration NSClient++
    (`nsclient.ini`, alias, script PowerShell) suit la documentation de
    NSClient++ mais n'a pas pu être exécutée sur un Windows.

## Linux : nagios-nrpe-server

```sh
apt install nagios-nrpe-server monitoring-plugins-basic
install -d -m 750 -o root -g nagios /etc/nagios/ssl
cp ca.crt nrpe-server.crt nrpe-server.key /etc/nagios/ssl/
chgrp nagios /etc/nagios/ssl/nrpe-server.key && chmod 640 /etc/nagios/ssl/nrpe-server.key
cp shinken.cfg /etc/nagios/nrpe.d/shinken.cfg      # contrib/checks/nrpe/shinken.cfg
systemctl restart nagios-nrpe-server
```

`contrib/checks/nrpe/shinken.cfg` définit `allowed_hosts`, TLS avec
certificat client obligatoire (`ssl_client_certs=2`) et sans chiffrement
anonyme (`ssl_use_adh=0`), pas d'arguments
(`dont_blame_nrpe=0`) et les commandes `check_load`, `check_disk`,
`check_root`, `check_swap`, `check_procs`, `check_zombies`, `check_sshd`.

Côté Shinken : hôte `use nrpe-ssl-host`, services `check_nrpe_ssl!check_load`.

## Validation

```sh
podman exec shinken_poller_1 /usr/lib/nagios/plugins/check_nrpe -H srv-win01.example.lan -t 15 \
    -A /etc/shinken/certs/ca.crt -C /etc/shinken/certs/shinken-server.crt -K /etc/shinken/certs/shinken-server.key
# I (0.5.x) seem to be doing fine...     <- version de l'agent

podman exec shinken_poller_1 /usr/lib/nagios/plugins/check_nrpe -H srv-win01.example.lan -t 30 \
    -A /etc/shinken/certs/ca.crt -C /etc/shinken/certs/shinken-server.crt -K /etc/shinken/certs/shinken-server.key \
    -c alias_cpu
```

## Commandes fournies (`etc/commands/check_nrpe*.cfg`)

| Commande | Usage |
|---|---|
| `check_nrpe!<nom>` | TLS sans certificat |
| `check_nrpe_ssl!<nom>` | TLS mutuel (`etc/certs/`) |
| `check_nrpe_alive` / `check_nrpe_ssl_alive` | test d'hôte : l'agent répond (sans / avec certificat client) |
| `check_nrpe_1arg` / `_2args` / `_3args` | arguments envoyés (exige `allow arguments` sur l'agent), chacun entre guillemets |
| `check_nrpe_args` | ancienne définition à 4 arguments, inchangée (arguments sans guillemets) |

## Dépannage {#depannage}

| Message | Cause | Action |
|---|---|---|
| `CHECK_NRPE: Receive header underflow` / `Error - Could not connect` | Adresse refusée (`allowed hosts`), certificat client exigé mais absent, ou pare-feu | Vérifier `allowed hosts` (adresse de l'hôte Podman vue par l'agent) ; utiliser `check_nrpe_ssl` |
| `CHECK_NRPE: Error - Could not complete SSL handshake` | Certificats non signés par la même CA, ou ancien agent en mode `insecure` (chiffrement ADH refusé par OpenSSL 3) | Passer l'agent en certificats (ci-dessus) ; mettre l'agent à jour |
| `Cannot read key file` / `Error: could not use private key` | Clé `shinken-server.key` illisible par le poller | `podman unshare chown 10001:10001 etc/certs/shinken-server.key` |
| `NRPE: Command 'x' not defined` | Alias ou commande absent de l'agent | L'ajouter dans `nsclient.ini` / `nrpe.cfg`, redémarrer l'agent |
| `Arguments not allowed` / `Request contained illegal metachars` | Commande avec arguments vers un agent qui les refuse, ou `>`/`<` dans un argument | Utiliser un alias ; écrire `gt`/`lt` |
| `UNKNOWN: Script "x.ps1" not found` | Script absent de `scripts\` | Copier le script, vérifier le nom dans `wrapped scripts` |
| Sortie tronquée | Sortie supérieure à 1024 octets (NRPE v2) | Raccourcir la sortie du script |

## Voir aussi

- [Choisir un type de check](README.md)
- [SNMP](snmp.md), pour les équipements sans agent
