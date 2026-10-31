# Secrets pour les checks (jetons d API...)

Fichiers lus par les commandes de `etc/commands/check_api.cfg` (`--token-file`).
Ignore par git. Le poller tourne en uid 10001 : rendre le fichier lisible
(`podman unshare chown 10001:10001 fichier` puis `chmod 600`).
Voir doc/checks/api.md.
