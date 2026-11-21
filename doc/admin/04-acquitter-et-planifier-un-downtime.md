# Acquitter un problème et planifier un downtime

**Public :** administrateur de la supervision, niveau simple.

## Acquitter un problème

Acquitter (*acknowledge*) signifie « ce problème est pris en charge » :

- les rappels de notification s'arrêtent ;
- les autres contacts reçoivent une notification d'acquittement (si
  demandé), ce qui évite que deux personnes traitent le même incident ;
- le problème disparaît des vues *Unhandled* de Thruk.

L'acquittement n'est possible que sur un objet **en problème** : sur un
service OK, la commande est ignorée sans message.

### Depuis Thruk

Page du service → *Acknowledge this service problem*, puis :

| Option | Effet |
|---|---|
| *Sticky Acknowledgement* | l'acquittement reste valable tant que l'objet n'est pas revenu à OK, même s'il passe de WARNING à CRITICAL. Sinon il est levé au premier changement d'état. |
| *Send Notification* | prévient les contacts que le problème est pris en charge. |
| *Persistent Comment* | conserve le commentaire après la fin de l'acquittement. |
| *Comment* | votre texte : qui, pourquoi, ticket associé. |

### En ligne de commande

Les commandes passent par Livestatus (port 50000). Exemple avec un petit
script Python (aucune dépendance) :

```bash
python3 - <<'EOF'
import socket, time
now = int(time.time())
cmd = ("COMMAND [%d] ACKNOWLEDGE_SVC_PROBLEM;srv-web-01;HTTP;2;1;1;"
       "jdupont;Incident en cours, ticket 1234\n\n" % now)
s = socket.create_connection(("127.0.0.1", 50000), timeout=5)
s.sendall(cmd.encode())
s.close()
EOF
```

Format : `ACKNOWLEDGE_SVC_PROBLEM;<hôte>;<service>;<sticky>;<notifier>;<persistant>;<auteur>;<commentaire>`
— `sticky` vaut 2 (collant) ou 0. Pour un hôte :
`ACKNOWLEDGE_HOST_PROBLEM;<hôte>;<sticky>;<notifier>;<persistant>;<auteur>;<commentaire>`.

Lever un acquittement : `REMOVE_SVC_ACKNOWLEDGEMENT;<hôte>;<service>` ou
`REMOVE_HOST_ACKNOWLEDGEMENT;<hôte>`.

## Planifier un downtime (maintenance)

Un downtime déclare une période de maintenance : l'objet continue d'être
vérifié, mais **aucune notification de problème** n'est envoyée pendant la
période. Les contacts reçoivent une notification de début et de fin de
downtime si `s` figure dans leurs `notification_options`.

### Depuis Thruk

Page de l'hôte ou du service → *Schedule downtime*. Pour un hôte, choisir
*Schedule downtime for all services on this host* afin de couvrir aussi ses
services.

| Option | Effet |
|---|---|
| *Start / End Time* | bornes de la fenêtre. |
| *Type : Fixed* | le downtime couvre exactement la fenêtre. |
| *Type : Flexible* | le downtime commence au premier problème survenant dans la fenêtre et dure *Duration*. |
| *Comment* | motif de l'intervention. |

### En ligne de commande

```bash
python3 - <<'EOF'
import socket, time
start = int(time.time())
end = start + 2 * 3600          # 2 heures
cmd = ("COMMAND [%d] SCHEDULE_SVC_DOWNTIME;srv-web-01;HTTP;%d;%d;1;0;7200;"
       "jdupont;Mise à jour applicative\n\n" % (start, start, end))
s = socket.create_connection(("127.0.0.1", 50000), timeout=5)
s.sendall(cmd.encode())
s.close()
EOF
```

Format : `SCHEDULE_SVC_DOWNTIME;<hôte>;<service>;<début>;<fin>;<fixe 1|0>;<id déclencheur>;<durée s>;<auteur>;<commentaire>`
(dates en secondes depuis le 1er janvier 1970, `date +%s`).

| Commande | Portée |
|---|---|
| `SCHEDULE_HOST_DOWNTIME;<hôte>;…` | l'hôte seul |
| `SCHEDULE_HOST_SVC_DOWNTIME;<hôte>;…` | tous les services de l'hôte |
| `SCHEDULE_HOSTGROUP_HOST_DOWNTIME;<groupe>;…` | tous les hôtes d'un groupe |
| `DEL_SVC_DOWNTIME;<id>` / `DEL_HOST_DOWNTIME;<id>` | supprime un downtime (identifiant visible dans Thruk) |

La liste complète est dans la [référence des commandes externes](reference/commandes-externes.md).

### Maintenance récurrente

Pour une maintenance qui revient chaque semaine (sauvegarde du dimanche
soir…), plutôt qu'un downtime manuel, utilisez la directive
`maintenance_period` de l'hôte ou du service :

```
define timeperiod {
    timeperiod_name     sauvegarde-dimanche
    alias               Sauvegarde hebdomadaire
    sunday              22:00-24:00
}
```

puis `maintenance_period  sauvegarde-dimanche` dans l'hôte : il est traité
comme en downtime sur ces plages.

## Conservation après redémarrage

Acquittements, downtimes et commentaires sont enregistrés par le module de
rétention du scheduler et rechargés après un redémarrage ou un rechargement
de la configuration (voir [rétention](25-retention.md)).
