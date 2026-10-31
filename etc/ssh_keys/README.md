# Clés SSH des checks `check_by_ssh`

Ce dossier est monté dans les conteneurs sur `/etc/shinken/ssh_keys/`. La
commande `check_by_ssh` (`etc/commands/check_by_ssh.cfg`) utilise la clé
désignée par la macro `$SSHKEY$` (`etc/resource.d/ssh.cfg`), par défaut
`/etc/shinken/ssh_keys/id_ed25519`.

**Ne versionnez jamais de clé privée.** Seul ce fichier README est suivi par
git ; les clés sont à créer sur le serveur de supervision.

Procédure complète (génération, restriction `command=` côté serveur
supervisé, droits sous Podman rootless) :
[doc/admin/recettes/linux-ssh.md](../../doc/admin/recettes/linux-ssh.md).
