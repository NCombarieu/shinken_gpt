# Flapping et event handlers

**Public :** administrateur de la supervision, niveau avancé.

## Flapping

Un objet *flappe* quand il change d'état trop souvent : un lien réseau
instable, un service qui redémarre en boucle. Sans protection, chaque
changement produirait une notification.

### Fonctionnement

Shinken mémorise les `flap_history` derniers états (20 par défaut,
`shinken.cfg`) et calcule le pourcentage de changements, en pondérant plus
fort les plus récents.

- Au-dessus du **seuil haut**, l'objet est déclaré en flapping : une
  notification *FLAPPINGSTART* est envoyée (option `f`), puis **les
  notifications de problème sont suspendues**.
- Sous le **seuil bas**, le flapping s'arrête (*FLAPPINGSTOP*) et les
  notifications reprennent normalement.

| Directive | Où | Défaut |
|---|---|---|
| `flap_detection_enabled` | hôte, service | 1 |
| `low_flap_threshold` / `high_flap_threshold` | service | -1 = valeurs globales `low_service_flap_threshold` (20) et `high_service_flap_threshold` (30) |
| `low_flap_threshold` / `high_flap_threshold` | hôte | 25 et 50 |
| `flap_detection_options` | hôte (`o,d,u`), service (`o,w,c,u`) | tous les états |
| `enable_flap_detection` | `shinken.cfg` | 1 (interrupteur global) |

Un service qui flappe est un symptôme, pas un bruit : corrigez la cause ou
rendez le check plus tolérant (`max_check_attempts` plus élevé, modèles
`*_long` de `time_templates.cfg`).

### Services volatils

`is_volatile 1` est l'inverse : chaque résultat en problème est traité comme
un nouvel événement et notifié, sans phase SOFT. À réserver aux checks qui
remontent des événements ponctuels (alerte de sécurité, trap SNMP reçu
passivement).

## Event handlers (auto-remédiation)

Un *event handler* est une commande lancée automatiquement quand l'état d'un
objet change : redémarrer un service, vider un cache, ouvrir un ticket. Il est
exécuté par le **reactionner**.

### Quand est-il lancé

- au premier résultat en problème (état SOFT) ;
- à chaque nouvelle tentative en état SOFT ;
- au passage en HARD ;
- au retour à OK.

Il **n'est pas** lancé pendant un downtime (`no_event_handlers_during_downtimes=1`
dans `shinken.cfg`).

### Exemple : redémarrer un service web à la 2e tentative

Le script reçoit l'état, le type d'état et le numéro de tentative, et décide
lui-même s'il agit :

```
define command {
    command_name    relancer-apache
    command_line    $LOCALPLUGINSDIR$/relancer_apache.sh $SERVICESTATE$ $SERVICESTATETYPE$ $SERVICEATTEMPT$ $HOSTADDRESS$
}

define service {
    use                     generic-service
    host_name               srv-web-01
    service_description     HTTP
    check_command           check_http!/
    event_handler           relancer-apache
    event_handler_enabled   1
}
```

```bash
#!/bin/sh
# plugins-local/relancer_apache.sh <état> <type> <tentative> <adresse>
state=$1; state_type=$2; attempt=$3; address=$4
# Agir une seule fois : à la 2e tentative SOFT en CRITICAL.
if [ "$state" = "CRITICAL" ] && [ "$state_type" = "SOFT" ] && [ "$attempt" = "2" ]; then
    ssh -i /etc/shinken/ssh_keys/id_ed25519 supervision@"$address" relancer-apache
fi
exit 0
```

Côté serveur supervisé, la clé SSH est restreinte à cette seule action
(`command=` dans `authorized_keys`, voir la [recette SSH](recettes/linux-ssh.md)).

> **Attention** — Un event handler s'exécute avec les droits du compte
> `shinken`, dans le conteneur reactionner : déposez-y les scripts
> (`plugins-local/` est monté dans le poller et le reactionner) et limitez
> ce qu'ils peuvent faire à distance.

### Event handler global

`global_host_event_handler` et `global_service_event_handler`
(`shinken.cfg`) désignent une commande lancée pour **tous** les objets qui
n'ont pas leur propre event handler, par exemple pour journaliser chaque
changement d'état dans un outil externe.
