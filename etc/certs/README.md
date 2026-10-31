# Certificats

Ce dossier est monté dans les conteneurs sur `/etc/shinken/certs/`. Il ne
contient aucun certificat : **ne versionnez jamais de clé privée**. Déposez
ici vos propres fichiers, générés sur le serveur de supervision.

## Générer une petite autorité de certification

Pour chiffrer les échanges entre daemons (`use_ssl=1`) ou authentifier le
poller auprès des agents NRPE, il faut une autorité (CA) et un certificat
par usage. Exemple avec `openssl`, depuis la racine du dépôt :

```bash
cd etc/certs
# Autorité (à conserver hors du serveur une fois les certificats signés)
openssl req -x509 -newkey rsa:4096 -sha256 -days 3650 -nodes \
    -keyout ca.key -out ca.pem -subj "/CN=Supervision CA"
# Certificat d'un daemon ou du client NRPE
openssl req -newkey rsa:2048 -sha256 -nodes \
    -keyout server.key -out server.csr -subj "/CN=shinken.example.com"
openssl x509 -req -in server.csr -CA ca.pem -CAkey ca.key -CAcreateserial \
    -days 825 -sha256 -out server.cert
rm server.csr
```

Puis rendez les clés lisibles par l'utilisateur des conteneurs uniquement
(Podman rootless) :

```bash
podman unshare chown 10001:10001 server.key
podman unshare chmod 600 server.key
```

Les chemins attendus par défaut dans `shinken.cfg` et `daemons/*.ini` sont
`/etc/shinken/certs/ca.pem`, `server.cert` et `server.key`. Voir
[doc/exploitation/09-securite.md](../../doc/exploitation/09-securite.md) :
le chiffrement natif entre daemons n'est pas couvert par les tests de cette
version ; la protection recommandée reste un réseau privé.

## Certificats NRPE (TLS client)

Pour un agent NRPE 4 qui exige un certificat client, déposez par exemple
`nrpe-client.key`, `nrpe-client.crt` et `ca.crt`, puis déclarez une commande
dédiée :

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
