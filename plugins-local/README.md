# Scripts de check maison

Déposez ici vos propres plugins de supervision (scripts shell, Python, Perl…).
Ce dossier est monté **en lecture seule** dans les conteneurs `poller` et
`reactionner` sur `/usr/local/lib/shinken/plugins-local`, chemin de la macro
`$LOCALPLUGINSDIR$` (`etc/resource.d/paths.cfg`).

Seuls ce README et l'exemple `check_example.sh` sont versionnés : vos scripts
restent locaux (voir `.gitignore`) et ne sont pas copiés dans l'image.

## Ajouter un plugin

1. Copiez le script dans `plugins-local/` et rendez-le exécutable :
   `chmod 755 plugins-local/check_mon_appli.sh`.
2. Respectez le contrat des plugins Nagios : une ligne de sortie
   (`ÉTAT - message|perfdata`) et un code retour 0 = OK, 1 = WARNING,
   2 = CRITICAL, 3 = UNKNOWN.
3. Déclarez une commande dans `etc/commands/` :

   ```
   define command {
       command_name    check_example
       command_line    $LOCALPLUGINSDIR$/check_example.sh -w $ARG1$ -c $ARG2$
   }
   ```

4. Testez-le dans le conteneur, avec l'utilisateur des daemons :
   `podman exec shinken_poller_1 /usr/local/lib/shinken/plugins-local/check_example.sh -w 80 -c 90`
5. Rechargez la configuration (redémarrage de l'arbiter).

Le script s'exécute dans le conteneur poller (Debian, utilisateur non root
`shinken`, uid 10001) : il ne voit ni les fichiers ni les processus de
l'hôte. Les plugins standard sont dans `$NAGIOSPLUGINSDIR$`
(`/usr/lib/nagios/plugins`). S'il vous faut un paquet supplémentaire,
construisez une image dérivée :

```
FROM localhost/shinken:2.4.3
USER root
RUN apt-get update && apt-get install -y --no-install-recommends <paquet> \
    && rm -rf /var/lib/apt/lists/*
USER 10001:10001
```
