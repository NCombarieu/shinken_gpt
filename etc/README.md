# Configuration d'exemple de Shinken

Ce dossier est une configuration **d'exemple**, neutre, qui démarre telle
quelle : un seul hôte supervisé (`localhost`, le serveur Shinken) et un
contact `admin`. Il est monté en lecture seule sur `/etc/shinken` dans les
conteneurs.

Avant une mise en service, au minimum :

1. remplacer l'adresse et le mot de passe du contact `admin`
   (`contacts/admin.cfg`), supprimer ou modifier `contacts/guest.cfg` ;
2. renseigner le relais SMTP (`resource.d/notifications.cfg`) ;
3. remplacer les valeurs d'exemple de `resource.d/` (communauté SNMP,
   comptes techniques) ;
4. ajouter vos hôtes et services (voir `hosts/exemples.cfg`,
   `services/exemples.cfg` et
   [doc/admin/01-demarrage-rapide.md](../doc/admin/01-demarrage-rapide.md)).

Pour un déploiement réel, conservez votre configuration dans un dépôt git
**privé** (elle contient des adresses et des identifiants) et montez-la à la
place de ce dossier.

Vérifier la configuration après chaque modification :
`shinken-arbiter -v -c /etc/shinken/shinken.cfg` (voir
[doc/admin/01-demarrage-rapide.md](../doc/admin/01-demarrage-rapide.md)).

## Contenu

| Dossier ou fichier | Contenu |
|---|---|
| `shinken.cfg` | Fichier principal lu par l'arbiter : dossiers chargés et paramètres globaux. |
| `hosts/` | Hôtes supervisés (`define host`). `exemples.cfg` : modèles commentés. |
| `services/` | Services (`define service`). `exemples.cfg` : modèles commentés. |
| `hostgroups/`, `servicegroups/`, `contactgroups/` | Groupes. |
| `contacts/` | Personnes notifiées et comptes de consultation. |
| `templates/` | Modèles (`generic-host`, `generic-service`, `generic-contact`, fréquences de check). |
| `commands/` | Commandes de check, de notification et de rechargement. |
| `timeperiods/` | Périodes de temps (`24x7`, `workhours`, jours fériés). |
| `notificationways/` | Modes de notification des contacts (e-mail). |
| `escalations/`, `dependencies/` | Escalades et dépendances (exemples commentés). |
| `resource.d/` | Macros globales : chemins des plugins, relais SMTP, identifiants techniques. |
| `realms/` | Realms (supervision distribuée). |
| `packs/` | Packs de configuration ajoutés à la main. |
| `modules/` | Définition des modules (Livestatus, rétention, WebUI…). |
| `arbiters/`, `schedulers/`, `pollers/`, `reactionners/`, `brokers/`, `receivers/` | Déclaration des daemons et des modules qu'ils chargent. |
| `daemons/*.ini` | Paramètres de lancement de chaque daemon (port, journaux, répertoires). |
| `certs/`, `ssh_keys/` | Certificats et clés : **jamais versionnés** (voir les README). |
| `discovery/` | Règles de l'outil de découverte réseau. |
| `grafana/` | Provisionnement de la pile de métriques expérimentale. |

Référence complète : [doc/README.md](../doc/README.md).
