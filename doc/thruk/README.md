# Thruk : l'interface web de Shinken

**Public :** exploitant système et administrateur de la supervision.

Shinken n'a pas d'interface web complète. On lui adjoint
[Thruk](https://www.thruk.org), une interface compatible Nagios qui lit
l'état et envoie les commandes par le protocole **Livestatus**, servi par
le module `livestatus` du broker. Cette partie décrit une installation de
Thruk **en conteneur**, à côté des conteneurs Shinken, telle qu'elle est
utilisée en production avec ce fork.

```
 navigateur ──HTTPS──► reverse proxy (Caddy, nginx…)
                          │  127.0.0.1:8443
                          ▼
              ┌──────── conteneur omd-thruk ────────┐
              │ Apache système :443 (TLS local)     │
              │   └► Apache du site OMD :5000       │
              │        └► Thruk (comptes, droits)   │
              └───────────────┬─────────────────────┘
                              │ Livestatus, TCP broker:50000
                              │ (réseau Podman partagé)
              ┌───────────────▼─────────────────────┐
              │ conteneur shinken-broker            │
              │   module livestatus ◄── broks ◄── scheduler…
              └─────────────────────────────────────┘
```

| Page | Contenu |
|---|---|
| [1. Le conteneur Thruk](01-conteneur.md) | image OMD Labs, site, volumes, ports, démarrage, playbook drop-in, mise à jour |
| [2. Connecter Thruk à Shinken](02-connexion-livestatus.md) | réseau Podman, déclaration du backend, tests, plusieurs Shinken |
| [3. Comptes et droits](03-comptes-et-droits.md) | comptes Thruk, correspondance avec les contacts Shinken, rôles, administrateurs |
| [4. Exposition et dépannage](04-exposition-et-depannage.md) | reverse proxy, en-têtes, accès de secours, problèmes connus |

## Ce qu'il faut retenir

1. Thruk et le broker doivent être sur **le même réseau Podman**, choisi
   **à la création** du conteneur Thruk.
2. Le backend Thruk pointe sur **`broker:50000`** (nom du conteneur ou de
   son alias sur ce réseau).
3. Un login Thruk ne voit que les objets dont il est **contact Shinken** :
   même nom, sinon l'interface est vide.
4. Les droits d'administration Thruk (`authorized_for_admin`…) sont
   distincts des contacts Shinken.
5. Derrière un reverse proxy : **une seule** authentification (celle de
   Thruk), et les en-têtes `X-Forwarded-Port` / `X-Forwarded-Proto`.

Pour la lecture des pages de Thruk au quotidien (vues, détail d'un service,
actions), voir [lire l'interface web](../admin/03-interface-web.md). Pour le
protocole lui-même : [Livestatus](../admin/26-livestatus.md).
