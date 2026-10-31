=======
Shinken
=======

Moteur de supervision compatible Nagios, porté en **Python 3** et déployé
par **conteneurs Podman**.

Cette version reprend `Shinken <https://github.com/naparuba/shinken>`_ 2.4,
dont le développement s'est arrêté en Python 2. Elle conserve le format de
configuration (``define host { ... }``, modèles, macros, ``$USER1$``,
business rules, realms), les plugins Nagios, les commandes externes et
l'interface Livestatus utilisée par Thruk.

Fonctionnalités
===============

- Six daemons spécialisés (arbiter, scheduler, poller, reactionner, broker,
  receiver), distribuables sur plusieurs machines.
- Plugins standard (monitoring-plugins, NRPE, SNMP) et scripts maison
  déposés dans ``plugins-local/``.
- Notifications par e-mail via un relais SMTP.
- Livestatus avec historique SQLite, pour Thruk et les outils compatibles.
- Rétention de l'état (acquittements, downtimes) entre les redémarrages,
  y compris la reprise d'un fichier de Shinken 2.4.
- Tube ``nagios.cmd`` pour les commandes externes.
- Image conteneur versionnée, quadlets systemd, tests de santé.

Démarrage rapide
================

Prérequis : Linux, Podman 4.7 ou plus, ``podman-compose``, ``git``.

.. code-block:: bash

  git clone <url-du-depot> shinken
  cd shinken
  cp .env.example .env                       # fuseau horaire, version, ports
  # adapter etc/contacts/admin.cfg et etc/resource.d/notifications.cfg
  podman-compose build
  podman-compose run --rm --no-deps arbiter check
  podman-compose up -d
  podman-compose exec broker shinken-healthcheck

La page d'état est servie sur ``http://127.0.0.1:8081/`` et Livestatus sur
``127.0.0.1:50000``. Détails : `installation <doc/exploitation/01-installation.md>`_.

Documentation
=============

Toute la documentation est en français dans `doc/ <doc/README.md>`_ :

- `administrateur de la supervision <doc/admin/README.md>`_ : configuration,
  plugins, recettes, du niveau simple au niveau expert ;
- `exploitant système <doc/exploitation/README.md>`_ : installation,
  sauvegarde, mise à jour, sécurité, dépannage ;
- `migration depuis Shinken 2.4 <doc/migration-depuis-shinken-master.md>`_ ;
- `développeur <doc/dev/README.md>`_ et `DEVELOPMENT.md <DEVELOPMENT.md>`_.

Statut du projet
================

- Version 2.4.3, Python 3.11 à 3.13. Les changements sont listés dans le
  `Changelog <Changelog>`_.
- Le remplacement d'une installation Shinken 2.4 se fait en une seule
  bascule (les daemons des deux versions ne communiquent pas) ; plusieurs
  modules tiers de Shinken 2.4 (``webui``, ``graphite``, ``mongodb``…) ne
  sont pas disponibles. Voir le `guide de migration
  <doc/migration-depuis-shinken-master.md>`_.
- Les échanges entre daemons ne sont pas authentifiés : ils doivent rester
  sur un réseau privé (voir `sécurité <doc/exploitation/09-securite.md>`_).

Contribuer
==========

Voir `CONTRIBUTING.rst <CONTRIBUTING.rst>`_. Les anomalies propres à cette
version (Python 3, conteneurs) sont à signaler sur ce dépôt et non sur le
projet d'origine.

Licence
=======

GNU Affero General Public License v3 ou ultérieure (voir ``COPYING``).
