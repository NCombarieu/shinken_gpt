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
