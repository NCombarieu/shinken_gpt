# Configuration Shinken pour la pile conteneurisée

Fragments à déposer dans l'arborescence `/etc/shinken` montée dans le conteneur
`shinken-arbiter` (volume `conf` de l'application `shinken` dans
puppet-containers). Ils remplacent les fichiers de même nom de `etc/` :

| Fichier | Rôle |
|---|---|
| `arbiters/`, `schedulers/`, `pollers/`, `brokers/`, `reactionners/`, `receivers/` | un démon par conteneur, joint par son **alias DNS** sur le réseau Podman |
| `modules/livestatus.cfg` | module broker Livestatus, port 50000, consommé par Thruk sur le réseau interne |
| `realms/all.cfg` | realm unique `All` |

Le reste (`shinken.cfg`, `commands/`, `hosts/`, `packs/`, `resource.d/`…) vient
de `etc/` du dépôt, puis de la configuration du site. `shinken.cfg` doit
contenir `cfg_dir=modules` et `cfg_dir=realms`, ce qui est le cas du modèle
`etc/shinken.cfg.in`.

Les alias (`scheduler`, `poller`, `broker`…) sont ceux posés par
`containers.<nom>.aliases` dans le Hiera de puppet-containers
(`examples/stack-supervision/hiera_node.yaml`). Changer l'un impose de changer
l'autre.
