---
title: "Installer et lancer Shinken"
domain: "Shinken"
type: "procedure"
level: "debutant"
duration: "20 min"
version: "1.0"
updated: "2026-09-13"
owner: "Administration Supervision"
status: "valid"
order: 3
action: "Mettre Shinken en service sur un serveur"
keywords: [installation, podman, podman-compose, containerfile, mise en service]
summary: "Cloner le dépôt, construire l'image et lancer les six daemons Shinken avec Podman."
---

# Installer et lancer Shinken

## Objectif

Mettre en route les six daemons Shinken (arbiter, scheduler, poller,
reactionner, broker, receiver) en containers Podman sur un serveur Linux, et
vérifier qu'ils tournent.

## Périmètre

Couvre le clonage, le build et le premier démarrage. La configuration des
hôtes/services est traitée dans [Configurer Shinken](configuration.md), et
l'exposition d'une interface web dans [Brancher Thruk via
Livestatus](livestatus-thruk.md).

## Prérequis

- Un serveur Linux avec **Podman** (rootless ou non) et **git**.
- `podman-compose` — pas forcément préinstallé :

    ```bash
    sudo dnf install -y python3-pip   # ou apt install python3-pip
    sudo pip install podman-compose
    ```

- Les ports suivants libres sur l'hôte (adaptables dans `compose.yaml`) :
  **8081** (webui minimal) et **50000** (Livestatus).

!!! attention "Vérifier les ports avant de lancer"
    `ss -tlnp` avant de démarrer. Un port déjà pris par un autre service ne
    donne pas d'erreur claire au démarrage de `podman-compose up`, juste un
    container qui ne publie jamais son port.

## Étapes

1. **Cloner le dépôt et se placer sur la bonne branche** :

    ```bash
    git clone git@github.com:NCombarieu/shinken_gpt.git
    cd shinken_gpt
    git checkout modernize/podman-python3
    ```

    !!! information "Pourquoi cette branche et pas master"
        `master` ne porte qu'un correctif mineur sur l'upstream Python 2.
        Tout le travail de modernisation (Python 3, Podman, Livestatus) vit
        sur `modernize/podman-python3`.

2. **Construire l'image** :

    ```bash
    podman-compose build
    ```

    Le `Containerfile` installe Python 3, les plugins Nagios de base
    (`nagios-plugins-basic`), NRPE (`nagios-nrpe-plugin`, pour
    `check_nrpe_ssl`) et le client SSH système (`openssh-client`, requis par
    `check_by_ssh`).

3. **Lancer la stack** :

    ```bash
    podman-compose up -d
    ```

    Six containers démarrent : `shinken_arbiter_1`, `shinken_scheduler_1`,
    `shinken_poller_1`, `shinken_reactionner_1`, `shinken_broker_1`,
    `shinken_receiver_1`. Seul le broker publie des ports sur l'hôte
    (webui + Livestatus).

## Résultat attendu

!!! resultat "Ce que vous devez obtenir"
    - `podman ps -a --filter name=shinken` montre les six containers `Up` ;
    - `curl http://127.0.0.1:8081/healthz` répond `ok` ;
    - une requête Livestatus brute répond (voir validation ci-dessous).

## Validation finale

!!! validation "À contrôler avant de passer à la suite"
    ```bash
    podman ps -a --filter name=shinken --format "table {{.Names}}\t{{.Status}}"
    curl -s http://127.0.0.1:8081/healthz
    python3 -c "
    import socket
    s = socket.create_connection(('127.0.0.1', 50000), timeout=5)
    s.sendall(b'GET hosts\nColumns: name state\n\n')
    s.shutdown(socket.SHUT_WR)
    print(s.recv(4096).decode())
    "
    ```

    La requête Livestatus doit renvoyer au moins `localhost;0` (l'hôte
    fourni par défaut, voir [Configurer Shinken](configuration.md)).

## Retour arrière

```bash
podman-compose down       # arrête et retire les containers, garde les volumes
podman-compose down -v    # + supprime les volumes (perte des logs/état)
```

Aucune installation système n'est touchée : tout vit dans les containers et
dans `etc/` (bind-mount du dépôt).

## Dépannage

!!! depannage "Un container reste en \"Created\" sans jamais démarrer"
    Souvent un conflit de port. `ss -tlnp` pour identifier ce qui occupe déjà
    le port visé, puis remapper dans `compose.yaml` (`"127.0.0.1:<autre
    port>:8080"` par exemple pour le broker).

!!! depannage "\"Configuration is incorrect, sorry, I bail out\" en boucle"
    L'arbiter rejette un fichier de `etc/`. Voir les logs complets :
    `podman logs shinken_arbiter_1`. Cause fréquente : un caractère interdit
    dans un `service_description` — voir [Dépanner
    Shinken](depannage.md#caracteres-interdits).

!!! depannage "Rien ne se passe pendant plusieurs minutes après le lancement"
    Normal pour le tout premier cycle : Shinken étale ses checks initiaux sur
    jusqu'à 5 minutes (`max_service_check_spread` dans `etc/shinken.cfg`)
    pour éviter un pic de charge au démarrage. Ce n'est pas un blocage — voir
    [Exploiter Shinken](exploitation.md#forcer-un-check) pour ne pas
    attendre.

## Voir aussi

- [Configurer Shinken](configuration.md)
- [Brancher Thruk via Livestatus](livestatus-thruk.md)
- [Dépanner Shinken](depannage.md)
