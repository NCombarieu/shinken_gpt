# Périodes de temps

**Public :** administrateur de la supervision, niveau avancé.

Une période (`define timeperiod`) décrit des plages horaires. Elle est
utilisée par `check_period`, `notification_period`, `maintenance_period`,
`escalation_period`, `dependency_period` et les périodes des contacts.

Les heures sont interprétées dans le **fuseau horaire des daemons** : la
variable `TZ` du déploiement (par défaut `Europe/Paris`, voir
[configuration du déploiement](../exploitation/02-configuration.md)).

## Syntaxe

```
define timeperiod {
    timeperiod_name     astreinte
    alias               Hors heures ouvrées
    monday              00:00-09:00,18:00-24:00
    tuesday             00:00-09:00,18:00-24:00
    wednesday           00:00-09:00,18:00-24:00
    thursday            00:00-09:00,18:00-24:00
    friday              00:00-09:00,18:00-24:00
    saturday            00:00-24:00
    sunday              00:00-24:00
}
```

Chaque ligne associe un **jour ou une date** à une ou plusieurs **plages**
`HH:MM-HH:MM` séparées par des virgules. `24:00` désigne la fin de journée.
Les noms de jours et de mois s'écrivent en anglais.

| Forme | Exemple | Signification |
|---|---|---|
| jour de la semaine | `monday 09:00-18:00` | chaque lundi |
| date fixe chaque année | `july 14 00:00-24:00` | chaque 14 juillet |
| date précise | `2027-03-29 00:00-24:00` | une seule fois |
| jour du mois | `day 1 00:00-06:00` | le 1er de chaque mois ; `day -1` = dernier jour |
| n-ième jour de la semaine du mois | `monday 1 september 00:00-24:00` | premier lundi de septembre ; `-1` = dernier |
| intervalle de dates | `december 24 - january 2 00:00-24:00` | du 24 décembre au 2 janvier |

> **Attention** — Une date précise (`2027-03-29`) ne vaut que pour cette
> année : mettez-la à jour chaque année (jours fériés mobiles).

## Exclusions

`exclude` retire d'autres périodes. C'est la façon de gérer les jours fériés :

```
define timeperiod {
    timeperiod_name     workhours
    alias               Heures ouvrées
    monday              09:00-18:00
    tuesday             09:00-18:00
    wednesday           09:00-18:00
    thursday            09:00-18:00
    friday              09:00-18:00
    exclude             jours-feries-fr
}
```

La période `jours-feries-fr` fournie (`etc/timeperiods/jours-feries-fr.cfg`)
contient les jours fériés français à date fixe ; ajoutez-y chaque année
lundi de Pâques, Ascension et lundi de Pentecôte sous forme de dates
précises.

## Périodes fournies

| Nom | Contenu |
|---|---|
| `24x7` | en permanence |
| `workhours` | du lundi au vendredi, 9 h - 18 h, hors jours fériés |
| `jours-feries-fr` | jours fériés français à date fixe (à exclure, pas à utiliser seule) |
| `none` | jamais (désactive une notification sans supprimer sa définition) |

## Vérifier une période

`shinken-arbiter -v` signale les lignes non reconnues. Dans Thruk, la page
*Configuration → Time Periods* affiche les périodes chargées.
