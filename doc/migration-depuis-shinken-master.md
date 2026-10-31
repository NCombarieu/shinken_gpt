# Migrer depuis Shinken master (2.4, Python 2)

**Public :** administrateur de la supervision et exploitant système.

Ce guide décrit le remplacement d'une installation Shinken « master »
(projet `naparuba/shinken`, version 2.4.x, Python 2) par cette version
(Python 3, conteneurs Podman).

## Ce qui ne change pas

- **Le langage de configuration** : objets, directives, modèles,
  `register 0`, héritage multiple et `+`, macros (`$USER1$`, `_VAR`),
  `duplicate_foreach`, expressions de groupes, `bp_rule`, dépendances,
  escalades, realms, périodes. Une configuration master se charge telle
  quelle (sous réserve des points ci-dessous).
- **Les plugins** : même contrat, mêmes monitoring-plugins.
- **Les commandes externes** (liste identique, plus l'alias
  `RESTART_PROCESS` envoyé par le bouton *Restart* de Thruk).
- **Les daemons** : mêmes rôles, mêmes options de ligne de commande, mêmes
  fichiers `.ini`, mêmes ports (7768 à 7773, Livestatus 50000).
- **Livestatus** : Thruk et les outils compatibles fonctionnent.

## Ce qui change

| Sujet | Shinken master | Cette version | Conséquence |
|---|---|---|---|
| langage | Python 2 | Python 3.11+ | les modules Python 2 ne se chargent pas |
| protocole entre daemons | `PUT` + `zlib(pickle)` Python 2 | `POST` + `base64(zlib(pickle))` Python 3 | **aucune cohabitation** de daemons des deux versions : bascule de tous les daemons en même temps |
| installation | paquets, `setup.py` installant `/etc/shinken`, scripts init | image conteneur ; le paquet Python n'installe rien dans le système | voir [installation](exploitation/01-installation.md) |
| modules | installés par `shinken install` depuis shinken.io | livrés avec le projet ; `shinken install` et shinken.io ne sont plus disponibles | voir le tableau des modules |
| interface web | module `webui` / `webui2` | page d'état minimale ; Thruk recommandé | voir [interface web](admin/03-interface-web.md) |
| encodage des `.cfg` | Python 2 tolérant (latin-1 accepté) | UTF-8 attendu | convertir les fichiers latin-1 |
| rechargement | `/etc/init.d/shinken reload` | redémarrage de l'arbiter (conteneur) | commandes `reload-shinken` / `restart-shinken` adaptées |
| `nagios.cmd` | module `named-pipe` | module `named-pipe` porté | activer `command_file` |

Directives et options de Shinken 2.4.4 **non prises en charge** :
`conflict_policy` et `enable_problem_impacts_states_reprocessing` (acceptées
avec un avertissement, sans effet) et l'option `--dump_conf` de l'arbiter.
Si vous utilisiez `conflict_policy=strict`, vérifiez l'absence d'objets
définis deux fois : cette version garde la dernière définition.

### Modules

| Module master | Disponible ici | Équivalent ou action |
|---|---|---|
| `livestatus` | oui | module `livestatus` |
| `logstore-sqlite` | oui | module `logstore-sqlite` (historique de Livestatus) |
| `logstore-null` | oui | — |
| `pickle-retention-file-scheduler` / `retention-file` | oui | module `retention-pickle` (relit les fichiers master) |
| `named-pipe` | oui | module `named-pipe` |
| `webui`, `webui2` | non | Thruk via Livestatus ; page d'état `status-webui` |
| `graphite`, `influxdb` (perfdata) | non | voir [métriques](admin/27-metriques.md) |
| `retention-mongodb`, `retention-redis`, `mongodb` | non | `retention-pickle` |
| `simple-log` | non | journaux des daemons et historique Livestatus (`logstore-sqlite`) |
| `ws-arbiter`, `nsca` (receiver) | non | commandes externes par Livestatus ou `nagios.cmd` |
| `booster-nrpe` | non | `check_nrpe` classique |
| autres modules tiers | non | à porter en Python 3 (voir [écrire un module](dev/ecrire-un-module.md)) |

