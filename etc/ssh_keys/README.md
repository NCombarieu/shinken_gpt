# Clés SSH pour les checks actifs (check_by_ssh)

Déposer ici la clé **privée** dédiée à la supervision (par exemple
`shinken_monitoring`) et, de préférence, un fichier `known_hosts`.
Le dossier est monté en lecture seule dans `/etc/shinken/ssh_keys/`.

Au démarrage, le poller :

1. copie chaque clé privée lisible vers un répertoire privé, en `0600` ;
2. génère la configuration du client ssh (clés, `known_hosts`, `BatchMode`),
   donc les commandes n'ont pas besoin de `-i` ;
3. sans `known_hosts` ici, accepte la clé d'un serveur à la première
   connexion et la mémorise (`/var/lib/shinken/ssh_known_hosts`).

Une seule étape côté hôte Podman, **une fois** : rendre la clé lisible par
l'utilisateur du conteneur (uid 10001) :

```
podman unshare chown 10001:10001 etc/ssh_keys/shinken_monitoring
```

Si la clé n'est pas lisible, le poller l'écrit dans ses logs
(`podman logs shinken_poller_1 | grep "SSH key"`).

Côté machine supervisée : `contrib/checks/ssh/shinken-checks`.
Procédure complète : `doc/checks/ssh-actif.md`.

Ne jamais committer de vraie clé privée : `etc/ssh_keys/*` est ignoré par git.
