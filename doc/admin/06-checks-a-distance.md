# Superviser à distance : qui se connecte où, avec quoi

**Public :** administrateur de la supervision et exploitant, niveau simple
à avancé. Cette page répond aux questions « depuis où part la connexion ? »,
« avec quel compte ? », « où mettre la clé, le certificat, le mot de
passe ? » pour chaque méthode de check. Les procédures pas à pas sont dans
les [recettes](recettes/README.md).

## Règle de base : tout part du poller

Un check actif est **toujours** exécuté dans le conteneur **poller** (voir
[comment un check est exécuté](05-execution-des-checks.md)). Conséquences :

- l'adresse source vue par la cible est celle du poller, c'est-à-dire du
  **serveur de supervision** (les conteneurs Podman sortent par l'adresse de
  l'hôte) : c'est elle qu'on autorise dans les pare-feux, `allowed_hosts`
  de NRPE, `from=` de SSH ;
- la résolution DNS est celle **du conteneur**, qui ne voit pas le
  `/etc/hosts` de l'hôte ;
- les fichiers (clés, certificats, jetons) doivent être visibles **dans le
  conteneur**, avec les bons droits pour l'utilisateur du conteneur ;
- tout test manuel se fait **dans le poller** :
  `podman exec shinken-poller <commande>` (quadlets) ou
  `podman-compose exec poller <commande>`.

Les notifications suivent la même règle, mais depuis le conteneur
**reactionner** (relais SMTP, passerelle SMS).

## Vue d'ensemble des méthodes

| Méthode | Sens de la connexion | Port cible | Ce qui authentifie Shinken auprès de la cible | Où est le secret | Agent sur la cible | Recette |
|---|---|---|---|---|---|---|
| Réseau (ping, port TCP, DNS) | poller → cible | ICMP, port testé | rien | — | non | [DNS, ping, ports](recettes/dns.md) |
| HTTP / HTTPS | poller → cible | 80, 443… | rien, ou Basic, jeton, certificat client | `etc/resource.d/`, `etc/certs/` | non | [HTTP/TLS](recettes/http-tls.md) |
| API REST (JSON) | poller → cible | 443… | jeton Bearer, Basic, certificat client | fichier dans `etc/certs/` | non | [API REST](recettes/api-rest.md) |
| SSH | poller → cible | 22 | **clé SSH** sur un compte dédié | `etc/ssh_keys/` | non (sshd) | [Linux par SSH](recettes/linux-ssh.md) |
| NRPE | poller → cible | 5666 | adresse source (`allowed_hosts`), TLS, certificat client (v4) | `etc/certs/` | **oui** (NRPE) | [Linux par NRPE](recettes/linux-nrpe.md) |
| SNMP | poller → cible | 161/UDP | communauté (v2c) ou compte (v3) | `etc/resource.d/snmp.cfg` | agent SNMP | [SNMP](recettes/snmp.md) |
| Windows | poller → cible | 12489, 5666, 5985/5986 | mot de passe NSClient++, NRPE, compte WinRM | `etc/resource.d/` | NSClient++ conseillé | [Windows](recettes/windows.md) |
| Bases de données | poller → cible | 3306, 5432… | compte en lecture seule | `etc/resource.d/databases.cfg` | non | [Bases de données](recettes/bases-de-donnees.md) |
| **Passif** | **cible → Shinken** | 50000 (Livestatus) via SSH | clé SSH vers le serveur de supervision | côté cible | script émetteur | [Checks passifs](15-checks-passifs-commandes-externes.md) |

### Comment choisir

| Situation | Méthode conseillée |
|---|---|
| Serveur Linux, vous administrez la machine | **SSH** avec clé restreinte : rien à installer, contrôle total côté cible |
| Parc qui a déjà des agents NRPE | **NRPE** avec commandes figées |
| Serveur Windows | NSClient++ (NRPE ou API REST de NSClient++) |
| Équipement réseau, imprimante, onduleur | **SNMP** (v3 si possible) |
| Service web, application | **HTTP/HTTPS** ou **API** : on teste ce que voit l'utilisateur |
| Cible injoignable depuis le serveur | **passif**, ou poller dédié dans le réseau de la cible (`poller_tag`) |

## Qui est qui : les comptes en jeu

Quatre identités interviennent dans un check à distance. Les confondre est
la première cause de « ça marche à la main mais pas dans Shinken ».

| Identité | Où | Rôle |
|---|---|---|
| **Compte qui fait tourner Podman** | serveur de supervision (votre utilisateur, ou un compte dédié comme `app-shinken`) | possède les conteneurs et les fichiers de configuration sur l'hôte |
| **`shinken`, UID 10001** | **dans** les conteneurs | exécute les daemons **et les plugins** ; son `HOME` est `/var/lib/shinken` (volume persistant) |
| **Compte distant** (`$SSHUSER$`, `supervision` par défaut) | serveur supervisé | compte sur lequel le poller se connecte en SSH |
| **Compte applicatif** | API, base de données, SNMPv3 | identifiant technique de lecture, propre à chaque cible |

### UID dans le conteneur et sur l'hôte

Avec Podman **rootless**, les UID du conteneur sont décalés par rapport à
ceux de l'hôte. Ce que voit le conteneur dépend du mode d'espace de noms :

| Déploiement | Correspondance | Pour donner un fichier au compte `shinken` |
|---|---|---|
| `podman-compose` (`compose.yaml`) et quadlets fournis | UID 10001 du conteneur = un UID de la plage `subuid` de l'hôte (par exemple 534288) | `podman unshare chown 10001:10001 <fichier>` |
| conteneurs lancés avec `--userns keep-id:uid=10001,gid=10001` (par exemple via Puppet) | UID 10001 du conteneur = **le compte qui fait tourner Podman** | `chown <compte-podman> <fichier>` : un fichier qui lui appartient est vu comme appartenant à `shinken` |
| Podman exécuté en root | UID 10001 = UID 10001 de l'hôte | `chown 10001:10001 <fichier>` |

Pour savoir où vous en êtes :

```bash
podman exec shinken-poller cat /proc/self/uid_map    # correspondance des UID
podman exec shinken-poller ls -ln /etc/shinken/ssh_keys/
```

La seconde commande doit montrer `10001 10001` comme propriétaire des
fichiers de clés. Si elle montre `0`, `65534` ou un autre nombre, le
conteneur ne pourra pas les lire.

## SSH en détail

### Les fichiers

| Fichier | Sur l'hôte (dépôt de configuration) | Dans le conteneur poller | Droits attendus (vus du conteneur) |
|---|---|---|---|
| clé privée | `etc/ssh_keys/id_ed25519` | `/etc/shinken/ssh_keys/id_ed25519` (lecture seule) | propriétaire `10001`, mode **`600`** ou `400` |
| clé publique | `etc/ssh_keys/id_ed25519.pub` | idem `.pub` | indifférent |
| clés d'hôtes connues | — | `/var/lib/shinken/.ssh/known_hosts` (volume de données) | créé automatiquement |
| macros | `etc/resource.d/ssh.cfg` : `$SSHUSER$`, `$SSHKEY$` | — | — |

> **Attention** — OpenSSH **refuse** une clé privée lisible par le groupe ou
> par les autres (`WARNING: UNPROTECTED PRIVATE KEY FILE!`, puis
> `Permission denied (publickey)`). Un outil de déploiement qui pose
> `0750` ou `0640` sur tout le dossier de configuration casse donc les
> checks SSH : forcez `0600` sur la clé privée elle-même.

La clé privée n'est **jamais versionnée** : seul `etc/ssh_keys/README.md`
est suivi par git.

### Le compte distant

Sur chaque serveur supervisé, un compte **dédié**, sans privilège, sans mot
de passe :

```bash
sudo useradd --system --create-home --shell /bin/sh supervision
sudo install -d -m 700 -o supervision -g supervision ~supervision/.ssh
```

Ne réutilisez pas un compte personnel ni `root` : la clé du serveur de
supervision ouvrirait alors tout ce que ce compte peut faire.

Dans `~supervision/.ssh/authorized_keys`, la clé publique est **toujours
restreinte** :

```
from="192.0.2.5",command="/usr/local/lib/supervision/aiguilleur.sh",restrict ssh-ed25519 AAAA… supervision-shinken
```

| Option | Effet |
|---|---|
| `from="…"` | n'accepte la clé que depuis l'adresse du serveur de supervision |
| `command="…"` | **seule** cette commande s'exécute, quoi que demande le poller |
| `restrict` | pas de terminal, pas de redirection de ports ni d'agent |

L'aiguilleur compare `$SSH_ORIGINAL_COMMAND` à une liste fermée de checks :
modèle complet dans la [recette SSH](recettes/linux-ssh.md#plusieurs-checks-avec-une-seule-clé).

Si un check a besoin de privilèges (lire un journal protégé, interroger
`smartctl`), donnez-les par une règle `sudo` limitée à **cette commande
exacte**, sans argument libre, dans `/etc/sudoers.d/supervision` :

```
supervision ALL=(root) NOPASSWD: /usr/sbin/smartctl -H /dev/sda
```

### Une clé, plusieurs clés ?

| Organisation | Quand |
|---|---|
| **une clé pour tout le parc** (`$SSHKEY$`) | cas courant : la restriction `command=`/`from=` côté cible limite l'impact d'un vol |
| **une clé par zone** (production, DMZ, tests) | pour pouvoir révoquer une zone sans toucher aux autres |
| **un compte distant différent sur certains hôtes** | macro personnalisée sur l'hôte, utilisée par une commande dédiée |

Exemple avec une macro d'hôte (`_SSHUSER` sur l'hôte devient
`$_HOSTSSHUSER$` dans la commande) :

```
define host {
    use             generic-host
    host_name       srv-ancien
    address         192.0.2.20
    _SSHUSER        nagios
    _SSHKEY         /etc/shinken/ssh_keys/id_ed25519_ancien
}

define command {
    command_name    check_by_ssh_hote
    command_line    $NAGIOSPLUGINSDIR$/check_by_ssh -H $HOSTADDRESS$ -l $_HOSTSSHUSER$ -i $_HOSTSSHKEY$ -o StrictHostKeyChecking=accept-new -t 15 -C "$ARG1$"
}
```

### Les clés d'hôtes (`known_hosts`)

La commande fournie `check_by_ssh` passe
`-o StrictHostKeyChecking=accept-new` :

- **première connexion** : la clé d'hôte du serveur supervisé est
  enregistrée dans `/var/lib/shinken/.ssh/known_hosts` (le dossier est créé
  si besoin) ;
- **connexions suivantes** : si la clé d'hôte a changé, la connexion est
  refusée (`Host key verification failed`) et le service passe UNKNOWN.
  C'est voulu : soit le serveur a été réinstallé, soit quelqu'un s'interpose.

Une commande `check_by_ssh` écrite **sans** cette option refuse tout hôte
absent de `known_hosts`, donc échoue dès le premier check avec
`Host key verification failed`. Deux corrections : ajouter l'option, ou
pré-remplir le fichier :

```bash
podman exec shinken-poller sh -c \
  'mkdir -p ~/.ssh && ssh-keyscan -t ed25519 192.0.2.10 >> ~/.ssh/known_hosts'
```

Après une réinstallation légitime d'un serveur supervisé :

```bash
podman exec shinken-poller ssh-keygen -R 192.0.2.10
```

### Rotation de la clé

1. Générer la nouvelle clé (`id_ed25519_2026`) à côté de l'ancienne.
2. Ajouter la nouvelle clé publique dans les `authorized_keys` de **tout**
   le parc, à côté de l'ancienne (même options de restriction).
3. Changer `$SSHKEY$` dans `etc/resource.d/ssh.cfg`, recharger la
   configuration, vérifier qu'aucun check SSH ne passe UNKNOWN.
4. Retirer l'ancienne clé publique du parc, puis l'ancienne clé privée.

### Superviser le serveur de supervision lui-même

Depuis un conteneur, `localhost` désigne le conteneur, pas l'hôte. Utilisez
l'adresse **`host.containers.internal`** (Podman 4.7 et plus). Le sshd de
l'hôte voit alors la connexion venir d'une adresse interne au réseau de
Podman : adaptez `from=` en conséquence, et autorisez ce trafic dans le
pare-feu de l'hôte.

## NRPE en détail

- Le poller se connecte au port 5666 de la cible ; l'agent n'accepte que
  les adresses de `allowed_hosts` (mettez l'adresse du serveur de
  supervision).
- La connexion est chiffrée par TLS. Avec NRPE 4, un **certificat client**
  authentifie réellement le serveur de supervision : certificat et clé dans
  `etc/certs/` (mêmes règles de propriétaire et de droits que la clé SSH),
  commande `check_nrpe_tls` (voir `etc/certs/README.md`).
- Les commandes exécutées sont **définies sur la cible**
  (`command[nom]=…` dans `nrpe.cfg`) ; laissez `dont_blame_nrpe=0` pour
  que le réseau ne puisse pas choisir les arguments.
- L'agent tourne sous son propre compte (`nagios` ou `nrpe`) : c'est lui qui
  doit avoir les droits de lecture nécessaires aux checks.

## HTTP, HTTPS et API en détail

- Aucune identité n'est nécessaire pour une page publique : le check est un
  simple client.
- Le nom virtuel (en-tête `Host`) et le SNI sont pris dans l'adresse de
  l'hôte : déclarez l'hôte avec son **nom DNS** comme `address`.
- Le certificat du serveur est vérifié avec les autorités du conteneur. Une
  autorité interne s'ajoute à l'image, pas en désactivant la vérification.
- Les secrets (mot de passe Basic, jeton) ne doivent pas apparaître dans
  `check_command` :

| Secret | Où le mettre | Visible dans Thruk ? | Visible dans `ps` du conteneur ? |
|---|---|---|---|
| dans `check_command` | — | **oui** | oui |
| macro de ressource (`etc/resource.d/`) | `$APIPASSWORD$=…` | non | oui |
| **fichier** lu par le plugin (`--token-file`) | `etc/certs/…`, mode 400 | non | **non** |

## Vérifier un check à distance, dans l'ordre

1. **Résolution** : `podman exec shinken-poller getent hosts <nom>`.
2. **Réseau** : `podman exec shinken-poller /usr/lib/nagios/plugins/check_tcp -H <cible> -p <port>`.
3. **Identité** : la clé, le certificat, le jeton sont-ils lisibles par
   l'UID 10001 ? `podman exec shinken-poller ls -ln /etc/shinken/ssh_keys/`.
4. **Commande complète** : copier l'*Expanded Command* de Thruk et la
   relancer dans le poller, puis `echo $?`.
5. **Côté cible** : journal de sshd (`journalctl -u sshd`), de NRPE, du
   serveur web ou de l'API.

## Suite

- [Comment un check est exécuté et récolté](05-execution-des-checks.md)
- [Sécurité de l'installation](../exploitation/09-securite.md)
- [Écrire son propre plugin](16-ecrire-un-plugin.md)
