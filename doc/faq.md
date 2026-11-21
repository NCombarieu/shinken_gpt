# Questions fréquentes

### Pourquoi mon nouvel hôte reste-t-il PENDING ?

Après chaque rechargement, les premiers checks sont étalés sur 5 minutes.
Forcez un check depuis Thruk, ou attendez. Si cela dure, voir le
[dépannage](exploitation/11-depannage.md#un-hôte-ou-un-service-reste-pending).

### J'ai modifié un fichier `.cfg` et rien ne change.

La configuration n'est relue qu'au redémarrage de l'arbiter :
`podman-compose restart arbiter` (ou bouton *Restart* de Thruk). Vérifiez
d'abord avec `podman-compose run --rm --no-deps arbiter check`.

### Où mettre mon script de check ?

Dans `plugins-local/`, exécutable (`chmod 755`), puis dans une commande
`$LOCALPLUGINSDIR$/mon_script.sh`. Voir
[écrire un plugin](admin/16-ecrire-un-plugin.md).

### Mon plugin marche sur le serveur mais pas dans Shinken.

Il s'exécute dans le conteneur poller, sous l'utilisateur `shinken`, avec le
réseau et le DNS du conteneur. Testez-le avec
`podman-compose exec poller …`.

### Pourquoi ne reçois-je aucun e-mail ?

Il faut un relais SMTP (`etc/resource.d/notifications.cfg`), un problème en
état HARD, un contact destinataire, et ni acquittement ni downtime. Voir
[notifications](admin/17-notifications.md).

### Thruk n'affiche aucun hôte.

Le login Thruk doit être identique à un `contact_name` Shinken, contact des
objets. Voir [interface web](admin/03-interface-web.md#3-comptes-et-droits).

### Les acquittements disparaissent après un redémarrage.

Le module de rétention doit être actif sur le scheduler et le volume de
données conservé. Voir [rétention](admin/25-retention.md).

### Comment superviser l'hôte Podman lui-même ?

Les checks « locaux » mesurent le conteneur poller. Supervisez l'hôte comme
un serveur distant (SSH ou NRPE) à l'adresse `host.containers.internal`.

### Le ping ne fonctionne pas.

Le poller a besoin de la capacité `NET_RAW` (fournie avec Podman). Pour un
hôte qui filtre l'ICMP, utilisez `check_command check_tcp!<port>`.

### Puis-je garder mes fichiers de configuration Nagios ou Shinken 2.4 ?

Oui, le format est le même. Convertissez-les en UTF-8 et suivez le
[guide de migration](migration-depuis-shinken-master.md).

### Un nom de service avec parenthèses fait refuser toute la configuration.

Les caractères `` ` ~ ! $ % ^ & * " | ' < > ? , ( ) = `` sont interdits dans
les noms : `CPU (SSH)` → `CPU via SSH`.

### Comment voir la ligne de commande réellement exécutée ?

Dans Thruk, page du service (*Check Command*, avec
`show_full_commandline = 2`), ou en remplaçant les macros à la main (voir
[macros](admin/11-macros.md)).

### Comment désactiver toutes les notifications pendant une intervention globale ?

Commande externe `DISABLE_NOTIFICATIONS` (puis `ENABLE_NOTIFICATIONS`), ou
un downtime sur les hôtes concernés. Voir
[commandes externes](admin/15-checks-passifs-commandes-externes.md).

### Comment exposer l'interface sur Internet ?

Jamais directement : un reverse proxy HTTPS avec authentification devant la
page d'état ou Thruk, Livestatus restant sur `127.0.0.1`. Voir
[reverse proxy TLS](exploitation/10-reverse-proxy-tls.md).

### `shinken install` ne fonctionne pas.

Le dépôt shinken.io n'existe plus et cette commande n'est pas disponible :
les modules sont livrés avec le projet, les packs se copient à la main dans
`etc/packs/`.

### Les triggers (`etc/triggers.d`) sont-ils pris en charge ?

Le code existe (fonction héritée de Shinken) mais n'a pas été validé en
Python 3 : à éviter. Préférez une [business rule](admin/21-business-rules.md)
ou un plugin.
