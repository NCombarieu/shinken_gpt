# Clefs SSH pour check_by_ssh

Meme principe que `etc/certs/` : deposer une clef privee ici la rend
disponible a `/etc/shinken/ssh_keys/` dans le poller, sans rebuild.

Exemple de commande (a adapter, pas definie par defaut dans ce repo) :

```
define command {
    command_name    check_by_ssh_uptime
    command_line    $NAGIOSPLUGINSDIR$/check_by_ssh -H $HOSTADDRESS$ \
                     -i /etc/shinken/ssh_keys/id_monitoring \
                     -l monitoring -C "uptime"
}
```

Ne pas committer de vraie clef privee en clair dans ce repo git public.
