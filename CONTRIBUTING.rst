Contribuer
==========

Merci de votre intérêt. Avant de proposer une modification :

1. Lisez `DEVELOPMENT.md <DEVELOPMENT.md>`_ : installation de développement,
   tests (``python -m pytest -q test``), conventions de code et de commit.
2. Lisez l'`architecture <doc/dev/architecture.md>`_ et les
   `pièges du portage Python 3 <doc/dev/historique-portage-python3.md>`_
   avant de toucher au cœur des daemons, à la sérialisation ou au module
   Livestatus.
3. Pour un bogue, décrivez la version, la configuration minimale qui le
   reproduit (sans donnée réelle), le comportement attendu et observé, et
   les journaux des daemons concernés.

Règles essentielles :

- un correctif s'accompagne d'un test ;
- code, docstrings et messages de commit en anglais, au format
  conventionnel (``fix(scheduler): ...``) ; documentation en français ;
- aucune donnée personnelle ni information d'infrastructure réelle dans le
  dépôt (exemples : ``example.com``, ``192.0.2.0/24``) ;
- toute évolution visible des utilisateurs est ajoutée au ``Changelog`` et
  à la documentation.

Les anomalies propres au portage Python 3 ou au déploiement Podman sont à
signaler sur ce dépôt, pas sur le projet Shinken d'origine.
