# Clés des clients passifs (SSH)

`authorized_keys` de ce dossier est lu par le conteneur `passive-ssh`
(profil compose `passive`). Une ligne par machine cliente, **toujours** avec
le nom d'hôte Shinken auquel la clé est liée :

```
environment="SHINKEN_PASSIVE_HOST=srv-web01" ssh-ed25519 AAAA... srv-web01
environment="SHINKEN_PASSIVE_HOST=srv-win01" ssh-ed25519 AAAA... srv-win01
```

- Une clé sans `environment="SHINKEN_PASSIVE_HOST=..."` est refusée.
- Une clé ne peut envoyer des résultats **que** pour son hôte.
- Aucun shell n'est possible : sshd force `shinken-passive-receive`
  (`ForceCommand`), sans PTY ni redirection de port.

Ce fichier est ignoré par git. Après modification :
`podman restart shinken_passive-ssh_1`.

Procédure complète : `doc/checks/ssh-passif.md`.
