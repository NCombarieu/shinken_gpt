# Générer des services par hôte : `duplicate_foreach`

**Public :** administrateur de la supervision, niveau expert. Fonction
propre à Shinken.

Problème : chaque serveur a des disques, des interfaces ou des instances
différents. Plutôt qu'un service écrit à la main par disque et par serveur,
on décrit la liste **sur l'hôte**, et **un seul** service générique est
dupliqué pour chaque élément.

## Exemple : un service par système de fichiers

Sur l'hôte, une macro personnalisée liste les éléments et, pour chacun, ses
valeurs entre `$(` et `)$` :

```
define host {
    use             serveur-linux
    host_name       srv-bdd-01
    address         192.0.2.30
    _DISQUES        racine$(/)$, donnees$(/srv/data)$, journaux$(/var/log)$
}
```

Sur le service (souvent attaché à un modèle d'hôte ou à un groupe) :

```
define service {
    use                     generic-service
    hostgroup_name          linux
    service_description     Disque $KEY$
    duplicate_foreach       _DISQUES
    check_command           check_nrpe_args!check_disk!15%!10%!$VALUE$
}
```

Shinken crée sur `srv-bdd-01` trois services : `Disque racine`,
`Disque donnees` et `Disque journaux`, chacun avec son point de montage.
Un hôte du groupe sans macro `_DISQUES` ne reçoit aucun de ces services.

## Syntaxe

| Élément | Signification |
|---|---|
| `duplicate_foreach _NOM` | nom de la macro personnalisée de l'**hôte** qui porte la liste |
| `cle$(valeur)$` | un élément ; les éléments sont séparés par des virgules |
| `cle$(v1)$$(v2)$` | plusieurs valeurs pour un élément : `$VALUE1$`, `$VALUE2$`… |
| `cle` seule | élément sans valeur : utilise `default_value` du service |
| `$KEY$` | la clé ; utilisable dans `service_description`, `display_name`, `check_command`, `event_handler` |
| `$VALUE$` | la (première) valeur |
| `disque[1-4]` | plage de clés : `disque1` à `disque4` |

Dans `service_description`, les caractères interdits de la clé sont
remplacés par `_`.

## Seuils par élément

Avec plusieurs valeurs, chaque élément porte ses propres seuils :

```
    _DISQUES        racine$(/)$$(20%)$$(10%)$, donnees$(/srv/data)$$(10%)$$(5%)$
```

```
    check_command   check_nrpe_args!check_disk!$VALUE2$!$VALUE3$!$VALUE1$
```

## Vérifier

`shinken-arbiter -v` signale les erreurs de syntaxe de la macro (parenthèse
non fermée, valeur manquante sans `default_value`). Le nombre de services
créés apparaît dans la ligne `Checked N services`.
