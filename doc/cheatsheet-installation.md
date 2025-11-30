# Shinken installation & launch cheat sheet

Use this as a concise checklist to set up and start Shinken from a source checkout.

## 1) Préparation système
- Assurez-vous d'avoir Python et `pip` disponibles (les binaires Shinken sont fournis par `setup.py`).
- Créez les répertoires système attendus si vous n'utilisez pas de paquets OS :
  ```bash
  sudo mkdir -p /etc/shinken /var/lib/shinken /var/log/shinken /var/run/shinken
  sudo chown -R $USER:$USER /etc/shinken /var/lib/shinken /var/log/shinken /var/run/shinken
  ```
- Sur RHEL/CentOS, vous pouvez utiliser le script fourni pour créer l'arborescence et le compte système `shinken` :
  ```bash
  sudo contrib/setup_shinken_paths_rhel.sh
  ```

## 2) Récupération des sources
```bash
git clone https://github.com/naparuba/shinken.git
cd shinken
```

## 3) Installation Python (bibliothèques + scripts)
- Installation classique depuis la racine du dépôt :
  ```bash
  pip install .
  ```
- Pour mettre à jour une installation existante sans toucher à la configuration :
  ```bash
  python setup.py install --update
  ```

## 4) Déployer la configuration et les modules
- Copiez les exemples de configuration fournis vers le chemin système attendu :
  ```bash
  sudo rsync -a etc/ /etc/shinken/
  ```
- Copiez les modules et ressources vers `/var/lib/shinken` si vous ne passez pas par des paquets :
  ```bash
  sudo rsync -a libexec/ modules/ share/ /var/lib/shinken/
  ```

## 5) Lancement des démons
- Avec le script d'init (mode debug possible) :
  ```bash
  sudo /etc/init.d/shinken start
  # ou pour le debug
  sudo /etc/init.d/shinken -d start
  ```
- Pour activer le service au démarrage (selon la distribution) :
  ```bash
  # RHEL/CentOS
  sudo chkconfig --add shinken
  sudo chkconfig shinken on

  # Debian/Ubuntu
  sudo update-rc.d shinken defaults 20
  ```

## 6) Emplacements utiles
- Configuration : `/etc/shinken`
- Logs par défaut : `/var/log/shinken`
- Données/modules : `/var/lib/shinken`
- PID/lock : `/var/run/shinken`

## 7) Vérifications rapides
- Vérifiez que les fichiers de configuration sont bien présents dans `/etc/shinken`.
- Surveillez les logs lors du premier démarrage pour repérer d'éventuelles erreurs :
  ```bash
  tail -f /var/log/shinken/*
  ```
- Si vous migrez depuis Nagios, aucune modification de configuration n'est nécessaire tant que vous gardez la syntaxe existante.
