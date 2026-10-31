# Guide de l'administrateur de la supervision

Pour qui configure la supervision : hôtes, services, contacts, plugins de
check. Aucune connaissance du code de Shinken n'est nécessaire. Pour
installer et faire tourner les conteneurs, voir le
[guide de l'exploitant](../exploitation/README.md).

## Niveau simple : être opérationnel

| Page | Vous saurez… |
|---|---|
| [Présentation](00-presentation.md) | ce que fait Shinken et le rôle de chaque daemon |
| [Démarrage rapide](01-demarrage-rapide.md) | ajouter un hôte, un service, un contact ; vérifier et recharger |
| [Concepts essentiels](02-concepts.md) | états OK/WARNING/CRITICAL/UNKNOWN, SOFT/HARD, périodes, notifications |
| [Lire l'interface web](03-interface-web.md) | brancher Thruk et lire une page de détail |
| [Acquitter et planifier un downtime](04-acquitter-et-planifier-un-downtime.md) | gérer un incident et une maintenance |

## Niveau avancé : structurer et étendre

| Page | Vous saurez… |
|---|---|
| [Modèles et héritage](10-templates-heritage.md) | `use`, `register 0`, héritage multiple, `+` additif |
| [Macros](11-macros.md) | `$HOSTADDRESS$`, `$ARGn$`, `$USER1$`, macros de ressource et personnalisées `_VAR` |
| [Groupes](12-groupes.md) | groupes d'hôtes, de services, de contacts ; organisation des fichiers |
| [Dépendances et escalades](13-dependances-escalades.md) | parents, dépendances de services, escalades |
| [Flapping et event handlers](14-flapping-et-event-handlers.md) | instabilité, auto-remédiation |
| [Checks passifs et commandes externes](15-checks-passifs-commandes-externes.md) | soumettre des résultats, `nagios.cmd`, Livestatus |
| [**Écrire son propre plugin**](16-ecrire-un-plugin.md) | contrat des plugins, exemples shell et Python, `plugins-local/`, tests |
| [Notifications par e-mail](17-notifications.md) | relais SMTP, modes de notification, tests |
| [Périodes de temps](18-periodes-de-temps.md) | syntaxe, exclusions, jours fériés |
| [Recettes](recettes/README.md) | Linux (SSH, NRPE), Windows, SNMP, HTTP/TLS, DNS, bases de données |

## Niveau expert : grandes installations et fonctions avancées

| Page | Vous saurez… |
|---|---|
| [Architecture distribuée](20-architecture-distribuee.md) | realms, pollers et reactionners dédiés (tags), daemons de secours |
| [Business rules](21-business-rules.md) | services métier calculés (`bp_rule`) |
| [`duplicate_foreach`](22-duplicate-foreach.md) | générer un service par disque, interface… |
| [Découverte](23-decouverte.md) | état de l'outil de découverte et alternative |
| [Performances](24-performances.md) | dimensionnement, workers, latence |
| [Rétention](25-retention.md) | conservation de l'état entre redémarrages |
| [Livestatus](26-livestatus.md) | requêtes LQL, historique, commandes |
| [Métriques](27-metriques.md) | perfdata et métriques internes |

## Référence

- [Référence de la configuration](reference/README.md) : toutes les
  directives de chaque objet, les macros et les commandes externes,
  générées depuis le code.
- [Glossaire](../glossaire.md) et [FAQ](../faq.md).
- [Migrer depuis Shinken master](../migration-depuis-shinken-master.md).
