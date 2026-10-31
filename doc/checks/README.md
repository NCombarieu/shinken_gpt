---
title: "Choisir un type de check"
domain: "Shinken"
type: "guide"
level: "intermediaire"
duration: "10 min"
version: "1.0"
updated: "2026-10-31"
owner: "Administration Supervision"
status: "valid"
order: 10
keywords: [checks, ssh, passif, nrpe, nsclient, snmp, api, json, agent]
summary: "Comparer les façons de superviser une machine ou un service (SSH actif/passif, NRPE, SNMP, API) et trouver la fiche correspondante."
---

# Choisir un type de check

## Objectif

Savoir quelle méthode utiliser pour superviser une machine ou une
application, et trouver la fiche qui la met en place pas à pas.

## Rappel : qui exécute quoi

Dans ce déploiement Podman, c'est le conteneur **poller** qui lance les
plugins (`check_by_ssh`, `check_nrpe`, `check_snmp`...). Il sort sur le réseau
comme n'importe quel client : une machine du LAN ou d'Internet se joint par
son IP ou son nom DNS. Seul cas particulier, le serveur Podman lui-même, qui
se joint par `host.containers.internal` (voir
[Configurer Shinken](../configuration.md#reseau-depuis-un-container)).

Un check **actif** est lancé par Shinken à intervalle régulier. Un check
**passif** est lancé par la machine supervisée, qui envoie son résultat à
Shinken.

## Tableau de choix

| Méthode | Sens | Agent sur la cible | Port ouvert | Pour quoi | Fiche |
|---|---|---|---|---|---|
| SSH actif | Shinken → cible | aucun (sshd + plugins) | 22 sur la cible | serveurs Linux/Unix | [SSH actif](ssh-actif.md) |
| SSH passif | cible → Shinken | un script lancé par cron / tâche planifiée | 2222 sur le serveur Shinken | machines derrière un pare-feu, DMZ, postes, sauvegardes et traitements batch | [SSH passif](ssh-passif.md) |
| NRPE | Shinken → cible | `nagios-nrpe-server` (Linux) ou NSClient++ (Windows) | 5666 sur la cible | serveurs Windows, Linux sans accès SSH | [NRPE et NSClient++](nrpe.md) |
| SNMP | Shinken → cible | agent SNMP (souvent déjà présent) | 161/udp sur la cible | switchs, routeurs, onduleurs, imprimantes, NAS, Linux | [SNMP](snmp.md) |
| API / HTTP | Shinken → service | aucun | port du service | applications web, endpoints `/health`, API REST, certificats | [API et HTTP](api.md) |

Points de repère :

- **Serveur Linux** : SSH actif (rien à installer). NRPE si la politique
  interdit l'accès SSH.
- **Serveur Windows** : NRPE avec NSClient++. Si la machine ne peut pas être
  jointe depuis Shinken, SSH passif (OpenSSH est intégré à Windows).
- **Équipement réseau** : SNMP, toujours.
- **Application** : API/HTTP pour « le service répond-il correctement », en
  plus de la supervision de la machine qui l'héberge.
- **Résultat produit par un traitement** (sauvegarde, export nocturne) :
  SSH passif, envoyé par le traitement lui-même à la fin de son exécution.

## Modèles fournis

| Modèle (`use`) | Fichier | Rôle |
|---|---|---|
| `linux-ssh` | `etc/templates/linux-ssh.cfg` | hôte supervisé par SSH (`_SSH_USER`, `_SSH_PORT`) |
| `nrpe-host` / `nrpe-ssl-host` | `etc/templates/nrpe-host.cfg` | hôte avec agent NRPE / NSClient++ (sans / avec certificat client) |
| `snmp-host` | `etc/templates/snmp-host.cfg` | équipement SNMP (`_SNMP_COMMUNITY`, `_SNMP_PORT`, `_SNMP_V3_USER`) |
| `passive-service` | `etc/templates/passive-service.cfg` | service alimenté par des résultats passifs, avec contrôle de fraîcheur |

## Pièges communs à tous les types

!!! attention "Caractères interdits dans les noms"
    `host_name` et `service_description` refusent ``` `~!$%^&*"|'<>?,()= ```.
    `Disk (C:)` fait planter l'arbiter au chargement : écrire `Disk C`.
    Évitez aussi `;`, qui sert de séparateur dans les commandes externes
    (résultats passifs, Thruk).

!!! attention "Arguments des commandes"
    Dans `check_command commande!arg1!arg2`, un `!` littéral s'écrit `\!`.
    Un `$` isolé passe tel quel (`check_snmp_storage!^/$!85!95` fonctionne,
    testé) ; écrivez `$$` seulement si le texte pourrait former une macro
    (`$NOM$`). Shinken passe la ligne à `/bin/sh` dès qu'elle
    contient un caractère spécial : un `>` non protégé devient une
    redirection. Pour NSClient++, utilisez `gt`/`lt` plutôt que `>`/`<`.

!!! information "Sorties de plugin et notifications"
    `etc/shinken.cfg` définit `illegal_macro_output_chars`
    (`` ` `` `~ $ & | ' " \ < >`). Ces caractères sont retirés des macros de
    sortie (`$SERVICEOUTPUT$`, `$HOSTOUTPUT$`, perfdata, commentaires
    d'acquittement) avant qu'elles n'arrivent dans une commande de
    notification : une sortie de plugin, ou un résultat passif envoyé par un
    client, ne peut pas y injecter de commande shell. Effet visible : ces
    caractères disparaissent aussi des mails (`l'espace` devient
    `lespace`). `$LONGSERVICEOUTPUT$` et `$LONGHOSTOUTPUT$` ne sont **pas**
    filtrés : ne les mettez jamais dans une ligne de commande.

## Validation

Après tout ajout de configuration :

```sh
podman exec shinken_arbiter_1 shinken-arbiter -v -c /etc/shinken/shinken.cfg
podman restart shinken_arbiter_1
```

Puis vérifier l'état dans l'interface (`http://127.0.0.1:8081/`) ou par
Livestatus :

```sh
printf 'GET services\nColumns: host_name description state plugin_output\nFilter: host_name = srv-web01\n\n' \
  | nc 127.0.0.1 50000
```

## Ce qui a été vérifié

Les commandes ont été testées avec les six daemons Shinken contre de vrais
démons Linux (sshd, snmpd v2c/v3, nrpe 4.1, serveur HTTP), à la main : le
détail et les limites sont en fin de chaque fiche. La CI rejoue à chaque push, dans des
conteneurs Podman séparés, le SSH actif (cible avec commande forcée), le
SSH passif (envoi par un client jusqu'à l'état du service) et le check API
JSON. Elle vérifie aussi que chaque plugin référencé dans `etc/commands`
est présent et se charge dans l'image (`integration/check_image_plugins.sh`).
NSClient++ (Windows) et le client PowerShell n'ont pas pu être testés.
