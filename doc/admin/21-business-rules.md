# Business rules : superviser un service métier

**Public :** administrateur de la supervision, niveau expert. Fonction
propre à Shinken (absente de Nagios).

Une *business rule* calcule l'état d'un service à partir de l'état d'autres
hôtes et services, avec des opérateurs logiques. Elle répond à la question
métier : « le site de commande en ligne fonctionne-t-il ? » plutôt que « le
serveur web n° 2 est-il en panne ? ».

## Exemple

Le site fonctionne si au moins un des deux frontaux web répond **et** que la
base de données répond :

```
define host {
    use                 generic-host
    host_name           metier
    alias               Services métier
    address             127.0.0.1
    check_command       check_dummy!0!Hôte logique des services métier
}

define service {
    use                     generic-service
    host_name               metier
    service_description     Commande en ligne
    check_command           bp_rule!(srv-web-01,HTTPS | srv-web-02,HTTPS) & srv-bdd-01,MySQL
    business_impact         5
}
```

`bp_rule` est une commande interne : rien n'est exécuté par un poller,
l'état est calculé par le scheduler à partir de l'état **HARD** des
éléments (un élément en état SOFT n'est pas encore pris en compte).

## Syntaxe

| Élément | Signification |
|---|---|
| `hôte,service` | l'état d'un service |
| `hôte` | l'état d'un hôte (UP = OK, DOWN = CRITICAL) |
| `A & B` | ET : l'état le **plus grave** des deux |
| `A \| B` | OU : l'état le **moins grave** des deux |
| `!A` | NON : inverse OK et CRITICAL (WARNING reste WARNING) |
| `( … )` | regroupement |
| `N of: A,B,C` | OK si au moins N éléments sont OK (ex. `2 of: srv-a,HTTP,srv-b,HTTP,srv-c,HTTP`) |
| `N% of: …` | idem en pourcentage |
| `O,W,C of: …` | trois seuils : O éléments OK pour être OK, W éléments en problème pour passer WARNING, C éléments CRITICAL pour passer CRITICAL (ex. `3,1,2 of: …`) |

### Sélection d'éléments par groupe, motif ou étiquette

Un préfixe permet de viser un ensemble d'éléments :

| Préfixe | Exemple | Éléments |
|---|---|---|
| `g:` | `g:web,HTTPS` | le service HTTPS de tous les hôtes du groupe `web` |
| `r:` | `r:^srv-web-[0-9]+,HTTPS` | les hôtes dont le nom correspond à l'expression régulière |
| `l:` | `l:prod,HTTPS` | les hôtes portant l'étiquette `prod` (directive `labels`) |
| `t:` | `t:serveur-linux,HTTPS` | les hôtes qui héritent du modèle `serveur-linux` (les « tags » d'un objet sont ses modèles) |

Exemple : « au moins 2 frontaux sur l'ensemble du groupe `web` » :
`bp_rule!2 of: g:web,HTTPS`.

## Notifications des business rules

Le service métier notifie comme tout service. Directives utiles :

| Directive | Effet |
|---|---|
| `business_rule_smart_notifications 1` | pas de notification si tous les éléments en panne sont déjà acquittés ou en downtime |
| `business_rule_downtime_as_ack 1` | un élément en downtime compte comme acquitté |
| `business_rule_output_template` | modèle du texte de sortie ; la partie entre `$(` et `)$` est répétée pour chaque élément en problème, par exemple `$STATUS$ $([$STATUS$: $HOSTNAME$,$SERVICEDESC$] )$` |

Contactez l'équipe métier sur le service métier, et l'équipe technique sur
les éléments : chacun reçoit l'alerte qui le concerne.

## Impacts et causes

Avec une business rule, Shinken relie les problèmes techniques (causes) aux
services métier touchés (impacts). Dans Thruk, la page d'un service métier
montre les éléments qui le composent. Le `business_impact` (0 à 5) des
services métier permet aussi de trier les problèmes par importance, et de
filtrer les notifications (`min_business_impact` des contacts).
