# Recette : machines qui envoient leurs résultats par SSH (checks passifs)

**Principe :** la machine supervisée lance elle-même ses checks (cron, tâche
planifiée, fin d'un traitement de sauvegarde) et **envoie** les résultats à
Shinken par SSH. Shinken n'a pas besoin de joindre la machine : utile
derrière un pare-feu, en DMZ, pour des postes de travail, ou pour le
résultat d'un traitement batch.

```
srv-web01 (cron)                       serveur de supervision
  shinken-passive-send                   conteneur passive-ssh (port 2222)
   lance ses checks           --ssh-->    sshd non-root, ForceCommand
   format send_nsca                       shinken-passive-receive
                                            vérifie chaque ligne
                                            --> Livestatus (broker:50000)
                                                --> arbiter --> scheduler
```

C'est la mise en œuvre de la recommandation de
[checks passifs et commandes externes](../15-checks-passifs-commandes-externes.md#2-soumettre-le-résultat) :
« faites transiter les résultats par SSH, avec une clé restreinte ».
`nagios.cmd` et le port Livestatus restent locaux au serveur ; seul le
port 2222 est ouvert aux clients, derrière le filtre décrit ci-dessous.

Fichiers fournis :

| Fichier | Rôle |
|---|---|
| `containers/shinken-passive-receive` | récepteur (dans l'image) |
| rôle `passive-ssh` de l'image, service `passive-ssh` de `compose.yaml`, `deploy/quadlet/shinken-passive-ssh.*` | sshd non-root dédié |
| `etc/templates/passive-service.cfg`, `etc/commands/check_passive_stale.cfg` | modèle de service passif avec contrôle de fraîcheur |
| `contrib/checks/passive/shinken-passive-send` | client Linux (sh + cron) |
| `contrib/checks/passive/shinken-passive-send.ps1` | client Windows (PowerShell + tâche planifiée) |

## Sécurité

- **Une clé par machine**, liée à **un seul** hôte Shinken
  (`environment="SHINKEN_PASSIVE_HOST=srv-web01"` sur sa ligne de
  `authorized_keys`). Une clé ne peut pas envoyer de résultats pour un autre
  hôte. La liaison est lue dans `authorized_keys` pour la clé qui s'est
  réellement authentifiée (`ExposeAuthInfo`), pas dans l'environnement de la
  session : un `~/.ssh/environment` ne peut pas la contourner.
- **Aucun shell** : sshd impose `shinken-passive-receive` (`ForceCommand`),
  sans PTY ni redirection de port, et n'exécute ni `~/.ssh/rc` ni
  `~/.ssh/environment`. Une clé sans liaison d'hôte est refusée.
- **Rien n'est relayé tel quel.** Seuls `PROCESS_SERVICE_CHECK_RESULT` et
  `PROCESS_HOST_CHECK_RESULT` sont acceptés. Chaque champ est vérifié (nom,
  code retour 0 à 3, longueur), et tout caractère de contrôle ou séparateur
  de ligne est retiré, y compris les séparateurs Unicode (U+2028, U+0085…)
  que Livestatus prendrait pour une nouvelle commande. La commande est
  ensuite reconstruite : un client ne peut pas envoyer `DISABLE_NOTIFICATIONS`.
- **L'horodatage est celui du serveur.** Shinken ignore sans aucun message un
  résultat plus ancien que le dernier check : une horloge cliente en retard
  ferait disparaître les résultats.
- **Isolé des autres daemons** : le conteneur a son propre volume
  (`passive-ssh-data`) pour sa clé d'hôte et sa copie de `authorized_keys`.

> **Attention** — Livestatus n'a pas d'authentification. Son port n'est
> publié que sur `127.0.0.1` du serveur : ne le publiez jamais ailleurs, et
> limitez les comptes sur ce serveur. Les clients passent uniquement par le
> port 2222 et le filtre ci-dessus.

## 1. Déclarer l'hôte et ses services passifs

```
# etc/hosts/srv-web01.cfg
define host {
    use                     generic-host
    host_name               srv-web01
    address                 srv-web01.example.lan
}

# etc/services/srv-web01-passif.cfg
define service {
    use                     passive-service
    host_name               srv-web01
    service_description     Sauvegarde
    freshness_threshold     93600       ; sauvegarde quotidienne : 26 h
}
define service {
    use                     passive-service
    host_name               srv-web01
    service_description     Disque
    ; freshness_threshold 900 (défaut du modèle) pour un envoi toutes les 5 min
}
```

Le modèle `passive-service` désactive les checks actifs et active le
**contrôle de fraîcheur** : sans résultat reçu depuis `freshness_threshold`
secondes, le service passe en **UNKNOWN** (« No passive result received in
time »). Un client arrêté se voit, au lieu de rester « OK » indéfiniment.
Mettez au moins deux fois l'intervalle d'envoi.

`first_notification_delay 20` (minutes) laisse aux clients le temps de
renvoyer un résultat après un démarrage à vide (première mise en service,
fichier de rétention absent) : un résultat reçu entre-temps annule la
notification en attente.

> **Hôte actif, résultat d'hôte passif** — Si l'hôte a un check actif, un
> résultat d'hôte envoyé en passif est remplacé au check actif suivant. Pour
> un hôte uniquement passif : `active_checks_enabled 0` et
> `check_freshness 1` sur l'hôte.

## 2. Autoriser la clé de la machine

La clé est générée **sur le client** (elle ne le quitte jamais, étape 4 ou 5).
Sa partie publique va dans `etc/passive/authorized_keys` (ignoré par git),
une ligne par machine :

```
environment="SHINKEN_PASSIVE_HOST=srv-web01" ssh-ed25519 AAAA... srv-web01
environment="SHINKEN_PASSIVE_HOST=srv-win01" ssh-ed25519 AAAA... srv-win01
```

`SHINKEN_PASSIVE_HOST` doit être **exactement** le `host_name` Shinken
(sensible à la casse).

## 3. Démarrer le récepteur

Avec compose :

```bash
podman-compose --profile passive up -d passive-ssh
podman-compose logs passive-ssh          # « Server listening on 0.0.0.0 port 2222. »
```

Avec les quadlets : copier aussi `deploy/quadlet/shinken-passive-ssh.container`
et `shinken-passive-ssh.volume`, puis
`systemctl --user daemon-reload && systemctl --user start shinken-passive-ssh`.

Ouvrez le port 2222/tcp du serveur aux seules machines clientes (pare-feu).
Le port publié se change avec `SHINKEN_PASSIVE_PORT` dans `.env`. Après
chaque modification de `authorized_keys`, redémarrez le récepteur
(`podman-compose restart passive-ssh` ou `systemctl --user restart shinken-passive-ssh`).

## 4. Client Linux

```bash
install -d -m 700 /etc/shinken-passive
ssh-keygen -t ed25519 -N "" -C srv-web01 -f /etc/shinken-passive/id_ed25519
ssh-keyscan -p 2222 supervision.example.com > /etc/shinken-passive/known_hosts   # vérifier l'empreinte
install -m 755 shinken-passive-send /usr/local/bin/    # contrib/checks/passive/shinken-passive-send
```

`/etc/shinken-passive/client.conf` :

```bash
SHINKEN_SERVER=supervision.example.com
SHINKEN_PORT=2222
SHINKEN_HOST=srv-web01
SHINKEN_KEY=/etc/shinken-passive/id_ed25519
```

`/etc/shinken-passive/checks.conf` : un check par ligne, séparé par une
**tabulation** (`service<TAB>commande`) ; `HOST` pour un résultat d'hôte :

```
Disque	/usr/lib/nagios/plugins/check_disk -w 20% -c 10% -p /
Sauvegarde	/usr/local/lib/check_backup.sh
HOST	/usr/lib/nagios/plugins/check_dummy 0 "UP"
```

Cron :

```
*/5 * * * * root /usr/local/bin/shinken-passive-send >/var/log/shinken-passive.log 2>&1
```

Un traitement peut aussi envoyer son résultat lui-même, à la fin de son
exécution :

```bash
printf 'srv-web01\tSauvegarde\t0\tOK - sauvegarde terminée en 42 min\n' \
  | ssh -T -p 2222 -i /etc/shinken-passive/id_ed25519 \
        -o UserKnownHostsFile=/etc/shinken-passive/known_hosts shinken@supervision.example.com
```

## 5. Client Windows

Windows 10, Server 2019 et versions ultérieures embarquent `ssh.exe`
(fonctionnalité « Client OpenSSH »).

1. Copier `contrib/checks/passive/shinken-passive-send.ps1` dans
   `C:\ProgramData\shinken-passive\`.
2. Générer la clé, récupérer l'empreinte du serveur, restreindre la clé :
   ```powershell
   ssh-keygen -t ed25519 -N '""' -C srv-win01 -f C:\ProgramData\shinken-passive\id_ed25519
   ssh-keyscan -p 2222 supervision.example.com | Out-File -Encoding ascii C:\ProgramData\shinken-passive\known_hosts
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

> Le script PowerShell suit le même format que le client Linux, qui est
> testé ; il n'a pas pu être exécuté sur une vraie machine Windows.

## Format accepté

Une ligne par résultat, sur l'entrée standard :

| Format | Exemple |
|---|---|
| send_nsca, service | `srv-web01<TAB>Disque<TAB>1<TAB>DISK WARNING - 82% used\|used=82%` |
| send_nsca, hôte | `srv-web01<TAB>0<TAB>UP` |
| commande externe | `[1730375000] PROCESS_SERVICE_CHECK_RESULT;srv-web01;Disque;1;DISK WARNING` |

Les lignes vides et celles commençant par `#` sont ignorées. Le récepteur
répond ligne par ligne :

```
OK line 1: srv-web01;Disque rc=1
REJECTED line 2: service 'Dsique' is not defined on srv-web01
forwarded=1 rejected=1
```

Code retour du `ssh` : `0` tout relayé, `1` au moins une ligne rejetée,
`2` Livestatus injoignable ou clé non liée (rien n'a été relayé).

« OK » veut dire « transmis » : Livestatus n'accuse pas réception. Le
résultat est valide, le service existe et accepte le passif, et le résultat
a été transmis ; il est appliqué en 1 à 3 secondes (broker, arbiter puis
scheduler). Si l'arbiter est arrêté à ce moment-là, il est perdu, et le
contrôle de fraîcheur le signalera.

## 6. Tester

```bash
printf 'srv-web01\tDisque\t0\tOK - test manuel\n' \
  | ssh -T -p 2222 -i /etc/shinken-passive/id_ed25519 shinken@supervision.example.com
# OK line 1: srv-web01;Disque rc=0
# forwarded=1 rejected=0
```

Quelques secondes plus tard, le service `Disque` affiche « OK - test manuel »
dans l'interface.

## Dépannage

| Message | Cause | Action |
|---|---|---|
| `Permission denied (publickey)` | Clé absente de `etc/passive/authorized_keys`, ou récepteur non redémarré | Ajouter la ligne, redémarrer `passive-ssh` |
| `this key is not bound to a host` | Ligne sans `environment="SHINKEN_PASSIVE_HOST=..."` | Ajouter la liaison d'hôte |
| `this key may only send results for X` | Le client envoie pour un autre `host_name` | Corriger `SHINKEN_HOST` côté client, ou la liaison côté serveur |
| `service 'X' is not defined on H` | Nom différent (casse, espace) ou configuration non rechargée | Comparer avec `service_description`, recharger la configuration |
| `does not accept passive checks` | Service avec `passive_checks_enabled 0` | Utiliser le modèle `passive-service` |
| `Livestatus unreachable` | Broker arrêté, ou Livestatus en panne | `podman-compose logs broker \| grep -i livestatus` |
| Service UNKNOWN « No passive result received in time » | Le client n'envoie plus, ou `freshness_threshold` trop court | Vérifier le cron du client et son journal ; seuil ≥ 2 × l'intervalle |
| `Host key verification failed` (client) | Empreinte du serveur absente ou changée (volume `passive-ssh-data` recréé) | Refaire `ssh-keyscan -p 2222` et vérifier l'empreinte |
| Log du récepteur : `missing or unreadable` | `etc/passive/authorized_keys` absent ou illisible par l'UID 10001 | Créer le fichier ; `podman unshare chown 10001:10001 etc/passive/authorized_keys` si besoin |
