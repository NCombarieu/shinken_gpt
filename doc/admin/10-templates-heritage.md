# Modèles et héritage

**Public :** administrateur de la supervision, niveau avancé.

Les modèles (*templates*) évitent de répéter les mêmes directives dans des
centaines d'objets. Tout type d'objet (hôte, service, contact…) peut servir
de modèle.

## Définir et utiliser un modèle

Un modèle est un objet avec un `name` et `register 0` (il n'est pas
instancié, il sert seulement de source) :

```
define host {
    name                    serveur-linux
    use                     generic-host
    check_command           check_tcp!22
    hostgroups              linux
    notification_period     workhours
    register                0
}

define host {
    use                     serveur-linux
    host_name               srv-app-01
    address                 192.0.2.11
}
```

`srv-app-01` hérite de toutes les directives de `serveur-linux`, qui hérite
lui-même de `generic-host`. Une directive écrite dans l'objet l'emporte
toujours sur celle du modèle.

> **Note** — `name` (nom du modèle) et `host_name` (nom de l'hôte) sont deux
> choses distinctes. Un objet peut avoir les deux : il est alors à la fois un
> hôte réel et un modèle.

## Héritage multiple

`use` accepte plusieurs modèles séparés par des virgules. **Le premier
cité est prioritaire** : pour une directive définie dans plusieurs modèles,
c'est la valeur du plus à gauche qui est retenue.

```
define service {
    use                     5min_long,generic-service
    host_name               srv-app-01
    service_description     Charge
    check_command           check_nrpe!check_load
}
```

Ici `max_check_attempts` vient de `5min_long` (6) et non de
`generic-service` (3).

Bonne pratique : des petits modèles spécialisés (fréquence, période,
groupe de contacts) combinés à un modèle de base, plutôt qu'une hiérarchie
profonde difficile à lire.

## Héritage additif (`+`)

Par défaut, une directive de type liste écrite dans l'objet **remplace**
celle du modèle. Préfixée par `+`, elle **s'ajoute** à la valeur héritée :

```
define host {
    name                    serveur-critique
    contact_groups          admins
    register                0
}

define host {
    use                     serveur-critique
    host_name               srv-bdd-01
    address                 192.0.2.30
    contact_groups          +dba
}
```

`srv-bdd-01` a pour groupes de contacts `admins,dba`.

## Annuler une valeur héritée (`null`)

La valeur spéciale `null` efface une directive héritée et rétablit la valeur
par défaut :

```
    event_handler           null
```

## Héritage implicite hôte → service

Quelques directives d'un service non renseignées sont reprises de son hôte :
`contacts`, `contact_groups`, `notification_interval`,
`notification_period`, `resultmodulations`, `business_impact_modulations`,
`escalations`, `poller_tag`, `reactionner_tag`, `check_period`,
`business_impact`, `maintenance_period`. Ainsi, pour notifier une autre
équipe pour tous les services d'un hôte, il suffit de régler
`contact_groups` sur l'hôte… à condition que les services ne le redéfinissent
pas eux-mêmes (ce que fait `generic-service`).

## Appliquer un service à plusieurs hôtes

Un même service peut être défini une seule fois pour plusieurs hôtes :

```
define service {
    use                     generic-service
    hostgroup_name          linux
    service_description     SSH
    check_command           check_ssh
}
```

Tous les hôtes du groupe `linux` reçoivent ce service. On peut aussi :

- lister des hôtes : `host_name  srv-a,srv-b` ;
- exclure un hôte du groupe : `hostgroup_name  linux` **et**
  `host_name  !srv-test` dans le même service ;
- combiner des groupes : `hostgroup_name  linux&prod` (intersection),
  `linux|windows` (union), `linux&!test` (différence).

Voir [groupes](12-groupes.md).

## Services attachés à un modèle d'hôte

Un service peut être rattaché à un **modèle** d'hôte : tous les hôtes qui
utilisent ce modèle le reçoivent.

```
define service {
    use                     generic-service
    host_name               serveur-linux
    service_description     Disque racine
    check_command           check_nrpe!check_disk_root
    register                0
}
```

Le `register 0` est obligatoire ici ; sans lui, Shinken chercherait un hôte
réel nommé `serveur-linux`. Pour retirer un tel service d'un hôte précis :
`service_excludes  Disque racine` dans l'hôte.

## Vérifier le résultat

`shinken-arbiter -v` signale les modèles introuvables et les boucles
d'héritage. Pour voir les valeurs finales d'un objet, consultez sa page de
détail dans Thruk ou interrogez Livestatus
(`GET services` avec `Columns:`, voir [Livestatus](26-livestatus.md)).
