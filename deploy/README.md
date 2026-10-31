# Démarrage automatique au boot (quadlets Podman)

`podman-compose` ne relance aucun conteneur après un redémarrage de l'hôte.
Les fichiers de `deploy/quadlet/` décrivent la même pile que `compose.yaml`
sous forme d'unités systemd générées par Podman (quadlets, Podman ≥ 5.0).

## Installation (utilisateur non root)

```sh
# 1. Configuration et scripts maison dans ~/shinken (chemins utilisés par les quadlets)
mkdir -p ~/shinken
cp -a etc plugins-local ~/shinken/

# 2. Image versionnée
podman build -t localhost/shinken:2.4.3 -t localhost/shinken:latest \
    --build-arg VCS_REF=$(git rev-parse --short HEAD) .

# 3. Quadlets
mkdir -p ~/.config/containers/systemd
cp deploy/quadlet/* ~/.config/containers/systemd/
systemctl --user daemon-reload

# 4. Démarrage, et démarrage au boot sans session ouverte
systemctl --user start shinken-arbiter.service   # démarre aussi les satellites
loginctl enable-linger "$USER"
```

Les unités sont générées à partir des fichiers (`systemctl --user cat
shinken-poller.service` pour voir le résultat) : il n'y a pas de
`systemctl enable`, la section `[Install]` suffit.

## Exploitation

| Action | Commande |
|---|---|
| État | `systemctl --user status 'shinken-*'` ; `podman ps` (colonne health) |
| Logs | `journalctl --user -u shinken-scheduler -f` |
| Valider la configuration | `podman run --rm -v ~/shinken/etc:/etc/shinken:ro,z -e SHINKEN_CONTAINER_DNS=1 localhost/shinken:2.4.3 check` |
| Recharger la configuration | `systemctl --user restart shinken-arbiter` |
| Modules du broker modifiés | `systemctl --user restart shinken-broker shinken-arbiter` |
| Arrêt complet | `systemctl --user stop 'shinken-*'` |

## Adapter

- **Version de l'image** : `Image=localhost/shinken:2.4.3` dans chaque
  `.container`. Pour une mise à jour, construisez la nouvelle version, changez
  la ligne, puis `systemctl --user daemon-reload` et redémarrez les unités ;
  l'ancienne image reste disponible pour revenir en arrière.
- **Fuseau horaire** : `Environment=TZ=Europe/Paris`.
- **Chemins** : `%h/shinken/etc` et `%h/shinken/plugins-local` (`%h` = répertoire
  personnel). En root, placez les fichiers dans `/etc/containers/systemd/`
  et remplacez `%h` par un chemin absolu.
- **Ports publiés** : `PublishPort=` du broker (127.0.0.1 uniquement par défaut ;
  ne publiez jamais Livestatus sur une interface publique).
- **Daemons supplémentaires** (par exemple `poller-2`) : copiez
  `shinken-poller.container` en `shinken-poller-2.container` et mettez
  `ContainerName=shinken-poller-2` et `NetworkAlias=poller-2` : l'entrypoint
  remplace l'adresse `localhost` d'un daemon par son nom.

Le healthcheck de l'image (`shinken-healthcheck --daemon auto`) vérifie que
chaque daemon répond sur son port ; celui du broker exige aussi Livestatus.
Avec `Notify=healthy`, l'arbiter ne démarre qu'une fois les satellites sains.
