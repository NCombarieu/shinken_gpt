# Démarrage rapide : superviser un premier hôte

**Public :** administrateur de la supervision, niveau simple.
**Prérequis :** Shinken installé et démarré (voir
[installation](../exploitation/01-installation.md)).

Cette page montre le cycle complet : ajouter un hôte, un service, un contact,
vérifier la configuration, la recharger et constater le résultat.

## 1. Où se trouve la configuration

Toute la configuration est dans le dossier `etc/` du dépôt (monté en lecture
seule sur `/etc/shinken` dans les conteneurs) :

```
etc/
├── shinken.cfg      fichier principal (liste des dossiers chargés, réglages globaux)
├── hosts/           vos hôtes            ← vous écrivez surtout ici
├── services/        vos services         ← et ici
├── contacts/        les personnes à prévenir
├── commands/        les commandes de check disponibles
├── templates/       les modèles generic-host, generic-service…
└── resource.d/      macros globales (chemins, mots de passe techniques)
```

Tout fichier `.cfg` déposé dans ces dossiers est chargé automatiquement : il
n'y a rien à déclarer ailleurs. Organisez-vous comme vous le souhaitez, par
exemple un fichier par serveur.

## 2. Ajouter un hôte

Créez `etc/hosts/srv-web-01.cfg` :

```
define host {
    use                 generic-host
    host_name           srv-web-01
    alias               Serveur web de production
    address             192.0.2.10
}
```

- `use generic-host` : l'hôte hérite des réglages du modèle (check par ping
  toutes les 5 minutes, notifications au groupe `admins`…).
- `host_name` : nom unique, utilisé partout ailleurs pour désigner l'hôte.
- `address` : adresse IP ou nom DNS, que les checks utilisent.

> **Note** — Si la machine ne répond pas au ping, remplacez le check d'hôte,
> par exemple `check_command  check_tcp!22` (l'hôte est UP si le port SSH
> répond).

## 3. Ajouter un service

Créez `etc/services/srv-web-01.cfg` :

```
define service {
    use                     generic-service
    host_name               srv-web-01
    service_description     HTTP
    check_command           check_http!/
}
```

- `check_command` : la commande à exécuter (définie dans `etc/commands/`),
  suivie de ses arguments séparés par `!`. Ici `check_http` avec l'URL `/`.
- `service_description` : nom du service, unique pour cet hôte.

> **Attention** — Certains caractères sont interdits dans les noms
> (`` ` ~ ! $ % ^ & * " | ' < > ? , ( ) = ``). Un nom comme `CPU (SSH)` fait
> refuser **toute** la configuration : écrivez `CPU via SSH`.

Les commandes déjà disponibles sont listées dans `etc/commands/` ; chaque
fichier commence par un commentaire qui explique ses arguments. Pour en créer
une, voir [écrire un plugin](16-ecrire-un-plugin.md).

## 4. Ajouter un contact

Le contact `admin` (`etc/contacts/admin.cfg`) reçoit déjà toutes les
notifications : **remplacez son adresse e-mail et son mot de passe**. Pour
ajouter une personne, créez `etc/contacts/jdupont.cfg` :

```
define contact {
    use             generic-contact
    contact_name    jdupont
    alias           Jeanne Dupont
    email           jeanne.dupont@example.com
    contactgroups   admins
}
```

Être membre du groupe `admins` suffit : les modèles `generic-host` et
`generic-service` notifient ce groupe. Pour que les e-mails partent, le
relais SMTP doit être configuré (voir [notifications](17-notifications.md)).

## 5. Vérifier la configuration

Avant de recharger, faites vérifier la configuration par l'arbiter :

```bash
podman-compose run --rm --no-deps arbiter check
```

Le rôle `check` du conteneur lance `shinken-arbiter -v` sur la configuration
montée. La commande se termine par `Things look okay - No serious problems
were detected during the pre-flight check` si tout va bien. Sinon, les
lignes `[ERROR]` indiquent le fichier et la directive en cause.

> **Note** — Avec les quadlets, ou hors conteneur, voir
> [opérations courantes](../exploitation/03-operations-courantes.md#vérifier-la-configuration).

## 6. Recharger

Shinken n'a pas de rechargement à chaud : on redémarre l'arbiter, qui relit
`etc/` et renvoie la configuration aux autres daemons.

```bash
podman-compose restart arbiter
```

Ou depuis Thruk : *System → Process Info → Restart the monitoring process*.

Les acquittements, downtimes et états en cours sont conservés par le module de
rétention (voir [rétention](25-retention.md)).

## 7. Constater le résultat

Après un rechargement, les premiers checks sont **étalés sur 5 minutes**
(`max_service_check_spread` dans `shinken.cfg`) : un nouvel hôte reste
*PENDING* quelques minutes, c'est normal. Pour ne pas attendre, forcez un
check depuis Thruk (*Re-schedule the next check*).

Dans Thruk, ou en ligne de commande :

```bash
podman-compose exec broker shinken-healthcheck
```

affiche l'état de chaque hôte et service.

## Et ensuite

- Comprendre ce que vous voyez : [concepts essentiels](02-concepts.md).
- Superviser un serveur Linux, Windows, un équipement SNMP, un site HTTPS :
  [recettes](recettes/README.md).
- Factoriser la configuration : [modèles et héritage](10-templates-heritage.md).
