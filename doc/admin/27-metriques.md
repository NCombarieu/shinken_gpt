# Métriques et graphiques

**Public :** administrateur de la supervision, niveau expert.

Deux sortes de métriques sont à distinguer.

## 1. Les données de performance des checks (perfdata)

Ce sont les mesures renvoyées par les plugins après le `|`
(`'temps'=0.12s;1;3;0;`, voir [écrire un plugin](16-ecrire-un-plugin.md)).
Shinken les transmet au broker avec chaque résultat
(`process_perf_data 1`, actif dans les modèles fournis).

**État dans cette version :**

- elles sont visibles dans Thruk (*Performance Data*) et interrogeables par
  Livestatus (colonne `perf_data`) ;
- **aucun module n'exporte l'historique des perfdata** vers une base de
  séries temporelles (Graphite, InfluxDB…). Les modules historiques de
  Shinken pour cela (`graphite`, `influxdb`) n'ont pas été portés en
  Python 3 ;
- le profil `experimental-metrics` de `compose.yaml` démarre InfluxDB et
  Grafana mais **rien ne les alimente** : c'est un chantier, pas une
  fonction disponible. Ses identifiants par défaut sont des exemples.

**Solutions possibles aujourd'hui :**

| Solution | Principe |
|---|---|
| Interrogation périodique de Livestatus | un script lit `GET services` / `Columns: host_name description perf_data last_check` toutes les minutes et écrit les valeurs dans votre base de séries temporelles. |
| Thruk + greffon de graphiques | certaines distributions de Thruk intègrent un grapheur alimenté par les perfdata ; il faut alors lui fournir les données par l'une des méthodes ci-dessus. |
| Module broker | un module Python (voir [écrire un module](../dev/ecrire-un-module.md)) qui reçoit les broks `service_check_result` et écrit dans la base. C'est la solution propre, à développer. |

## 2. Les métriques internes de Shinken

Le fonctionnement des daemons eux-mêmes (files d'attente, temps de
traitement, nombre d'objets) peut être envoyé à un serveur **StatsD**
(UDP) :

```
# etc/shinken.cfg
statsd_enabled=1
statsd_host=statsd.example.com
statsd_port=8125
statsd_prefix=shinken
```

Ces métriques servent à surveiller la santé de Shinken (voir
[surveiller Shinken](../exploitation/07-surveiller-shinken.md) et
[performances](24-performances.md)), pas l'état des hôtes supervisés.
