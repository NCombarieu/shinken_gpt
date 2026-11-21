# Découverte automatique

**Public :** administrateur de la supervision, niveau expert.

> **État dans cette version : non maintenue.** Shinken fournit historiquement
> un outil de découverte réseau (`shinken-discovery`) qui scanne un réseau
> avec `nmap` et génère des définitions d'hôtes à partir de règles. Cet outil
> et ses scripts (`libexec/discovery/`) n'ont pas été validés en Python 3 et
> ne sont pas installés dans l'image conteneur. Ne comptez pas dessus en
> production.

## Ce qui est fourni

| Élément | Rôle |
|---|---|
| `etc/discovery/discovery.cfg` | configuration de l'outil (journal, règles chargées, délai des scripts) |
| `etc/discovery/discovery_rules.cfg` | règles : quel modèle appliquer selon ce qui a été découvert (ports ouverts, système…) |
| `etc/discovery/discovery_runs.cfg` | scripts lancés (scan `nmap`, inventaire VMware) |
| `etc/resource.d/nmap.cfg` | réseaux à scanner (`$NMAPTARGETS$`) et vitesse du scan |

Les objets `discoveryrule` et `discoveryrun` restent acceptés par l'arbiter
(voir la [référence](reference/README.md)).

## Alternative recommandée

Générez la configuration Shinken depuis votre **source de vérité** plutôt
que par scan réseau :

- un inventaire (CMDB, base d'IPAM, fichier tenu par l'équipe) ;
- un petit script qui écrit un fichier `.cfg` par hôte dans
  `etc/hosts/` à partir de cet inventaire, avec les bons modèles et groupes ;
- la vérification `shinken-arbiter -v` puis le rechargement (voir
  [démarrage rapide](01-demarrage-rapide.md)), éventuellement automatisés
  dans votre outil de déploiement.

Combiné aux [modèles](10-templates-heritage.md), aux [groupes](12-groupes.md)
et à [`duplicate_foreach`](22-duplicate-foreach.md), un hôte se décrit en
quelques lignes : la génération reste simple et relisible.

Un scan `nmap` ponctuel reste utile pour **contrôler** l'inventaire :
repérer les machines qui répondent sur le réseau mais ne sont pas
supervisées.
