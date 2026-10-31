# Recette : équipement interrogé en SNMP

**Principe :** commutateurs, routeurs, onduleurs, imprimantes et la plupart
des équipements exposent leurs compteurs en **SNMP** (UDP 161). Le poller
les lit avec `check_snmp` (monitoring-plugins) ou les scripts du paquet
`nagios-snmp-plugins` (`check_snmp_storage.pl`, `check_snmp_int.pl`,
`check_snmp_load.pl`…).

## 1. Communauté SNMP

La configuration fournie utilise SNMP v2c. La communauté par défaut est
définie une fois, dans `etc/resource.d/snmp.cfg` :

```
$SNMPCOMMUNITYREAD$=public
```

Remplacez `public` par la communauté réelle de votre parc. Le modèle
`generic-host` la reprend dans sa macro personnalisée `_SNMPCOMMUNITY` ;
un hôte qui a une autre communauté la redéfinit :

```
define host {
    use                 generic-host
    host_name           sw-coeur-01
    address             192.0.2.20
    hostgroups          reseau
    _SNMPCOMMUNITY      communaute-site-b
}
```

Les commandes SNMP fournies utilisent `$_HOSTSNMPCOMMUNITY$`.

## 2. Commandes fournies

`etc/commands/check_snmp.cfg` et `check_snmp_storage.cfg` :

| Commande | Mesure |
|---|---|
| `check_snmp_uptime` | temps depuis le dernier redémarrage de l'agent |
| `check_snmp_oid!<OID>!<warn>!<crit>` | n'importe quelle valeur numérique |
| `check_snmp_interface!<index>` | état opérationnel d'une interface (CRITICAL si elle n'est pas *up*) |
| `check_snmp_storage!<regex>!<% warn>!<% crit>` | occupation des volumes (serveurs, NAS) |

```
define service {
    use                     generic-service
    hostgroup_name          reseau
    service_description     Uptime
    check_command           check_snmp_uptime
}

define service {
    use                     generic-service
    host_name               sw-coeur-01
    service_description     Port 24 (liaison serveur)
    check_command           check_snmp_interface!24
}
```

## 3. Trouver un OID

Depuis le poller, `snmpwalk` liste ce que l'équipement expose :

```bash
podman-compose exec poller snmpwalk -v2c -c public 192.0.2.20 1.3.6.1.2.1.2.2.1.2
```

(ici les noms des interfaces, dont l'index sert à `check_snmp_interface`).
Les OID propres à un constructeur se trouvent dans ses MIB.

## 4. SNMP v3

SNMP v3 ajoute authentification et chiffrement. Créez une commande dédiée
avec les options de `check_snmp` et des macros de ressource pour les
secrets :

```
# etc/resource.d/snmp.cfg
$SNMPV3USER$=supervision
$SNMPV3AUTHPASS$=changez-moi
$SNMPV3PRIVPASS$=changez-moi

# etc/commands/check_snmp_v3.cfg
define command {
    command_name    check_snmp_v3_oid
    command_line    $NAGIOSPLUGINSDIR$/check_snmp -H $HOSTADDRESS$ -P 3 -L authPriv -U $SNMPV3USER$ -a SHA -A $SNMPV3AUTHPASS$ -x AES -X $SNMPV3PRIVPASS$ -o $ARG1$ -w $ARG2$ -c $ARG3$
}
```

## 5. Tester

```bash
podman-compose exec poller /usr/lib/nagios/plugins/check_snmp \
    -H 192.0.2.20 -P 2c -C public -o 1.3.6.1.2.1.1.3.0
```

| Message | Cause |
|---|---|
| `Timeout: No Response from 192.0.2.20` | mauvaise communauté, ACL SNMP de l'équipement, pare-feu UDP 161 |
| `No Such Object available` | OID absent de cet équipement |

## Traps SNMP

Les *traps* (messages envoyés spontanément par l'équipement) ne sont pas
reçus directement par Shinken. Utilisez un récepteur de traps (par exemple
`snmptrapd`) qui transforme chaque trap en résultat passif
(`PROCESS_SERVICE_CHECK_RESULT`, voir
[checks passifs](../15-checks-passifs-commandes-externes.md)), sur un service
déclaré `is_volatile 1`.
