# Architecture distribuée : realms, tags et daemons de secours

**Public :** administrateur de la supervision, niveau expert. Ces réglages
concernent aussi l'exploitant système (déploiement des daemons
supplémentaires, réseau).

Le déploiement fourni fait tourner un exemplaire de chaque daemon sur une
seule machine. Shinken sait répartir la charge et la supervision sur
plusieurs machines ; cette page décrit les mécanismes et leurs limites dans
cette version.

## Daemons supplémentaires : la règle de base

Chaque daemon est déclaré dans `etc/<type>s/` (`define poller { … }`) avec
son **adresse** et son **port**. L'arbiter se connecte à chacun, lui envoie
sa part de configuration et vérifie régulièrement qu'il est vivant
(`check_interval`, `timeout`, `max_check_attempts` du daemon).

```
define poller {
    poller_name         poller-dmz
    address             192.0.2.70
    port                7771
    realm               All
    poller_tags         dmz
}
```

> **Attention — sécurité.** Les daemons communiquent en HTTP **sans
> authentification**. Un daemon placé sur une autre machine doit être
> joignable **uniquement par un réseau privé** (VLAN dédié, VPN), jamais
> depuis Internet ni un réseau utilisateur. Voir
> [sécurité](../exploitation/09-securite.md).

> **Note — conteneurs.** Au démarrage, chaque conteneur adapte une copie de
> la configuration : un daemon déclaré avec l'adresse `localhost` reçoit le
> nom de son conteneur sur le réseau Podman (le rôle pour les daemons
> `<rôle>-master`, sinon son nom, par exemple `poller-2`). Une adresse
> explicite (nom ou IP) n'est jamais modifiée. Pour ajouter un daemon dans
> la même pile, nommez son service compose ou son quadlet comme le daemon.
> Voir [configuration du déploiement](../exploitation/02-configuration.md).

## Pollers et reactionners spécialisés : les tags

Un **tag** réserve des checks à certains pollers : par exemple un poller
installé dans une DMZ, seul à pouvoir joindre les machines qui s'y
trouvent.

1. Marquer les hôtes (ou services, ou commandes) concernés :

   ```
   define host {
       use             generic-host
       host_name       srv-dmz-01
       address         198.51.100.10
       poller_tag      dmz
   }
   ```

   Les services d'un hôte héritent de son `poller_tag`.

2. Déclarer un poller qui traite ce tag : `poller_tags  dmz`.

Un poller sans `poller_tags` ne traite que les objets **sans** tag (valeur
`None`). Pour qu'un poller traite les deux : `poller_tags  None,dmz`.

Les **reactionners** fonctionnent de même avec `reactionner_tag` (sur les
commandes de notification ou d'event handler, ou les objets) et
`reactionner_tags` : par exemple un reactionner qui dispose d'un modem SMS.

Un `poller_tag` peut aussi être posé sur une **commande** : tous les checks
qui l'utilisent partent vers le poller dédié (une commande qui exige un
logiciel installé sur un seul poller).

## Realms : supervision multi-sites

Un **realm** est un sous-ensemble autonome de la supervision : ses hôtes,
ses schedulers, ses pollers, ses reactionners. Cas typique : un siège et des
agences, chaque agence ayant son propre scheduler et ses pollers pour ne pas
dépendre du réseau étendu.

```
define realm {
    realm_name      All
    realm_members   Siege,Agence-Lyon
    default         1
}

define realm {
    realm_name      Agence-Lyon
}

define realm {
    realm_name      Siege
}
```

Chaque daemon et chaque hôte appartient à un realm (directive `realm`) ;
sans directive, c'est le realm `default`. L'arbiter répartit les hôtes d'un
realm entre **ses** schedulers, et un scheduler ne confie le travail qu'aux
pollers et reactionners de son realm (et des sous-realms si
`manage_sub_realms 1`).

Le broker central doit voir tous les realms : placez-le dans le realm de plus
haut niveau avec `manage_sub_realms 1` (valeur par défaut).

> **Note** — Un realm n'est pas une frontière de sécurité : tous les
> daemons restent pilotés par l'arbiter, sans authentification.

## Plusieurs schedulers

Avec plusieurs schedulers dans un realm, l'arbiter découpe les hôtes en
paquets (*packs* : un hôte et tout ce qui dépend de lui restent ensemble)
et les répartit selon le `weight` de chaque scheduler.
`pack_distribution_file` (`shinken.cfg`) garde la même répartition d'un
redémarrage à l'autre.

Chaque scheduler sauvegarde l'état de **ses** hôtes avec son propre module
de rétention : sur des machines différentes, chacun a son fichier.

## Daemons de secours (spare)

Un daemon déclaré avec `spare 1` reste inactif tant que le daemon principal
de même type répond. Si l'arbiter constate qu'un daemon est mort
(`max_check_attempts` tests de vie en échec), il confie sa configuration à
un spare du même realm.

```
define scheduler {
    scheduler_name      scheduler-secours
    address             192.0.2.71
    port                7768
    spare               1
    realm               All
}
```

Pour l'**arbiter** lui-même, un second `define arbiter` avec `spare 1` et
`host_name` égal au nom de la machine de secours ; l'arbiter de secours se
lance avec `-n <arbiter_name>` s'il ne peut pas se reconnaître par son nom
de machine.

> **Limites dans cette version.** Les spares et les daemons sur plusieurs
> machines reposent sur le code d'origine de Shinken, non modifié, mais ne
> sont pas couverts par les tests automatisés de cette version ; le
> déploiement fourni (une pile Podman sur une machine) ne les utilise pas.
> Testez la bascule avant de vous y fier. Un daemon hors conteneur
> s'installe avec le paquet Python (`pip install`) et ses fichiers
> `etc/daemons/*.ini` (voir [installation](../exploitation/01-installation.md)).

## Poller « passif »

Par défaut, le poller **va chercher** le travail auprès du scheduler
(il doit pouvoir joindre le port 7768 du scheduler). Avec `passive 1` sur le
poller, c'est le scheduler qui lui **pousse** les checks : utile quand le
poller est derrière un pare-feu qui interdit les connexions sortantes vers le
scheduler.

## Pour aller plus loin

- [Performances](24-performances.md) : dimensionner pollers et workers.
- [Architecture du code](../dev/architecture.md) : qui parle à qui, et
  comment.
