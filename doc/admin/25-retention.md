# Rétention de l'état

**Public :** administrateur de la supervision et exploitant, niveau expert.

## Ce qui est conservé

Le scheduler garde en mémoire l'état vivant de la supervision : états
courants (et SOFT/HARD), acquittements, downtimes, commentaires, historique
de flapping, prochaines notifications. Sans rétention, tout cela serait
perdu à chaque redémarrage du scheduler **et à chaque rechargement de la
configuration** (qui renvoie une configuration neuve au scheduler) : les
downtimes disparaîtraient et les problèmes acquittés seraient renotifiés.

## Le module `retention-pickle`

La configuration fournie active le module `retention-pickle` sur le
scheduler (`etc/schedulers/scheduler-master.cfg`, ligne `modules`). Il est
défini dans `etc/modules/` :

```
define module {
    module_name     retention-pickle
    module_type     pickle_retention_file
    path            /var/lib/shinken/retention.dat
}
```

| Moment | Action |
|---|---|
| démarrage du scheduler, réception d'une configuration | lecture de `retention.dat` et restauration de l'état des objets qui existent toujours |
| toutes les `retention_update_interval` minutes (`shinken.cfg`, 60) | sauvegarde |
| arrêt propre du scheduler | sauvegarde |

L'écriture est **atomique** (fichier temporaire puis renommage) : un arrêt
brutal pendant la sauvegarde ne corrompt pas le fichier précédent.

Le fichier est dans le volume de données (`/var/lib/shinken`), conservé lors
des recréations de conteneurs. Il fait partie de la
[sauvegarde](../exploitation/05-sauvegarde-restauration.md).

## Rechargement de la configuration

Un objet **renommé** est un nouvel objet pour Shinken : son état,
ses acquittements et ses downtimes ne sont pas repris. Un objet supprimé
perd son état. Les autres sont restaurés à l'identique.

## Reprise d'un fichier de Shinken 2.4 (Python 2)

Le module sait relire un `retention.dat` produit par Shinken master
(Python 2) : il suffit de le copier dans le volume, conteneurs arrêtés,
avant le premier démarrage. Procédure complète dans le
[guide de migration](../migration-depuis-shinken-master.md).

## Vérifier que la rétention fonctionne

1. Poser un downtime sur un service (voir
   [la page dédiée](04-acquitter-et-planifier-un-downtime.md)).
2. Redémarrer le scheduler : `podman-compose restart scheduler`.
3. Après quelques secondes, le downtime est toujours visible dans Thruk.

Le journal du scheduler (`podman-compose logs scheduler`) indique le
chargement et les sauvegardes de la rétention.
