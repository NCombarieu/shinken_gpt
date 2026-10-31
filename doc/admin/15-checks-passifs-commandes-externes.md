# Checks passifs et commandes externes

**Public :** administrateur de la supervision, niveau avancé.

## Commandes externes

Une commande externe est un ordre donné à Shinken de l'extérieur : forcer un
check, acquitter, poser un downtime, soumettre un résultat passif, désactiver
les notifications… Elle a toujours la forme :

```
[<horodatage Unix>] NOM_DE_LA_COMMANDE;argument1;argument2;...
```

La liste complète (171 commandes, compatibles Nagios) est dans la
[référence des commandes externes](reference/commandes-externes.md).

### Trois façons de les envoyer

| Canal | Pour qui | Comment |
|---|---|---|
| **Thruk** | les opérateurs | boutons des pages de détail |
| **Livestatus** (TCP 50000 sur le broker) | scripts, outils | `COMMAND [horodatage] NOM;args` suivi d'une ligne vide |
| **Tube nommé `nagios.cmd`** | scripts hérités de Nagios | écrire la ligne dans le fichier |

Exemple Livestatus depuis le serveur :

```bash
printf 'COMMAND [%s] SCHEDULE_FORCED_SVC_CHECK;srv-web-01;HTTP;%s\n\n' \
    "$(date +%s)" "$(date +%s)" | nc 127.0.0.1 50000
```

### Activer `nagios.cmd`

Le tube nommé est fourni par le module `named-pipe`, chargé par l'arbiter. Le
plus simple est de décommenter dans `etc/shinken.cfg` :

```
command_file=/var/lib/shinken/nagios.cmd
```

L'arbiter crée alors le module automatiquement au démarrage et le tube dans
le volume de données. Écriture depuis le serveur :

```bash
podman-compose exec arbiter sh -c \
  'printf "[%s] DISABLE_NOTIFICATIONS\n" "$(date +%s)" > /var/lib/shinken/nagios.cmd'
```

> **Note** — Le tube est créé dans le conteneur arbiter. Un script qui
> tourne sur le serveur hôte doit donc passer par `podman-compose exec
> arbiter`, ou utiliser Livestatus, plus simple à atteindre.

### Sécurité

Livestatus et `nagios.cmd` n'ont **aucune authentification** : quiconque
peut s'y connecter peut tout faire, y compris `RESTART_PROGRAM`. Le port
50000 n'est publié que sur `127.0.0.1` ; restreignez-le davantage avec la
directive `allowed_hosts` du module `livestatus` si d'autres conteneurs
partagent le réseau (voir [sécurité](../exploitation/09-securite.md)).

## Checks passifs

Un check passif est un résultat **soumis** à Shinken au lieu d'être mesuré
par lui : sauvegarde nocturne qui signale sa fin, application qui rapporte
ses erreurs, équipement injoignable directement.

### 1. Déclarer le service

```
define service {
    use                     generic-service
    host_name               srv-bdd-01
    service_description     Sauvegarde nocturne
    active_checks_enabled   0
    passive_checks_enabled  1
    max_check_attempts      1
    check_freshness         1
    freshness_threshold     93600
    check_command           check_dummy!2!Aucun résultat de sauvegarde depuis 26 h
}
```

- `active_checks_enabled 0` : Shinken ne lance rien de lui-même ;
- `max_check_attempts 1` : un résultat en échec passe directement en HARD ;
- `check_freshness` / `freshness_threshold` (secondes) : si aucun résultat
  n'arrive pendant 26 h, Shinken exécute `check_command` — ici le service
  passe CRITICAL avec un message explicite. Sans cela, un script de
  sauvegarde qui ne tourne plus du tout passerait inaperçu.

### 2. Soumettre le résultat

À la fin du script de sauvegarde :

```bash
code=0; texte="Sauvegarde OK, 42 Go en 37 min"
printf 'COMMAND [%s] PROCESS_SERVICE_CHECK_RESULT;srv-bdd-01;Sauvegarde nocturne;%s;%s|taille=42GB duree=2220s\n\n' \
    "$(date +%s)" "$code" "$texte" | nc supervision.example.com 50000
```

Format : `PROCESS_SERVICE_CHECK_RESULT;<hôte>;<service>;<code 0-3>;<sortie>|<perfdata>`.
Pour un hôte : `PROCESS_HOST_CHECK_RESULT;<hôte>;<code>;<sortie>` ; le code
est interprété comme celui d'un plugin de check d'hôte : 0 = UP, 2 ou 3 =
DOWN (1 est traité comme UP).

> **Attention** — Le port Livestatus n'est publié que sur `127.0.0.1`. Pour
> recevoir des résultats d'autres machines, ne l'ouvrez pas tel quel :
> faites transiter les résultats par SSH (`ssh supervision.example.com
> 'printf ... | nc 127.0.0.1 50000'`, avec une clé restreinte), ou par un
> relais qui authentifie les émetteurs.

### Résultats pour des objets inconnus

Par défaut, un résultat passif pour un hôte ou un service non déclaré est
ignoré. La directive `accept_passive_unknown_check_results 1`, dans la
définition du scheduler (`etc/schedulers/`) ou du receiver, le fait remonter
aux modules du broker (sans créer d'objet).

## Le receiver

Le daemon **receiver** est prévu pour recevoir des données de l'extérieur
via ses modules (NSCA, API web). Aucun module de réception n'est livré dans
cette version : utilisez Livestatus ou `nagios.cmd` comme décrit ci-dessus.
Voir le [guide de migration](../migration-depuis-shinken-master.md) si votre
installation actuelle utilise NSCA ou `ws-arbiter`.