Un module référencé mais absent ne bloque pas le démarrage : il produit
seulement l'avertissement `The module type <x> ... was not found in
modules!`, et **la fonction disparaît silencieusement**. Lisez donc tous les
avertissements de la vérification de configuration.

## Avant la bascule (sur l'installation master)

1. **Inventorier les modules** utilisés :

   ```bash
   grep -rh "^\s*modules" /etc/shinken/{arbiters,schedulers,brokers,receivers,pollers,reactionners}
   ```

   Pour chacun, trouver l'équivalent dans le tableau ci-dessus. Sans
   équivalent pour une fonction indispensable, ne migrez pas encore.

2. **Vérifier l'encodage** des fichiers de configuration et convertir ceux
   qui ne sont pas en UTF-8 :

   ```bash
   find /etc/shinken -name '*.cfg' -exec file -i {} + | grep -v 'utf-8\|us-ascii'
   iconv -f latin1 -t utf-8 fichier.cfg > fichier.cfg.new && mv fichier.cfg.new fichier.cfg
   ```

3. **Inventorier les plugins** appelés et vérifier leur présence dans
   l'image (monitoring-plugins, `check_nrpe`, scripts SNMP) ; les scripts
   maison iront dans `plugins-local/` :

   ```bash
   grep -rhoE '\$(USER1|NAGIOSPLUGINSDIR|PLUGINSDIR)\$/[A-Za-z0-9_.-]+' /etc/shinken | sort -u
   ```

4. **Retirer** les directives non prises en charge (`conflict_policy`,
   `enable_problem_impacts_states_reprocessing`) et `--dump_conf` des
   scripts.

5. **Sauvegarder** `/etc/shinken`, `/var/lib/shinken` (dont
   `retention.dat`, ou le fichier défini par votre module de rétention) et
   les scripts de plugins.

6. **Exporter** les acquittements et downtimes en cours (Thruk, ou
   Livestatus `GET downtimes` / `GET comments`) : ce sera le plan B si la
   reprise de rétention échoue.

## Préparer la nouvelle installation, en parallèle

7. Installer cette version sur un **autre serveur** (ou à côté, avec
   d'autres ports) : [installation](exploitation/01-installation.md).
8. Copier **votre** configuration master dans `etc/` (ne pas partir de
   l'exemple du dépôt) puis adapter :
   - `etc/resource.d/` : chemins des plugins (`$USER1$` →
     `/usr/lib/nagios/plugins`, scripts maison → `$LOCALPLUGINSDIR$`) ;
   - définitions des daemons : adresse `localhost` (adaptée automatiquement
     en conteneur) ;
   - modules : remplacer les modules absents (tableau ci-dessus), activer
     `retention-pickle` sur le scheduler, `livestatus` + `logstore-sqlite`
     sur le broker ;
   - commandes `reload-shinken` / `restart-shinken` : reprendre celles de
     `etc/commands/` du dépôt ;
   - `command_file` dans `shinken.cfg` si des scripts écrivent dans
     `nagios.cmd`.
9. Régler `TZ` comme sur l'ancien serveur.
10. **Désactiver les notifications** sur la nouvelle instance pendant
    l'observation : `enable_notifications=0` dans `shinken.cfg`.
11. Vérifier la configuration (`check`) : zéro erreur, et chaque
    avertissement compris.
12. Démarrer et **comparer** pendant quelques jours les états des deux
    instances :

    ```bash
    printf 'GET services\nColumns: host_name description state\n\n' | nc 127.0.0.1 50000 | sort > etats-nouveau.txt
    ```

    (même requête sur l'ancienne instance, puis `diff`). Les écarts viennent
    en général des plugins absents, du réseau depuis le poller ou du DNS.

## Bascule (tous les daemons en même temps)

13. Arrêter **tous** les daemons master, de tous les realms, spares compris.
    Ne jamais laisser des daemons master et de cette version se parler.
14. Copier le fichier de rétention master dans le volume de données de la
    nouvelle instance, **conteneurs arrêtés** :

    ```bash
    podman-compose stop
    podman volume inspect shinken_shinken-data --format '{{.Mountpoint}}'
    # copier retention.dat dans ce dossier (podman unshare cp en rootless),
    # propriétaire 10001
    ```

    Le module `retention-pickle` relit le format Python 2 (y compris les
    textes accentués) et le réécrit au format Python 3 à la sauvegarde
    suivante.
15. Réactiver les notifications (`enable_notifications=1`), démarrer.
16. Contrôler :
    - les downtimes et acquittements master sont présents ; sinon les
      reposer à partir de l'export de l'étape 6 ;
    - aucune notification ne part pour un objet en downtime ou acquitté ;
    - une notification de test arrive
      ([notifications](admin/17-notifications.md#tester-lenvoi)) ;
    - Thruk pointe vers la nouvelle instance ;
    - `GET log` de Livestatus est alimenté.

## Retour arrière

Gardez l'installation master **arrêtée mais intacte** (configuration,
rétention d'origine, paquets) pendant toute la période de validation.

1. Arrêter cette version : `podman-compose down` (sans `-v`).
2. Redémarrer les daemons master ; réactiver leurs notifications.

Les formats sont incompatibles dans ce sens : les acquittements et
downtimes posés sur la nouvelle instance ne sont **pas** repris par master.
Définissez à l'avance les critères de retour arrière (notifications non
reçues, daemon qui redémarre en boucle, Livestatus indisponible plus de
quelques minutes, nombre anormal de services PENDING).
