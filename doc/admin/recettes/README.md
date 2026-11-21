# Recettes

Procédures complètes, de la préparation de la cible au test depuis le
poller, pour les cas les plus courants.

| Recette | Méthode | Agent sur la cible |
|---|---|---|
| [Serveur Linux par SSH](linux-ssh.md) | `check_by_ssh` avec clé restreinte | non (compte SSH) |
| [Serveur Linux par NRPE](linux-nrpe.md) | `check_nrpe` | NRPE |
| [Serveur Windows](windows.md) | NSClient++, SNMP ou WinRM | NSClient++ conseillé |
| [Équipement SNMP](snmp.md) | `check_snmp`, scripts SNMP | agent SNMP de l'équipement |
| [Site HTTP/HTTPS et certificat](http-tls.md) | `check_http` | non |
| [API HTTP/REST (JSON)](api-rest.md) | `check_http`, `check_api_json.py` | non (jeton en lecture) |
| [DNS, ping, ports TCP](dns.md) | `check_dns`, `check_icmp`, `check_tcp` | non |
| [Bases de données](bases-de-donnees.md) | `check_mysql`, `check_pgsql` | non (compte en lecture) |
| [Machines qui envoient leurs résultats (passif SSH)](passif-ssh.md) | client `shinken-passive-send` → récepteur `passive-ssh` | un script en cron / tâche planifiée |

Pour choisir une méthode et comprendre quels comptes, clés et secrets
entrent en jeu : [superviser à distance](../06-checks-a-distance.md).

Dans toutes les recettes, les commandes de test s'exécutent **dans le
conteneur poller** (`podman-compose exec poller …`) : c'est de là que
partent les vrais checks, avec son réseau et ses résolutions DNS.
