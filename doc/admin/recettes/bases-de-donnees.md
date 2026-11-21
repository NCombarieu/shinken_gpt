# Recette : bases de données

Les monitoring-plugins fournissent `check_mysql` (MySQL, MariaDB) et
`check_pgsql` (PostgreSQL). Les commandes correspondantes sont dans
`etc/commands/check_database.cfg`, avec des identifiants placés dans
`etc/resource.d/databases.cfg`.

## 1. Créer un compte de supervision

Toujours un compte **dédié**, avec le minimum de droits.

MySQL / MariaDB :

```sql
CREATE USER 'supervision'@'192.0.2.5' IDENTIFIED BY 'un-mot-de-passe-long';
-- Aucun droit sur les données : la connexion et SHOW STATUS suffisent.
-- Pour surveiller la réplication :
GRANT REPLICATION CLIENT ON *.* TO 'supervision'@'192.0.2.5';
```

PostgreSQL :

```sql
CREATE ROLE supervision LOGIN PASSWORD 'un-mot-de-passe-long';
GRANT pg_monitor TO supervision;
```

et dans `pg_hba.conf`, autoriser ce compte depuis l'adresse du serveur de
supervision uniquement.

## 2. Renseigner les identifiants

```
# etc/resource.d/databases.cfg
$MYSQLUSER$=supervision
$MYSQLPASSWORD$=un-mot-de-passe-long
$PGUSER$=supervision
$PGPASSWORD$=un-mot-de-passe-long
```

Ces macros n'apparaissent pas dans les interfaces. Elles figurent toutefois
dans la ligne de commande du plugin pendant son exécution, visible des
processus du conteneur poller : n'utilisez ce compte pour rien d'autre.

## 3. Déclarer les services

| Commande | Vérifie |
|---|---|
| `check_mysql` | connexion au serveur et indicateurs de base |
| `check_mysql_replication!<retard warn>!<retard crit>` | réplication active et retard (secondes) |
| `check_pgsql!<base>` | connexion à la base indiquée |

```
define service {
    use                     generic-service
    host_name               srv-bdd-01
    service_description     MySQL
    check_command           check_mysql
}

define service {
    use                     generic-service
    host_name               srv-bdd-02
    service_description     PostgreSQL
    check_command           check_pgsql!postgres
}
```

## 4. Tester

```bash
podman-compose exec poller /usr/lib/nagios/plugins/check_pgsql \
    -H 192.0.2.31 -l supervision -p 'un-mot-de-passe-long' -d postgres
```

## Autres bases

Pour Oracle, SQL Server ou des requêtes métier (« nombre de commandes en
attente »), écrivez un plugin qui exécute la requête et compare le résultat
à des seuils : voir [écrire un plugin](../16-ecrire-un-plugin.md). Le client
de la base devra être ajouté à une image dérivée.
