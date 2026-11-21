# Groupes

**Public :** administrateur de la supervision, niveau avancé.

Les groupes servent à trois choses : **organiser** l'affichage (vues par
groupe dans Thruk), **appliquer** un service à un ensemble d'hôtes, et
**cibler** des contacts, des escalades ou des downtimes.

## Groupes d'hôtes

```
define hostgroup {
    hostgroup_name      linux
    alias               Serveurs Linux
}
```

Deux façons d'y mettre des hôtes, au choix :

- depuis l'hôte (ou mieux, depuis un modèle d'hôte) :
  `hostgroups  linux,prod` ;
- depuis le groupe : `members  srv-app-01,srv-app-02`.

Un groupe peut contenir d'autres groupes : `hostgroup_members  linux,windows`.

Appliquer un service à tout un groupe :

```
define service {
    use                     generic-service
    hostgroup_name          linux
    service_description     SSH
    check_command           check_ssh
}
```

Expressions acceptées dans `hostgroup_name` :

| Expression | Hôtes concernés |
|---|---|
| `linux,web` ou `linux\|web` | membres de `linux` **ou** de `web` |
| `linux&prod` | membres de `linux` **et** de `prod` |
| `linux&!test` | membres de `linux` qui ne sont pas dans `test` |
| `(linux\|web)&prod` | parenthèses pour grouper |
| `*` | tous les hôtes |

Exclure un hôte précis : ajoutez `host_name  !srv-test` dans le même service.

## Groupes de services

```
define servicegroup {
    servicegroup_name   services-web
    alias               Services web
    members             srv-web-01,HTTPS,srv-web-02,HTTPS
}
```

`members` liste des couples `hôte,service`. Plus simple : ajouter
`servicegroups  services-web` dans le service ou dans un modèle de service.

## Groupes de contacts

```
define contactgroup {
    contactgroup_name   dba
    alias               Administrateurs de bases de données
    members             jdupont,mmartin
}
```

ou `contactgroups  dba` dans chaque contact. Les objets désignent ensuite
leurs destinataires avec `contact_groups  admins,dba`.

## Organisation conseillée des fichiers

Shinken charge tous les `.cfg` des dossiers déclarés dans `shinken.cfg` :
l'organisation est libre. Une convention qui reste lisible à plusieurs
centaines d'hôtes :

```
etc/
├── templates/          modèles maison (serveur-linux, serveur-windows, equipement-snmp…)
├── hostgroups/         un fichier par famille de groupes
├── hosts/
│   ├── linux/          un fichier par hôte : srv-app-01.cfg
│   ├── windows/
│   └── reseau/
└── services/
    ├── par-groupe/     services appliqués par hostgroup_name
    └── specifiques/    services propres à un hôte
```

Les services communs s'appliquent par groupe ; un hôte reçoit ses services
simplement en rejoignant les bons groupes (directive `hostgroups` de son
modèle). Ajouter un serveur revient alors à écrire cinq lignes.
