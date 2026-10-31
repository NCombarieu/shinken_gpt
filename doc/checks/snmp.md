---
title: "Superviser par SNMP"
domain: "Shinken"
type: "procedure"
level: "intermediaire"
duration: "20 min"
version: "1.0"
updated: "2026-10-31"
owner: "Administration Supervision"
status: "valid"
order: 14
keywords: [snmp, snmpv3, check_snmp, manubulon, switch, net-snmp, oid, communauté]
summary: "Superviser switchs, routeurs, onduleurs, NAS et serveurs par SNMP v2c ou v3 : commandes fournies, modèle snmp-host, secrets SNMPv3 hors git."
---

# Superviser par SNMP

## Objectif

Interroger l'agent SNMP d'un équipement (UDP 161) : la seule méthode pour
la plupart des équipements réseau, et une option sans installation pour les
serveurs Linux (`snmpd`).

## Plugins disponibles dans l'image

| Plugin | Paquet | Usage |
|---|---|---|
| `check_snmp` | monitoring-plugins-standard | lire un OID, avec seuils ou attente d'une valeur |
| `check_snmp_storage.pl` | nagios-snmp-plugins | disques et partitions (HOST-RESOURCES-MIB) |
| `check_snmp_load.pl` | nagios-snmp-plugins | charge (Linux) ou % CPU (Windows, équipements) |
| `check_snmp_mem.pl` | nagios-snmp-plugins | mémoire et swap (net-snmp) |
| `check_snmp_int.pl` | nagios-snmp-plugins | état et débit des interfaces |
| `snmpget`, `snmpwalk` | snmp | exploration manuelle |

Les modules Perl de chiffrement SNMPv3 (DES, AES, HMAC) sont installés.
L'image ne contient **pas de MIB non libres** : utilisez des **OID
numériques** (`.1.3.6.1.2.1.1.3.0`), pas des noms (`sysUpTime.0`).

## Étapes

### 1. Côté équipement

Activer SNMP en lecture seule, restreint à l'adresse du serveur Podman.
Exemple `snmpd` sous Linux (`/etc/snmp/snmpd.conf`) :

```
agentaddress udp:161
# v2c : communauté en lecture seule, limitée au serveur Shinken
rocommunity  maCommunauteSecrete  192.0.2.10
# v3 (recommandé) : chiffré et authentifié
createUser   shinken SHA "motdepasse-auth" AES "motdepasse-priv"
rouser       shinken authPriv
```

```sh
systemctl restart snmpd
```

!!! attention "SNMP v2c n'est pas chiffré"
    La communauté v2c circule en clair et sert de mot de passe. Changez
    toujours `public`, limitez par adresse source, et préférez **v3
    `authPriv`** (SHA + AES) dès que l'équipement le permet.

### 2. Côté Shinken : l'hôte

```ini
define host{
        use                     snmp-host
        host_name               sw-core01
        address                 10.0.0.2
        ; check_command check_snmp_alive (défaut du modèle, v2c)
        ;               check_snmp_alive_v3 pour un équipement uniquement v3
        _SNMP_COMMUNITY         maCommunauteSecrete     ; v2c
        ; _SNMP_V3_USER         shinken                 ; v3 (défaut du modèle)
        ; _SNMP_PORT            161
        }
```

### 3. SNMPv3 : les mots de passe hors de git

```sh
cp etc/resource.d/snmpv3.local.cfg.example etc/resource.d/snmpv3.local.cfg
vi etc/resource.d/snmpv3.local.cfg       # $SNMPV3AUTHPASS$ / $SNMPV3PRIVPASS$
```

`*.local.cfg` est ignoré par git. Les commandes `*_v3` utilisent
`authPriv`, SHA et AES avec ces deux macros, et l'utilisateur `_SNMP_V3_USER`
de l'hôte. Dans ce fichier, écrivez `$$` pour un `$` et évitez `'` (la
valeur est placée entre apostrophes). Comme tout argument de plugin, les
mots de passe sont visibles dans `ps` sur le poller.

### 4. Les services

```ini
define host{
        use                     snmp-host
        host_name               srv-lin01
        address                 srv-lin01.example.lan
        _SNMP_COMMUNITY         maCommunauteSecrete
        }

define service{
        use                     generic-service
        host_name               srv-lin01
        service_description     Disk root
        check_command           check_snmp_storage!^/$!85!95
        }
define service{
        use                     generic-service
        host_name               srv-lin01
        service_description     Load
        check_command           check_snmp_load!3,3,2!5,5,4
        }
define service{
        use                     generic-service
        host_name               sw-core01
        service_description     Uplink
        check_command           check_snmp_int!^GigabitEthernet1/0/48$
        }
