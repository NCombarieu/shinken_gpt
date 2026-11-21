# Thruk : comptes et droits

**Public :** exploitant système et administrateur de la supervision.

Trois mécanismes **indépendants** décident de ce qu'un utilisateur voit et
peut faire. Il faut les trois pour qu'un compte fonctionne.

| Mécanisme | Où | Décide… |
|---|---|---|
| **Authentification** | Thruk : `etc/htpasswd` du site OMD | qui peut se connecter |
| **Visibilité** | Shinken : contacts (`etc/contacts/`) | quels hôtes et services le compte **voit** |
| **Rôles** | Thruk : `etc/thruk/cgi.cfg` | ce que le compte peut **faire** au-delà (tout voir, envoyer des commandes, administrer Thruk) |

## 1. Authentification : les comptes Thruk

Les comptes sont dans le fichier `htpasswd` du site
(`/omd/sites/<site>/etc/htpasswd`). Pour créer un compte ou changer un mot
de passe :

```bash
podman exec -it omd-thruk su - demo -c 'htpasswd -B etc/htpasswd alice'
```

Le compte d'administration d'OMD est `omdadmin` ; son mot de passe se
change avec `set_admin_password` (pas avec `htpasswd`) :

```bash
podman exec -it omd-thruk su - demo -c 'set_admin_password'
```

> **Attention** — Un compte ajouté à la main dans le conteneur peut ne pas
> survivre : un réglage rejoué au démarrage, une réinitialisation du site
> ou la recréation du volume le fait disparaître, et c'est difficile à
> diagnostiquer (« mot de passe refusé » sans changement apparent). Pour
> des comptes durables, **faites-les créer par le playbook drop-in** (voir
> [le conteneur](01-conteneur.md#démarrage--ce-que-fait-limage)), à partir
> de mots de passe stockés en secret, avec `htpasswd -B -b`.

Pour une authentification centralisée (LDAP, Kerberos, OIDC), Thruk peut
déléguer à Apache ou à un reverse proxy authentifiant : voir la
documentation de Thruk (*cookie_auth*, *REMOTE_USER*). Les règles
ci-dessous restent valables : le **nom de login** transmis doit
correspondre à un contact Shinken.

## 2. Visibilité : le login doit être un contact Shinken

Livestatus filtre chaque requête de Thruk par l'utilisateur connecté
(`AuthUser: <login>`) : il ne renvoie que les hôtes et services dont ce
login est **contact**, directement ou via un groupe de contacts.

```
# etc/contacts/alice.cfg
define contact {
    use             generic-contact
    contact_name    alice              # = login Thruk, à la lettre près
    alias           Alice Martin
    email           alice@example.com
    contactgroups   admins
}
```

| Cas | Ce que voit le compte |
|---|---|
| login = `contact_name`, contact de tout (groupe `admins` placé sur tous les modèles) | tout |
| login = `contact_name`, contact de quelques hôtes | ces hôtes et leurs services |
| login **sans** contact correspondant | **rien**, sans message d'erreur |
| login avec le rôle `authorized_for_all_hosts` / `_services` | tout, même sans être contact |

Pour qu'un utilisateur voie sans recevoir de notifications, créez un
contact sans notification (modèle `etc/contacts/guest.cfg` :
`host_notifications_enabled 0`, `service_notifications_enabled 0`).

Après avoir ajouté un contact, **rechargez la configuration Shinken** : le
contact n'existe pour Livestatus qu'une fois la nouvelle configuration
distribuée.

## 3. Rôles : `cgi.cfg`

`/omd/sites/<site>/etc/thruk/cgi.cfg` attribue des rôles à des listes de
logins (séparés par des virgules, `*` = tout le monde) :

| Directive | Permet |
|---|---|
| `authorized_for_admin` | **tous** les rôles ci-dessous, plus l'administration de Thruk |
| `authorized_for_all_hosts` / `authorized_for_all_services` | voir tous les objets, sans être contact |
| `authorized_for_all_host_commands` / `authorized_for_all_service_commands` | envoyer des commandes sur tous les objets |
| `authorized_for_system_information` | voir *Process Info*, *Performance Info* |
| `authorized_for_system_commands` | commandes globales : arrêt des notifications, **redémarrage** de Shinken |
| `authorized_for_configuration_information` | voir la configuration, dont la ligne de commande complète des checks |
| `authorized_for_read_only` | interdire toute commande, même sur ses propres objets |
| `authorized_for_reports` | rapports de disponibilité |

Un contact Shinken peut déjà envoyer des commandes (forcer un check,
acquitter) **sur les objets dont il est contact**. Les rôles servent pour
le reste.

Exemple, deux administrateurs et un opérateur en lecture seule :

```
authorized_for_admin=omdadmin,alice,bob
authorized_for_read_only=charlie
```

> **Note** — Être contact du groupe `admins` côté Shinken ne donne **aucun**
> rôle dans Thruk : le contact règle la visibilité, `cgi.cfg` règle les
> droits. Pour un administrateur, il faut les deux.

### Afficher la commande exacte des checks

Thruk masque la carte *Check Command / Expanded Command* aux comptes sans
rôle de configuration. Pour l'afficher à tous, dans un fichier de
`thruk_local.d/` :

```
show_full_commandline = 2
```

(`0` = jamais, `1` = rôle de configuration seulement, `2` = tout le monde.)
Indispensable pour diagnostiquer un check, mais attention : si un mot de
passe figure dans une `command_line`, il devient visible. Gardez les
secrets dans des fichiers (voir [checks à distance](../admin/06-checks-a-distance.md#http-https-et-api-en-détail)).

## Vérifier un compte

1. Connexion : la page de connexion accepte-t-elle le mot de passe ?
   Sinon, `htpasswd` (et sa persistance).
2. Visibilité : une fois connecté, le compte voit-il ses objets ? Sinon,
   contact Shinken manquant ou nom différent. Vérification directe :

   ```bash
   podman exec omd-thruk timeout 5 bash -c \
     'exec 3<>/dev/tcp/broker/50000; printf "GET hosts\nColumns: name\nAuthUser: alice\n\n" >&3; cat <&3'
   ```

   La commande affiche la liste des hôtes que voit `alice`, vide si elle
   n'est contact de rien, puis rend la main au bout de 5 s (le Livestatus de
   Shinken garde la connexion ouverte).
3. Droits : les boutons de commande apparaissent-ils ? Sinon, `cgi.cfg`.

## Suite

[4. Exposition et dépannage](04-exposition-et-depannage.md)
