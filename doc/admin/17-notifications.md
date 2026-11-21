# Notifications par e-mail

**Public :** administrateur de la supervision, niveau avancé.

## La chaîne complète

```
hôte/service en problème HARD
  └─► contacts et contact_groups de l'objet
        └─► notificationways du contact (période, états)
              └─► commande de notification (notify-service-by-email…)
                    └─► exécutée par le reactionner : notify_by_email.py
                          └─► relais SMTP de votre organisation ─► boîte du contact
```

Si un maillon manque, aucun message ne part. Les conteneurs n'embarquent pas
de serveur de messagerie : **un relais SMTP est obligatoire**.

## Configurer le relais SMTP

Les paramètres sont des macros de `etc/resource.d/notifications.cfg` :

```
$SMTP_HOST$=smtp.example.com
$SMTP_PORT$=25
$MAIL_FROM$=shinken@example.com
```

| Macro | Valeur |
|---|---|
| `$SMTP_HOST$` | nom ou adresse du relais, joignable depuis le conteneur reactionner |
| `$SMTP_PORT$` | 25 (relais interne, en clair ou STARTTLS), 587 (soumission authentifiée), 465 (SMTPS) |
| `$MAIL_FROM$` | adresse d'expéditeur ; elle doit être acceptée par le relais (SPF, domaine autorisé) |

Les commandes `notify-host-by-email`, `notify-service-by-email`,
`detailled-host-by-email` et `detailled-service-by-email`
(`etc/commands/`) utilisent ces macros. Rechargez la configuration après
modification.

### Relais avec authentification et chiffrement

Le script `notify_by_email.py` accepte :

| Option | Effet |
|---|---|
| `-S`, `--smtp-server` | relais SMTP |
| `--smtp-port` | port |
| `--smtp-starttls` | chiffrement STARTTLS après connexion |
| `--smtp-ssl` | connexion chiffrée dès le départ (port 465) |
| `--smtp-user` | compte d'authentification |
| `--smtp-password-file` | fichier contenant le mot de passe |
| `-s`, `--sender` | expéditeur |
| `-f txt\|html` | format du message |

Ajoutez les options nécessaires à la `command_line` des quatre commandes,
par exemple :

```
... -S $SMTP_HOST$ --smtp-port 587 --smtp-starttls --smtp-user supervision@example.com --smtp-password-file /run/secrets/smtp_password ...
```

Le mot de passe se place dans un **fichier** (secret Podman monté dans le
conteneur reactionner), jamais dans une macro : une macro apparaît dans la
ligne de commande, donc dans la liste des processus et les journaux. Voir
[configuration du déploiement](../exploitation/02-configuration.md).

## Qui reçoit quoi

Un contact reçoit une notification si **toutes** ces conditions sont
réunies :

| Côté objet (hôte ou service) | Côté contact (ou son notificationway) |
|---|---|
| `notifications_enabled 1` | `host_notifications_enabled` / `service_notifications_enabled` à 1 |
| dans `notification_period` | dans `host_notification_period` / `service_notification_period` |
| état présent dans `notification_options` | état présent dans `host_notification_options` / `service_notification_options` |
| le contact est dans `contacts` ou un de ses `contact_groups` | `business_impact` de l'objet ≥ `min_business_impact` du contact |
| problème non acquitté, hors downtime, pas en flapping | — |

Options d'états :

| Lettre | Hôte | Service |
|---|---|---|
| `d` | DOWN | — |
| `u` | UNREACHABLE | UNKNOWN |
| `w` | — | WARNING |
| `c` | — | CRITICAL |
| `r` | rétablissement (UP) | rétablissement (OK) |
| `f` | début et fin de flapping | idem |
| `s` | début et fin de downtime | idem |
| `n` | aucune notification | idem |

## Modes de notification (`notificationway`)

Un contact peut avoir plusieurs modes : e-mail en journée, SMS la nuit pour
les seuls problèmes critiques…

```
define notificationway {
    notificationway_name            email-heures-ouvrees
    host_notification_period        workhours
    service_notification_period     workhours
    host_notification_options       d,u,r
    service_notification_options    w,c,r
    host_notification_commands      notify-host-by-email
    service_notification_commands   notify-service-by-email
}

define contact {
    use                 generic-contact
    contact_name        jdupont
    email               jeanne.dupont@example.com
    notificationways    email-heures-ouvrees
}
```

Le mode `detailled-email` produit un message HTML enrichi des macros
personnalisées `_DETAILLEDDESC`, `_IMPACT` et `_FIXACTIONS` définies sur les
hôtes et services (procédure de résolution, impact métier).

## Rythme et regroupement

| Directive (hôte ou service) | Effet |
|---|---|
| `notification_interval` | minutes entre deux rappels tant que le problème dure (`0` = un seul message) |
| `first_notification_delay` | minutes d'attente avant le premier message (laisse le temps à une auto-réparation) |
| `escalations` | destinataires supplémentaires si le problème dure (voir [escalades](13-dependances-escalades.md)) |

## Tester l'envoi

1. Vérifier que le relais est joignable depuis le reactionner :

   ```bash
   podman-compose exec reactionner python3 -c \
     "import smtplib; print(smtplib.SMTP('smtp.example.com', 25, timeout=10).noop())"
   ```

2. Envoyer une notification de test sans attendre de panne, par Livestatus :

   ```bash
   printf 'COMMAND [%s] SEND_CUSTOM_SVC_NOTIFICATION;localhost;Charge;0;admin;Test de notification\n\n' \
       "$(date +%s)" | nc 127.0.0.1 50000
   ```

3. Consulter le journal du reactionner en cas d'échec :
   `podman-compose logs reactionner`.

## Autres canaux

Tout programme peut servir de commande de notification : il reçoit les
macros en arguments (`$CONTACTPAGER$`, `$SERVICEOUTPUT$`…). Pour un SMS, un
webhook de messagerie instantanée ou un outil de ticket, écrivez un script
dans `plugins-local/` (voir [écrire un plugin](16-ecrire-un-plugin.md)) et
déclarez une commande :

```
define command {
    command_name    notify-service-by-webhook
    command_line    $LOCALPLUGINSDIR$/notify_webhook.py --type "$NOTIFICATIONTYPE$" --host "$HOSTNAME$" --service "$SERVICEDESC$" --state "$SERVICESTATE$" --output "$SERVICEOUTPUT$"
}
```

Le script s'exécute dans le conteneur reactionner : l'URL du webhook doit y
être joignable.
