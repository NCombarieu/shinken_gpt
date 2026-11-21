# Macros

**Public :** administrateur de la supervision, niveau avancé.

Une macro est un nom entre `$…$` remplacé par sa valeur au moment
d'exécuter une commande. C'est ce qui permet d'écrire **une** commande de
check pour **tous** les hôtes.

```
define command {
    command_name    check_tcp
    command_line    $NAGIOSPLUGINSDIR$/check_tcp -H $HOSTADDRESS$ -p $ARG1$
}
```

Pour l'hôte `srv-web-01` (adresse `192.0.2.10`) et `check_command
check_tcp!443`, Shinken exécute
`/usr/lib/nagios/plugins/check_tcp -H 192.0.2.10 -p 443`.

## Les arguments `$ARGn$`

Dans `check_command`, tout ce qui suit le nom de la commande est découpé sur
`!` : `$ARG1$` est le premier morceau, `$ARG2$` le deuxième, etc.

```
check_command    check_local_disk!20%!10%!/var
#                                 ARG1 ARG2 ARG3
```

Pour mettre un `!` littéral dans un argument, écrivez `\!`.

## Macros standard

Les plus utilisées :

| Macro | Valeur |
|---|---|
| `$HOSTNAME$`, `$HOSTALIAS$`, `$HOSTADDRESS$` | nom, alias, adresse de l'hôte |
| `$HOSTSTATE$`, `$HOSTOUTPUT$` | état et sortie du dernier check de l'hôte |
| `$SERVICEDESC$`, `$SERVICESTATE$`, `$SERVICEOUTPUT$` | nom, état, sortie du service |
| `$SERVICESTATETYPE$`, `$SERVICEATTEMPT$` | SOFT/HARD et numéro de tentative (utiles dans un event handler) |
| `$SERVICEPERFDATA$`, `$HOSTPERFDATA$` | données de performance |
| `$CONTACTNAME$`, `$CONTACTEMAIL$`, `$CONTACTPAGER$` | contact notifié (commandes de notification) |
| `$NOTIFICATIONTYPE$` | PROBLEM, RECOVERY, ACKNOWLEDGEMENT, FLAPPINGSTART, DOWNTIMESTART… |
| `$LONGDATETIME$`, `$TIMET$` | date lisible, horodatage Unix |

La liste exhaustive, générée depuis le code, est dans la
[référence des macros](reference/macros.md).

## Macros de ressource (`$USER1$`, `$NAGIOSPLUGINSDIR$`…)

Les macros définies dans `etc/resource.d/*.cfg` sont globales. Elles servent
pour les chemins et pour les **identifiants techniques**, qui n'apparaissent
ainsi ni dans les définitions d'hôtes ni dans les interfaces :

```
# etc/resource.d/databases.cfg
$MYSQLUSER$=supervision
$MYSQLPASSWORD$=un-mot-de-passe-long
```

Macros de chemins fournies (`etc/resource.d/paths.cfg`) :

| Macro | Dossier (dans les conteneurs) | Contenu |
|---|---|---|
| `$NAGIOSPLUGINSDIR$` et son alias historique `$USER1$` | `/usr/lib/nagios/plugins` | plugins standard (paquet `monitoring-plugins`, `check_nrpe`, scripts SNMP) |
| `$PLUGINSDIR$` | `/usr/local/lib/shinken/libexec` | scripts fournis par Shinken (notification par e-mail…) |
| `$LOCALPLUGINSDIR$` | `/usr/local/lib/shinken/plugins-local` | **vos** scripts, déposés dans `plugins-local/` (voir [écrire un plugin](16-ecrire-un-plugin.md)) |

Une configuration Nagios ou Shinken existante qui utilise `$USER1$`
fonctionne sans modification.

## Macros personnalisées (`_VARIABLE`)

Toute directive dont le nom commence par `_` dans un hôte, un service ou un
contact crée une **macro personnalisée** :

| Défini dans | Directive | Macro |
|---|---|---|
| un hôte | `_SNMPCOMMUNITY  monsecret` | `$_HOSTSNMPCOMMUNITY$` |
| un service | `_SEUIL_WARN  80` | `$_SERVICESEUIL_WARN$` |
| un contact | `_TELEPHONE  +33100000000` | `$_CONTACTTELEPHONE$` |

Les macros personnalisées s'héritent par les modèles, ce qui permet une
valeur par défaut redéfinie au cas par cas. C'est ce que fait la
configuration fournie pour la communauté SNMP :

```
# etc/templates/generic-host.cfg
    _SNMPCOMMUNITY      $SNMPCOMMUNITYREAD$      ; valeur par défaut (resource.d)

# un hôte particulier
    _SNMPCOMMUNITY      communaute-du-site-b

# la commande
    command_line   ... -C $_HOSTSNMPCOMMUNITY$
```

Les macros sont résolues récursivement : une macro personnalisée peut
contenir une macro de ressource, comme ci-dessus.

Usage typique : seuils propres à un hôte, sans multiplier les commandes :

```
define host {
    use             serveur-linux
    host_name       srv-bdd-01
    address         192.0.2.30
    _DISK_WARN      10%
    _DISK_CRIT      5%
}

define service {
    use                     generic-service
    hostgroup_name          linux
    service_description     Disque racine
    check_command           check_nrpe_args!check_disk!$_HOSTDISK_WARN$!$_HOSTDISK_CRIT$!/
}
```

## Macros « à la demande »

On peut lire la valeur d'un **autre** objet en ajoutant son nom :
`$HOSTSTATE:srv-bdd-01$`, `$SERVICESTATE:srv-bdd-01:MySQL$`. Utile dans un
message de notification ou un event handler.

## Points d'attention

- Une macro inconnue (faute de frappe, macro personnalisée absente) est
  remplacée par une **chaîne vide**, sans erreur : le plugin reçoit alors un
  argument manquant. Vérifiez la ligne finale dans Thruk (page du service,
  *Check Command*) ou en lançant la commande à la main (voir
  [écrire un plugin](16-ecrire-un-plugin.md)).
- `$$` produit un `$` littéral.
- Les caractères listés dans `illegal_macro_output_chars` (`shinken.cfg`,
  vide par défaut) sont retirés des macros de sortie (`$SERVICEOUTPUT$`…)
  avant leur usage dans une commande. Renseignez-la (par exemple
  `` illegal_macro_output_chars=`~$&|'"<> ``) si des sorties de plugins sont
  réinjectées dans des commandes shell.
- `enable_environment_macros=0` (par défaut) : les macros ne sont **pas**
  exportées en variables d'environnement vers les plugins.