```

## Commandes fournies

| Commande | Arguments | Exemple |
|---|---|---|
| `check_snmp_alive` / `_v3` | (aucun) | test d'hôte sur sysUpTime |
| `check_snmp_get` | OID | `check_snmp_get!.1.3.6.1.2.1.1.5.0` (nom de l'équipement) |
| `check_snmp_oid` / `_v3` | OID, warn, crit | `check_snmp_oid!.1.3.6.1.4.1.2021.10.1.5.1!300!500` |
| `check_snmp_storage` / `_v3` | regex du volume, warn %, crit % | `check_snmp_storage!^/$!85!95`, `check_snmp_storage!^C:!85!95` |
| `check_snmp_load` / `_v3` | warn 1,5,15 min, crit | `check_snmp_load!3,3,2!5,5,4` (Linux) |
| `check_snmp_cpu` | warn %, crit % | `check_snmp_cpu!80!95` (Windows, équipements) |
| `check_snmp_mem` | warn ram,swap %, crit | `check_snmp_mem!90,30!95,50` (net-snmp) |
| `check_snmp_int` | regex de l'interface | `check_snmp_int!^eth0$` (état UP/DOWN) |

La dérive d'horloge ne passe pas par SNMP : `check_ntp_time!0.5!1`
interroge le service NTP de la cible (UDP 123), qui doit donc servir l'heure
(chrony ne le fait pas par défaut).

Pour le débit d'une interface, ajoutez une commande dédiée avec `-k` (voir
`check_snmp_int.pl -h`), par exemple
`-k -w 80,80 -c 95,95` (% de la bande passante en entrée et en sortie).

!!! information "Commandes retirées"
    `check_snmp_service` et `check_snmp_time` appelaient des plugins
    (`check_snmp_service`, `check_snmp_time.pl`) qui ne sont dans aucun
    paquet : elles ne pouvaient pas fonctionner. Elles sont remplacées par
    `check_snmp_cpu` et `check_ntp_time`. Pour les services Windows,
    utilisez NSClient++ ([NRPE](nrpe.md)) : le service SNMP de Windows est
    obsolète.

## OID utiles

| OID | Signification |
|---|---|
| `.1.3.6.1.2.1.1.3.0` | sysUpTime (durée de fonctionnement) |
| `.1.3.6.1.2.1.1.5.0` | sysName |
| `.1.3.6.1.4.1.2021.10.1.5.1` | charge 1 min × 100 (net-snmp) |
| `.1.3.6.1.2.1.25.1.1.0` | hrSystemUptime |
| `.1.3.6.1.2.1.33.1.2.4.0` | onduleur : charge restante de la batterie en % (UPS-MIB) |

Explorer un équipement depuis le poller :

```sh
podman exec shinken_poller_1 snmpwalk -v2c -c maCommunauteSecrete -On 10.0.0.2 .1.3.6.1.2.1.2.2.1.2
```

## Validation

```sh
podman exec shinken_poller_1 /usr/lib/nagios/plugins/check_snmp \
    -H 10.0.0.2 -P 2c -C maCommunauteSecrete -o .1.3.6.1.2.1.1.3.0
# SNMP OK - Timeticks: (49409) 0:08:14.09

podman exec shinken_poller_1 /usr/lib/nagios/plugins/check_snmp_storage.pl \
    -H srv-lin01 -l shinken -x 'motdepasse-auth' -X 'motdepasse-priv' -L sha,aes -m '^/$' -w 85 -c 95 -f
```

## Dépannage {#depannage}

| Message | Cause | Action |
|---|---|---|
| `Timeout` / `No Response from ...` | Mauvaise communauté v2c (l'agent ne répond pas du tout), ACL, pare-feu UDP 161 | Tester avec `snmpget` depuis le poller ; vérifier l'adresse source autorisée |
| `Authentication failure (incorrect password, community or key)` | Mot de passe v3, ou protocole SHA/MD5 différent | Vérifier `snmpv3.local.cfg` et le protocole configuré sur l'équipement |
| `SNMPv3 support is unavailable (Required module ...)` | Module Perl manquant (image ancienne) | Reconstruire l'image (`podman-compose build`) |
| `No usable data on file` / storage introuvable | Regex ne correspondant à aucun volume | `check_snmp_storage.pl ... -m . -v` pour lister les noms |
| `Cannot find module (...)` | Utilisation d'un nom de MIB | Utiliser l'OID numérique |

## Ce qui a été vérifié

Testé contre un vrai `snmpd`. Dans Shinken (macros d'hôte `_SNMP_*` et
fichier `snmpv3.local.cfg` compris) : `check_snmp_alive`,
`check_snmp_storage`, `check_snmp_load` et, en v3 authPriv SHA/AES,
`check_snmp_load_v3`. En ligne de commande, avec les mêmes paramètres :
`check_snmp_get`, `check_snmp_cpu`, `check_snmp_mem`, `check_snmp_int` et
`check_snmp_storage_v3`. Non testé sur un vrai switch ni sur le service
SNMP de Windows.

## Voir aussi

- [Choisir un type de check](README.md)
