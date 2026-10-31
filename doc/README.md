# Documentation de Shinken

Shinken est un moteur de supervision compatible Nagios (configuration et
plugins), ici porté en Python 3 et déployé par conteneurs Podman. Choisissez
votre parcours.

## Je configure la supervision (administrateur)

Hôtes, services, contacts, plugins de check. Aucune connaissance du code
nécessaire. → [Guide de l'administrateur](admin/README.md)

| Niveau | Pages |
|---|---|
| **Simple** | [Présentation](admin/00-presentation.md) · [Démarrage rapide](admin/01-demarrage-rapide.md) · [Concepts](admin/02-concepts.md) · [Interface web](admin/03-interface-web.md) · [Acquitter, downtime](admin/04-acquitter-et-planifier-un-downtime.md) |
| **Avancé** | [Modèles](admin/10-templates-heritage.md) · [Macros](admin/11-macros.md) · [Groupes](admin/12-groupes.md) · [Dépendances, escalades](admin/13-dependances-escalades.md) · [Flapping, event handlers](admin/14-flapping-et-event-handlers.md) · [Checks passifs](admin/15-checks-passifs-commandes-externes.md) · [**Écrire un plugin**](admin/16-ecrire-un-plugin.md) · [Notifications](admin/17-notifications.md) · [Périodes](admin/18-periodes-de-temps.md) · [Recettes](admin/recettes/README.md) |
| **Expert** | [Architecture distribuée](admin/20-architecture-distribuee.md) · [Business rules](admin/21-business-rules.md) · [duplicate_foreach](admin/22-duplicate-foreach.md) · [Découverte](admin/23-decouverte.md) · [Performances](admin/24-performances.md) · [Rétention](admin/25-retention.md) · [Livestatus](admin/26-livestatus.md) · [Métriques](admin/27-metriques.md) |
| **Référence** | [Directives, macros, commandes externes](admin/reference/README.md) |

## J'installe et j'exploite le serveur (exploitant système)

→ [Guide de l'exploitant](exploitation/README.md) :
[installation](exploitation/01-installation.md),
[configuration du déploiement](exploitation/02-configuration.md),
[opérations courantes](exploitation/03-operations-courantes.md),
[démarrage au boot](exploitation/04-demarrage-au-boot.md),
[sauvegarde](exploitation/05-sauvegarde-restauration.md),
[mise à jour](exploitation/06-mise-a-jour-retour-arriere.md),
[surveiller Shinken](exploitation/07-surveiller-shinken.md),
[journaux](exploitation/08-logs.md),
[sécurité](exploitation/09-securite.md),
[reverse proxy TLS](exploitation/10-reverse-proxy-tls.md),
[dépannage](exploitation/11-depannage.md).

## Je migre depuis Shinken 2.4 (master)

→ [Guide de migration](migration-depuis-shinken-master.md) : différences,
modules, bascule, retour arrière.

## Je développe

→ [Guide du développeur](dev/README.md) : [DEVELOPMENT.md](../DEVELOPMENT.md),
[architecture](dev/architecture.md),
[protocole entre daemons](dev/protocole-inter-daemons.md),
[écrire un module](dev/ecrire-un-module.md).

## Pour tous

- [Glossaire](glossaire.md)
- [FAQ](faq.md)
- [Changelog](../Changelog)
- [Revue de migration du 31/10/2026](revue/SYNTHESE.md) (historique)
