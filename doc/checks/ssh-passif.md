---
title: "Recevoir des résultats passifs par SSH"
domain: "Shinken"
type: "procedure"
level: "intermediaire"
duration: "30 min"
version: "1.0"
updated: "2026-10-31"
owner: "Administration Supervision"
status: "valid"
order: 12
keywords: [passif, ssh, nsca, livestatus, freshness, fraîcheur, cron, powershell, windows]
summary: "Les machines supervisées envoient leurs résultats à Shinken par SSH (format send_nsca), avec une clé liée à un seul hôte et un contrôle de fraîcheur."
---

# Recevoir des résultats passifs par SSH

## Objectif

La machine supervisée lance elle-même ses checks (cron, tâche planifiée, fin
d'un traitement de sauvegarde) et **envoie** les résultats à Shinken par SSH.
Shinken n'a pas besoin de joindre la machine : utile derrière un pare-feu, en
DMZ, pour des postes, ou pour le résultat d'un traitement batch.

```
srv-web01 (cron)                      serveur Podman
  shinken-passive-send                  conteneur passive-ssh (port 2222)
   lance ses checks          --ssh-->    sshd non-root, ForceCommand
   format send_nsca                      shinken-passive-receive
                                           vérifie chaque ligne
                                           --> Livestatus (broker:50000)
                                               --> arbiter --> scheduler
```

## Pourquoi pas `nagios.cmd` ?

Dans un Shinken classique, on écrit les résultats dans le tube nommé
`nagios.cmd`, ou on passe par NSCA. Aucun des deux n'est disponible ici : le
module `named_pipe` n'est pas livré, un tube nommé partagé entre conteneurs
est fragile, et les modules NSCA/ws-arbiter de Shinken ne sont pas portés en
Python 3. Livestatus accepte les **mêmes lignes de commandes externes**, et
c'est la seule entrée disponible.

## Sécurité

- **Une clé par machine**, liée à **un seul** hôte Shinken
  (`environment="SHINKEN_PASSIVE_HOST=srv-web01"` dans `authorized_keys`).
  Une clé ne peut pas envoyer de résultats pour un autre hôte.
- **Aucun shell** : sshd impose `shinken-passive-receive` (`ForceCommand`),
  sans PTY, sans redirection de port. Une clé sans liaison d'hôte est refusée.
- **Rien n'est relayé tel quel.** Seuls `PROCESS_SERVICE_CHECK_RESULT` et
  `PROCESS_HOST_CHECK_RESULT` sont acceptés. Chaque champ est vérifié (nom,
  code retour 0 à 3, caractères de contrôle, longueur), puis la commande est
  reconstruite. Un client ne peut donc pas envoyer `DISABLE_NOTIFICATIONS`.
- **L'horodatage est celui du serveur.** Shinken ignore sans aucun message un
  résultat plus ancien que le dernier check : une horloge cliente en retard
  ferait disparaître les résultats.

!!! attention "Livestatus n'a pas d'authentification"
    Le port 50000 est publié sur `127.0.0.1` de l'hôte Podman : tout
    utilisateur local du serveur peut y envoyer n'importe quelle commande
    externe. Ne le publiez jamais sur une autre adresse, et limitez les
    comptes sur ce serveur. Les clients passifs passent uniquement par le
    port 2222 et le filtre décrit ci-dessus.

## Étapes côté Shinken

### 1. Déclarer l'hôte et ses services passifs

```ini
# etc/hosts/srv-web01.cfg
define host{
        use                     generic-host
        host_name               srv-web01
        address                 srv-web01.example.lan
        }

# etc/services/srv-web01-passif.cfg
define service{
        use                     passive-service
        host_name               srv-web01
        service_description     Backup
        freshness_threshold     93600   ; sauvegarde quotidienne : 26 h
        }
define service{
        use                     passive-service
        host_name               srv-web01
        service_description     Disk
        ; freshness_threshold 900 (défaut du modèle) pour un envoi toutes les 5 min
        }
```

Le modèle `passive-service` désactive les checks actifs et active le
**contrôle de fraîcheur** : sans résultat reçu depuis `freshness_threshold`
secondes, le service passe en **UNKNOWN** (« No passive result received in
time »). Un client arrêté se voit donc, au lieu de rester « OK » pour
toujours. Mettez au moins deux fois l'intervalle d'envoi.

!!! information "Après un redémarrage de Shinken"
    Aucun module de rétention n'est livré : après un redémarrage, les
    services passifs repassent en UNKNOWN en moins d'une minute, jusqu'au
    prochain envoi de leur client. D'où UNKNOWN plutôt que CRITICAL, pour ne
    pas déclencher une vague d'alertes.

!!! information "Hôte actif, résultat d'hôte passif"
    Si l'hôte a un check actif (`check_command`), un résultat d'hôte envoyé
    en passif est remplacé au check actif suivant. Pour un hôte uniquement
    passif, mettez `active_checks_enabled 0` et `check_freshness 1` sur
    l'hôte.

### 2. Autoriser la clé de la machine

Générer la clé **sur le client** (elle ne quitte jamais la machine), puis
ajouter sa partie publique dans `etc/passive/authorized_keys` (ignoré par
git) :

```
environment="SHINKEN_PASSIVE_HOST=srv-web01" ssh-ed25519 AAAA... srv-web01
```

`SHINKEN_PASSIVE_HOST` doit être **exactement** le `host_name` Shinken
(sensible à la casse).

### 3. Démarrer le récepteur

```sh
podman-compose --profile passive up -d passive-ssh
podman logs shinken_passive-ssh_1     # "Server listening on 0.0.0.0 port 2222."
```

Ouvrez le port 2222/tcp du serveur aux clients, et à eux seuls. Après chaque
modification de `authorized_keys` : `podman restart shinken_passive-ssh_1`.

## Étapes côté client Linux

```sh
install -d -m 700 /etc/shinken-passive
ssh-keygen -t ed25519 -N "" -C srv-web01 -f /etc/shinken-passive/id_ed25519
ssh-keyscan -p 2222 shinken.example.lan > /etc/shinken-passive/known_hosts   # vérifier l'empreinte
install -m 755 shinken-passive-send /usr/local/bin/      # contrib/checks/passive/shinken-passive-send
```

`/etc/shinken-passive/client.conf` :

```sh
SHINKEN_SERVER=shinken.example.lan
SHINKEN_PORT=2222
SHINKEN_HOST=srv-web01
SHINKEN_KEY=/etc/shinken-passive/id_ed25519
```

`/etc/shinken-passive/checks.conf` : un check par ligne, séparé par une
**tabulation** (`service<TAB>commande`) :

```
Disk	/usr/lib/nagios/plugins/check_disk -w 20% -c 10% -p /
Backup	/usr/local/lib/check_backup.sh
HOST	/usr/lib/nagios/plugins/check_dummy 0 "UP"
```

Cron :

```
*/5 * * * * root /usr/local/bin/shinken-passive-send >/var/log/shinken-passive.log 2>&1
```

Un traitement peut aussi envoyer son résultat directement à la fin de son
exécution, sans fichier de configuration :

```sh
printf 'srv-web01\tBackup\t0\tOK - sauvegarde terminée en 42 min\n' \
  | ssh -T -p 2222 -i /etc/shinken-passive/id_ed25519 \
        -o UserKnownHostsFile=/etc/shinken-passive/known_hosts shinken@shinken.example.lan
```

## Étapes côté client Windows

Windows 10, Server 2019 et versions ultérieures embarquent `ssh.exe`
(fonctionnalité « Client OpenSSH »).

1. Copier `contrib/checks/passive/shinken-passive-send.ps1` dans
   `C:\ProgramData\shinken-passive\`.
2. Générer la clé et récupérer l'empreinte du serveur :
   ```powershell
   ssh-keygen -t ed25519 -N '""' -C srv-win01 -f C:\ProgramData\shinken-passive\id_ed25519
   ssh-keyscan -p 2222 shinken.example.lan | Out-File -Encoding ascii C:\ProgramData\shinken-passive\known_hosts
   icacls C:\ProgramData\shinken-passive\id_ed25519 /inheritance:r /grant:r "SYSTEM:F" "Administrators:F"
   ```
3. Créer `C:\ProgramData\shinken-passive\client.psd1` (`Server`, `Port`,
   `HostName`, `Key`, `KnownHosts` : voir l'en-tête du script).
4. Adapter la liste `$checks` du script : disque C:, mémoire et services
   automatiques arrêtés sont fournis ; un bloc commenté montre comment
   appeler un script `.ps1` maison.
5. Tâche planifiée toutes les 5 minutes :
   ```powershell
   schtasks /Create /TN "Shinken passive" /SC MINUTE /MO 5 /RU SYSTEM /TR "powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\ProgramData\shinken-passive\shinken-passive-send.ps1"
   ```

!!! information "Non testé sous Windows"
    Le script PowerShell suit le même format que le client Linux, qui est
    testé, mais il n'a pas pu être exécuté sur une vraie machine Windows.

## Format accepté

Une ligne par résultat, sur l'entrée standard :

| Format | Exemple |
|---|---|
| send_nsca, service | `srv-web01<TAB>Disk<TAB>1<TAB>DISK WARNING - 82% used\|used=82%` |
| send_nsca, hôte | `srv-web01<TAB>0<TAB>UP` |
| commande externe | `[1730375000] PROCESS_SERVICE_CHECK_RESULT;srv-web01;Disk;1;DISK WARNING` |

Les lignes vides et celles commençant par `#` sont ignorées. Le récepteur
répond ligne par ligne :

```
OK line 1: srv-web01;Disk rc=1
REJECTED line 2: service 'Dsik' is not defined on srv-web01
forwarded=1 rejected=1
```

Code retour du `ssh` : `0` tout relayé, `1` au moins une ligne rejetée,
`2` Livestatus injoignable ou clé non liée (rien n'a été relayé).

!!! information "« OK » veut dire « transmis »"
    Livestatus n'accuse pas réception. « OK » signifie que le résultat est
    valide, que le service existe et accepte le passif, et qu'il a été
    transmis. Il est appliqué en 1 à 3 secondes (broker, arbiter puis
    scheduler). Si l'arbiter est arrêté à ce moment-là, il est perdu ; le
    contrôle de fraîcheur le signalera.

## Validation

```sh
printf 'srv-web01\tDisk\t0\tOK - test manuel\n' | ssh -T -p 2222 -i <clé> shinken@shinken.example.lan
# OK line 1: srv-web01;Disk rc=0
# forwarded=1 rejected=0
```

Puis, quelques secondes plus tard, le service `Disk` affiche
« OK - test manuel » dans l'interface.

## Dépannage {#depannage}

| Message | Cause | Action |
|---|---|---|
| `Permission denied (publickey)` | Clé absente de `etc/passive/authorized_keys`, ou conteneur non redémarré | Ajouter la ligne puis `podman restart shinken_passive-ssh_1` |
| `this key is not bound to a host` | Ligne sans `environment="SHINKEN_PASSIVE_HOST=..."` | Ajouter la liaison d'hôte |
| `this key may only send results for X` | Le client envoie pour un autre `host_name` | Corriger `SHINKEN_HOST` côté client, ou la liaison côté serveur |
| `service 'X' is not defined on H` | Nom du service différent (casse, espace) ou configuration non rechargée | Comparer avec `service_description` ; `podman restart shinken_arbiter_1` |
| `does not accept passive checks` | Service avec `passive_checks_enabled 0` | Utiliser le modèle `passive-service` |
| `Livestatus unreachable` | Broker arrêté, ou Livestatus en panne | `podman logs shinken_broker_1 \| grep -i livestatus` |
| Service UNKNOWN « No passive result received in time » | Le client n'envoie plus, ou `freshness_threshold` trop court | Vérifier le cron du client et son log ; seuil supérieur ou égal à 2 × l'intervalle |
| `Host key verification failed` (client) | Empreinte du serveur absente ou changée (conteneur recréé sans son volume) | Refaire `ssh-keyscan -p 2222` et vérifier l'empreinte |

## Voir aussi

- [SSH actif](ssh-actif.md)
- [Brancher Thruk via Livestatus](../livestatus-thruk.md)
- [Choisir un type de check](README.md)
