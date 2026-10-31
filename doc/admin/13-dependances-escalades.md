# Dépendances et escalades

**Public :** administrateur de la supervision, niveau avancé.

## Pourquoi des dépendances

Quand le routeur d'un site tombe, tous les serveurs derrière lui deviennent
injoignables. Sans dépendances, vous recevez une alerte par serveur et par
service. Avec des dépendances, Shinken comprend que la **cause** est le
routeur et que le reste n'est qu'un **impact** : une seule alerte utile.

## Parents (topologie réseau)

```
define host {
    use             generic-host
    host_name       rt-site-b
    address         192.0.2.1
}

define host {
    use             generic-host
    host_name       srv-site-b-01
    address         192.0.2.40
    parents         rt-site-b
}
```

Si `srv-site-b-01` ne répond plus **et** que tous ses parents sont DOWN, il
passe en **UNREACHABLE** au lieu de DOWN. Les contacts ne reçoivent une
notification UNREACHABLE que si `u` figure dans `notification_options` ;
retirez `u` pour ne recevoir que l'alerte du routeur.

Avec `enable_problem_impacts_states_change=1` (`shinken.cfg`, activé dans la
configuration fournie), les éléments impactés changent immédiatement d'état
(hôtes en UNREACHABLE, services en UNKNOWN) sans attendre leur propre check.

## Dépendance de service simple

Dans le service dépendant :

```
define service {
    use                     generic-service
    host_name               srv-app-01
    service_description     Application
    check_command           check_http!/sante
    service_dependencies    srv-bdd-01,MySQL
}
```

Tant que `MySQL` sur `srv-bdd-01` est en problème, `Application` ne notifie
pas. Plusieurs dépendances : `srv-bdd-01,MySQL,srv-cache-01,Redis`. Pour
dépendre d'un service du même hôte, laissez le nom d'hôte vide :
`,MySQL`.

Par défaut, chaque service dépend aussi de **son hôte** : un service n'est
pas notifié si son hôte est DOWN (`host_dependency_enabled 1`).

## Objets de dépendance

Pour un contrôle fin (états concernés, période), utilisez les objets
`servicedependency` et `hostdependency` (exemples commentés dans
`etc/dependencies/sample.cfg`) :

```
define servicedependency {
    host_name                       srv-bdd-01
    service_description             MySQL
    dependent_host_name             srv-app-01
    dependent_service_description   Application
    execution_failure_criteria      c,u
    notification_failure_criteria   c,u
    dependency_period               24x7
}
```

| Directive | Effet quand le maître est dans l'un des états listés |
|---|---|
| `execution_failure_criteria` | les checks du dépendant sont suspendus |
| `notification_failure_criteria` | les notifications du dépendant sont suspendues |

États : `o` OK/UP, `w` WARNING, `c` CRITICAL, `u` UNKNOWN (service) ou
UNREACHABLE (hôte), `d` DOWN, `p` PENDING, `n` aucun.

## Escalades

Une escalade ajoute des destinataires quand un problème dure : par exemple
l'astreinte, puis le responsable.

### Forme Nagios : par numéro de notification

```
define serviceescalation {
    host_name               srv-web-01
    service_description     HTTPS
    contact_groups          astreinte
    first_notification      3
    last_notification       5
    notification_interval   30
    escalation_period       24x7
    escalation_options      w,u,c,r
}
```

De la 3e à la 5e notification, le groupe `astreinte` est aussi prévenu, et
les rappels passent à 30 minutes. `last_notification 0` = sans fin.
`hostescalation` fonctionne de même pour les hôtes.

### Forme Shinken : par durée, réutilisable

```
define escalation {
    escalation_name             vers-astreinte-1h
    first_notification_time     60
    last_notification_time      0
    notification_interval       30
    contact_groups              astreinte
}
```

Puis, dans un hôte, un service ou un modèle : `escalations
vers-astreinte-1h`. L'escalade s'applique après 60 minutes de problème,
quel que soit le nombre de notifications déjà envoyées : la règle reste vraie
même si vous changez `notification_interval`.

## Vérifier

`shinken-arbiter -v` signale les dépendances vers des objets inexistants et
les boucles de dépendance. Dans Thruk, la page d'un hôte affiche ses parents
et les éléments impactés.
