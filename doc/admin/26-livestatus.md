# Livestatus : interroger et piloter Shinken

**Public :** administrateur de la supervision, niveau expert.

Livestatus est un protocole texte simple, issu de Nagios (MK Livestatus),
pour **lire l'état** de la supervision et **envoyer des commandes**. Thruk,
`shinken-healthcheck` et de nombreux outils l'utilisent. Il est servi par le
module `livestatus` du broker.

## Configuration

`etc/modules/livestatus.cfg` :

| Paramètre | Rôle | Valeur fournie |
|---|---|---|
| `host` | adresse d'écoute | `0.0.0.0` (dans le conteneur) |
| `port` | port TCP | `50000` |
| `socket` | socket Unix supplémentaire (facultatif) | — |
| `allowed_hosts` | adresses IPv4 autorisées, séparées par des virgules (vide = toutes) | — |
| `modules` | sous-module de stockage de l'historique | `logstore-sqlite` |

Le port est publié sur l'hôte en `127.0.0.1:50000` uniquement.

### Historique : `logstore-sqlite`

Les requêtes sur la table `log` (historique des alertes, notifications, et
les rapports de disponibilité de Thruk) sont servies par le sous-module
`logstore-sqlite` (`etc/modules/logstore-sqlite.cfg`) :

| Paramètre | Rôle | Valeur fournie |
|---|---|---|
| `database_file` | base SQLite | `/var/lib/shinken/livestatus.db` |
| `max_logs_age` | durée de conservation : nombre suivi de `d` (jours), `w` (semaines), `m` (mois) ou `y` (années) | `3m` |
| `archive_path` | dossier des archives | `/var/lib/shinken/archives/` |

Le sous-module `logstore-null` n'enregistre rien (pas d'historique, pas de
rapport) : utile pour un broker secondaire ou des tests. Si `logstore-sqlite`
ne peut pas être chargé, Livestatus se rabat sur `logstore-null` et le
signale dans le journal du broker.

## Le langage (LQL)

Une requête est un bloc de lignes terminé par une **ligne vide** :

```
GET <table>
Columns: <colonne> <colonne> ...
Filter: <colonne> <opérateur> <valeur>
```

Envoi depuis le serveur :

```bash
printf 'GET hosts\nColumns: name state plugin_output\n\n' | nc 127.0.0.1 50000
```

### Tables principales

| Table | Contenu |
|---|---|
| `hosts` | hôtes : `name`, `address`, `state` (0 UP, 1 DOWN, 2 UNREACHABLE), `plugin_output`, `last_check`… |
| `services` | services : `host_name`, `description`, `state` (0 à 3), `state_type` (0 SOFT, 1 HARD), `acknowledged`, `scheduled_downtime_depth`, `latency`… |
| `hostgroups`, `servicegroups`, `contacts`, `contactgroups`, `commands`, `timeperiods` | objets de configuration |
| `downtimes`, `comments` | downtimes et commentaires en cours |
| `log` | historique (nécessite `logstore-sqlite`) |
| `status` | état global du moteur |
| `hostsbygroup`, `servicesbygroup`, `servicesbyhostgroup` | jointures avec les groupes |

### Exemples

Services en problème HARD, non acquittés, hors downtime :

```
GET services
Columns: host_name description state plugin_output
Filter: state > 0
Filter: state_type = 1
Filter: acknowledged = 0
Filter: scheduled_downtime_depth = 0
```

Nombre de services par état :

```
GET services
Stats: state = 0
Stats: state = 1
Stats: state = 2
Stats: state = 3
```

Alertes des dernières 24 heures :

```
GET log
Columns: time host_name service_description state plugin_output
Filter: class = 1
Filter: time >= 1793404800
```

(remplacez l'horodatage par `$(( $(date +%s) - 86400 ))`).

Réponse en JSON, avec les noms de colonnes :

```
GET hosts
Columns: name state
OutputFormat: json
ColumnHeaders: on
```

### Opérateurs de filtre

`=`, `!=`, `<`, `>`, `<=`, `>=`, `~` (expression régulière), `~~`
(expression régulière insensible à la casse), `=~` (égalité insensible à la
casse). Plusieurs `Filter:` se combinent en ET ; `Or: 2` combine les deux
derniers en OU, `And: 2` en ET.

### Restreindre à un utilisateur

`AuthUser: <contact_name>` limite la réponse aux objets dont ce contact est
destinataire : c'est ce que fait Thruk pour chaque utilisateur connecté.

## Envoyer une commande

```
COMMAND [<horodatage>] <NOM>;<arguments>
```

Voir [checks passifs et commandes externes](15-checks-passifs-commandes-externes.md)
et la [liste des commandes](reference/commandes-externes.md).

> **Attention** — Livestatus n'a pas d'authentification : tout client qui
> joint le port peut lire toute la supervision et envoyer n'importe quelle
> commande. Ne publiez jamais le port 50000 hors de la machine ; pour un
> accès distant, passez par un tunnel SSH. Voir
> [sécurité](../exploitation/09-securite.md).
