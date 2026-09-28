# Certificats NRPE/TLS

`etc/` est monté à `/etc/shinken` dans **tous** les containers (bind-mount,
voir `compose.yaml`). Un fichier posé ici sous `etc/certs/` est donc
immédiatement visible à `/etc/shinken/certs/` dans le poller, sans
rebuild — juste un `podman restart shinken_arbiter_1` pour recharger la
config qui les référence.

Exemple (`shinken-explorer/sample_config/12-commands.cfg`) :

```
define command {
    command_name    check_nrpe_ssl
    command_line    $PLUGINSDIR$/check_nrpe -H $HOSTADDRESS$ -c $ARG1$ -2 -t 30 \
                     --ssl-version=TLSv1.2+ \
                     -K /etc/shinken/certs/shinken-server.key \
                     -C /etc/shinken/certs/shinken-server.crt \
                     -A /etc/shinken/certs/ca.crt
}
```

Il suffit de déposer `shinken-server.key`, `shinken-server.crt` et
`ca.crt` ici pour que cette commande fonctionne (le binaire `check_nrpe`
est installé depuis le paquet `nagios-nrpe-plugin`).

Ne pas committer de vraies clés privées/certs en clair dans ce repo git
public — utiliser un `.gitignore` local ou un volume séparé pour la
prod.
