# Recette : serveur Windows

Trois approches, de la plus courante à la plus spécifique.

## 1. NSClient++ en mode NRPE (recommandé)

[NSClient++](https://nsclient.org) est l'agent de supervision Windows de
référence. Il parle le protocole NRPE : Shinken l'interroge avec la même
commande `check_nrpe` que pour Linux.

Sur le serveur Windows, à l'installation de NSClient++ :

- activer le serveur **NRPE** (port 5666) et les modules `CheckSystem`,
  `CheckDisk`, `CheckEventLog` ;
- renseigner **Allowed hosts** avec l'adresse du serveur de supervision ;
- ouvrir le port 5666/TCP du pare-feu Windows pour cette seule adresse.

Puis, dans `nsclient.ini`, déclarer des commandes figées :

```ini
[/settings/NRPE/server]
allowed hosts = 192.0.2.5
insecure = false

[/settings/external scripts/alias]
check_cpu_load = check_cpu "warn=load > 80" "crit=load > 95"
check_mem_used = check_memory "warn=used > 85%" "crit=used > 95%"
check_disk_c = check_drivesize drive=C: "warn=used > 85%" "crit=used > 95%"
check_svc_spooler = check_service service=Spooler
```

Côté Shinken :

```
define host {
    use             generic-host
    host_name       srv-win-01
    address         192.0.2.50
    hostgroups      windows
}

define service {
    use                     generic-service
    hostgroup_name          windows
    service_description     Disque C
    check_command           check_nrpe!check_disk_c
}
```

Test depuis le poller :

```bash
podman-compose exec poller /usr/lib/nagios/plugins/check_nrpe -H 192.0.2.50 -c check_cpu_load
```

> **Note** — Les noms exacts des sections et des commandes varient selon la
> version de NSClient++ : reportez-vous à sa documentation. Le principe
> (commandes figées, `allowed hosts`) reste le même.

### Fichier d'exemple complet

`contrib/checks/nsclient/nsclient.ini` est un point de départ commenté :

- modules et serveur NRPE en TLS, `allow arguments = false` et
  `allow nasty characters = false` ;
- TLS mutuel prêt à activer (`ca`, `verify mode = peer-cert`), avec la
  commande `check_nrpe_tls` côté Shinken ([etc/certs/README.md](../../../etc/certs/README.md)) ;
- des **alias** prêts à l'emploi : `alias_cpu`, `alias_mem`, `alias_disk`
  (tous les disques fixes), `alias_disk_c`, `alias_services` (services
  automatiques arrêtés), `alias_spooler`, `alias_uptime`, `alias_evt_sys`
  (erreurs du journal Système sur la dernière heure) ;
- `timeout = 8` pour les scripts, sous les 9 s de `check_nrpe` : le délai
  de l'agent doit rester inférieur à celui de Shinken (à ajuster ensemble).

> **Attention** — NSClient++ ne gère pas les commentaires en fin de ligne :
> `CheckSystem = enabled ; …` désactive le module. Chaque commentaire va sur
> sa propre ligne.

### Scripts PowerShell maison

Pour ce que les commandes intégrées ne couvrent pas (âge d'une sauvegarde,
état d'une application), un script PowerShell suit le contrat de tout
plugin : **une ligne** `ÉTAT - texte | perfdata` et un code de sortie
0/1/2/3. Modèle : `contrib/checks/nsclient/check_example.ps1` (âge du
dernier fichier d'un dossier de sauvegarde).

1. Copier le script dans `C:\Program Files\NSClient++\scripts\`.
2. Le déclarer avec ses arguments **figés** (autorisé même avec
   `allow arguments = false`, puisqu'ils sont écrits sur l'agent) :
   ```ini
   [/settings/external scripts/wrapped scripts]
   check_backup = check_example.ps1 -MaxAgeHours 26
   ```
3. Le « wrapping » `ps1` du fichier d'exemple lance PowerShell avec
   `-ExecutionPolicy Bypass` : le script s'exécute quelle que soit la
   politique d'exécution de la machine.
4. Côté Shinken : `check_nrpe!check_backup`.

> Ces fichiers suivent la documentation de NSClient++ (0.5/0.6) mais n'ont
> pas pu être testés sur un Windows ; les commandes `check_nrpe` côté
> Shinken, elles, ont été testées contre un agent NRPE 4.

Une machine Windows injoignable depuis Shinken peut aussi **envoyer** ses
résultats : [recette passif SSH](passif-ssh.md#5-client-windows)
(OpenSSH est intégré à Windows).

## 2. SNMP

Windows Server fournit un service SNMP (fonctionnalité « SNMP Service ») qui
expose processeur, mémoire et disques. Voir la [recette SNMP](snmp.md) et
les scripts `check_snmp_load.pl`, `check_snmp_mem.pl`,
`check_snmp_storage.pl` du paquet `nagios-snmp-plugins`. Moins riche que
NSClient++ (pas d'état des services Windows ni du journal d'événements).

## 3. WinRM (sans agent)

Si l'installation d'un agent est exclue, un plugin maison peut interroger
Windows par **WinRM** (PowerShell à distance). Aucun plugin WinRM n'est
fourni : il faut un script Python utilisant la bibliothèque `pywinrm`,
déposé dans `plugins-local/` et une image dérivée qui installe cette
bibliothèque (voir [écrire un plugin](../16-ecrire-un-plugin.md)). Prévoir
un compte de service à droits limités, avec ses identifiants dans
`etc/resource.d/active-directory.cfg` (`$DOMAINUSER$`, `$DOMAINPASSWORD$`),
et HTTPS (port 5986).
