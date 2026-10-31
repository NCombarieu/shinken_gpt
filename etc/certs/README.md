# Certificats

Ce dossier est monté dans les conteneurs sur `/etc/shinken/certs/`.

## Certificats de démonstration : ne pas utiliser

Les fichiers `ca.pem`, `server.cert`, `server.key`, `private/cakey.pem` et
associés proviennent du projet Shinken d'origine. Ils servent uniquement aux
tests automatisés (`test/`). Leur clé privée est **publique** et ils sont
**expirés** : ne les utilisez ni pour chiffrer les échanges entre daemons
(`use_ssl=1`), ni pour NRPE.

## Certificats NRPE (TLS client)

Pour un agent NRPE 4 qui exige un certificat client, déposez ici vos propres
fichiers (non versionnés), par exemple `nrpe-client.key`, `nrpe-client.crt` et
`ca.crt`, puis déclarez une commande dédiée :

```
define command {
    command_name    check_nrpe_tls
    command_line    $NAGIOSPLUGINSDIR$/check_nrpe -H $HOSTADDRESS$ -t 9 -u -c $ARG1$ \
                    -K /etc/shinken/certs/nrpe-client.key \
                    -C /etc/shinken/certs/nrpe-client.crt \
                    -A /etc/shinken/certs/ca.crt
}
```

Voir [doc/admin/recettes/linux-nrpe.md](../../doc/admin/recettes/linux-nrpe.md).
