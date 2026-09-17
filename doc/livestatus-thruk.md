---
title: "Brancher Thruk via Livestatus"
domain: "Shinken"
type: "procedure"
level: "intermediaire"
duration: "30 min"
version: "1.0"
updated: "2026-09-13"
owner: "Administration Supervision"
status: "valid"
order: 5
action: "Donner à Shinken une interface web complète"
keywords: [thruk, livestatus, omd, interface web, cgi.cfg, htpasswd]
summary: "Activer le module Livestatus de Shinken et y connecter Thruk pour obtenir statuts, force check, acknowledge et downtime."
---

# Brancher Thruk via Livestatus

## Objectif

Donner à Shinken une vraie interface web (statuts, force check, acknowledge,
downtime) en le branchant à **Thruk**, une interface générique qui parle le
protocole **Livestatus**.

## Périmètre

Thruk **n'est pas inclus dans ce dépôt** — c'est un logiciel à part
(distribué ici via l'image `consol/omd-labs-debian`, OMD Labs Edition), qui
se connecte à Shinken uniquement par le réseau, via le module Livestatus de
Shinken. Cette fiche couvre l'activation du module côté Shinken et le
branchement de Thruk dessus. Pour ajouter des hôtes/services à afficher,
voir [Configurer Shinken](configuration.md).

## Prérequis

- La stack Shinken déjà lancée (voir [Installer et lancer
  Shinken](installation.md)).
- Un container Thruk/OMD déjà en place, ou à créer :

    ```bash
    podman volume create omd-thruk-site
    podman run -d --name omd-thruk \
      --network shinken_default \
      -p 127.0.0.1:8443:443 \
      -v omd-thruk-site:/omd/sites/demo \
      --cap-add=NET_RAW \
      --restart unless-stopped \
      docker.io/consol/omd-labs-debian:latest
    ```

    !!! attention "--network shinken_default est obligatoire dès la création"
        Le container Thruk doit être sur le même réseau Podman que la stack
        Shinken pour la joindre par nom (`broker:50000`). Le mode réseau
        rootless par défaut ("pasta") ne permet pas d'ajouter un réseau après
        coup avec `podman network connect` — il faut le préciser dès le
        `podman run`, sinon recréer le container.

## Étapes

1. **Activer le module Livestatus côté Shinken** (déjà fait dans ce dépôt,
   pour référence si vous partez d'une config vierge) :

    ```ini
    # etc/modules/livestatus.cfg
    define module{
        module_name     livestatus
        module_type     livestatus
        host            0.0.0.0
        port            50000
        modules         logstore-null
    }
    ```

    ```ini
    # etc/modules/logstore-null.cfg
    define module{
        module_name     logstore-null
        module_type     logstore_null
    }
    ```

    Et référencer dans `etc/brokers/broker-master.cfg` :

    ```
    modules             livestatus,status-webui
    ```

    Publier le port dans `compose.yaml` (`broker.ports`) :

    ```yaml
    ports:
      - "127.0.0.1:50000:50000"
    ```

2. **Vérifier que Livestatus répond**, avant de toucher à Thruk :

    ```bash
    python3 -c "
    import socket
    s = socket.create_connection(('127.0.0.1', 50000), timeout=5)
    s.sendall(b'GET hosts\nColumns: name state\n\n')
    s.shutdown(socket.SHUT_WR)
    print(s.recv(4096).decode())
    "
    ```

3. **Pointer Thruk vers le Livestatus de Shinken.** Éditer
   `etc/thruk/thruk.conf` dans le site OMD (`podman cp` pour extraire,
   éditer, renvoyer) :

    ```
    <Component Thruk::Backend>
        <peer>
            name  = Shinken
            type  = livestatus
            <options>
                peer = broker:50000
            </options>
        </peer>
    </Component>
    ```

    Puis `podman exec omd-thruk su - demo -c 'omd restart apache'`.

4. **Créer les comptes** dans `etc/htpasswd` du site OMD :

    ```bash
    podman exec omd-thruk su - demo -c "htpasswd -b etc/htpasswd <user> '<mdp>'"
    ```

    Pour un accès admin complet (force check, ack, downtime, config), ajouter
    l'utilisateur à `authorized_for_admin` dans `etc/thruk/cgi.cfg` :

    ```
    authorized_for_admin=omdadmin,<user>
    ```

5. **Déclarer chaque utilisateur comme contact Shinken réel**, sinon
   Livestatus ne lui montrera rien du tout :

    ```ini
    # etc/contacts/webteam.cfg
    define contact{
        use                 generic-contact
        contact_name        <user>
        contactgroups       admins
        email               <user>@example.org
        password            unused-thruk-handles-auth
        is_admin            1
    }
    ```

    !!! information "Pourquoi ce contact est nécessaire"
        Livestatus filtre les résultats par `AuthUser` : un login qui n'est
        pas aussi un contact Shinken exact voit un site **vide**, sans
        message d'erreur.

## Résultat attendu

!!! resultat "Ce que vous devez obtenir"
    - `https://<votre-domaine>/demo/thruk/` affiche un login Thruk ;
    - une fois connecté, les hôtes/services configurés dans
      [Configurer Shinken](configuration.md) apparaissent ;
    - le bouton "Reschedule" (force check) sur un service produit un
      résultat réel en quelques secondes.

## Validation finale

!!! validation "À contrôler avant de passer à la suite"
    ```bash
    # Livestatus repond
    python3 -c "
    import socket
    s = socket.create_connection(('127.0.0.1', 50000), timeout=5)
    s.sendall(b'GET services\nColumns: host_name description state\n\n')
    s.shutdown(socket.SHUT_WR)
    print(s.recv(4096).decode())
    "
    # forcer un check et verifier qu'il produit un vrai resultat
    python3 -c "
    import socket, time
    s = socket.create_connection(('127.0.0.1', 50000), timeout=5)
    now = int(time.time())
    s.sendall(('COMMAND [%d] SCHEDULE_FORCED_SVC_CHECK;localhost;Load;%d\n\n' % (now, now)).encode())
    "
    ```

## Reload/Restart depuis Thruk

Les boutons "Reload"/"Restart" de Thruk (page Process Info) envoient les
commandes `RELOAD_CONFIG`/`RESTART_PROCESS`. Shinken n'a pas de rechargement
à chaud façon SIGHUP : les deux commandes tuent le process arbiter, et
`restart: unless-stopped` dans `compose.yaml` relance le container, qui
relit `etc/`. Les commandes `reload-shinken`/`restart-shinken` (dans
`etc/commands/`) doivent pointer vers cette action plutôt que vers un script
`/etc/init.d/shinken` qui n'existe pas dans un déploiement conteneurisé :

```ini
define command {
    command_name        reload-shinken
    command_line        /usr/bin/pkill -TERM -f shinken-arbiter
}
```

## Dépannage

!!! depannage "\"Session is not valid anymore\" juste après connexion"
    Race condition connue de Thruk entre ses process Apache (`mod_fcgid`) et
    le stockage de session, pas liée à Shinken. Réessayer quelques secondes
    après suffit en général. Confirmé indépendant de Caddy/reverse-proxy en
    testant en direct sur le port du container.

!!! depannage "Le mot de passe d'un utilisateur redevient invalide sans raison"
    Observé de façon répétée sur un compte sans cause identifiée après
    audit du crontab OMD et du code Thruk. Pas de correctif trouvé à ce
    jour — juste re-régénérer le mot de passe. Documenter la date/heure si
    ça se reproduit, pour recouper avec d'autres événements du serveur.

!!! depannage "Le \"Check Command\" n'apparaît pas sur la page de détail"
    Masqué par le rôle Thruk `authorized_for_configuration_information`.
    Passer `show_full_commandline = 2` dans `thruk.conf` (visible par tous)
    plutôt que de construire un mapping de rôles pour peu d'utilisateurs.

!!! depannage "Le hostname n'apparaît pas, seule la description du service"
    `Host.display_name` n'a pas de valeur par défaut dans ce fork (contra
    `Service.display_name`, qui retombe sur `service_description`). Corrigé
    dans `shinken/objects/host.py` — si le symptôme réapparaît sur un autre
    fork/version, ajouter le même fallback vers `host_name`.

## Voir aussi

- [Configurer Shinken](configuration.md)
- [Exploiter Shinken au quotidien](exploitation.md)
- [Dépanner Shinken](depannage.md)
