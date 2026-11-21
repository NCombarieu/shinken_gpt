# Recette : serveurs DNS, ping et ports TCP

## Serveur DNS

L'hôte supervisé est le **serveur DNS** ; le service vérifie qu'il résout
correctement un nom. Commandes fournies dans `etc/commands/check_dig.cfg` :

| Commande | Vérifie |
|---|---|
| `check_dig!<nom>` | le serveur répond pour ce nom (avec `dig`) |
| `check_dns!<nom>!<adresse attendue>` | le serveur résout le nom vers l'adresse attendue |

```
define host {
    use                 generic-host
    host_name           dns-01
    address             192.0.2.53
}

define service {
    use                     generic-service
    host_name               dns-01
    service_description     Résolution www
    check_command           check_dns!www.example.com!192.0.2.80
}
```

Test :

```bash
podman-compose exec poller /usr/lib/nagios/plugins/check_dns \
    -H www.example.com -s 192.0.2.53 -a 192.0.2.80
```

## Ping (disponibilité réseau)

`check_host_alive` (check d'hôte par défaut) et `check_ping` utilisent
`check_icmp`, qui envoie de vrais paquets ICMP. Il lui faut la capacité
`NET_RAW`, accordée **au seul conteneur poller** dans `compose.yaml`.

`check_ping` mesure aussi la qualité de la liaison (temps de réponse,
pertes) : adaptez ses seuils dans `etc/commands/check_ping.cfg` ou créez une
variante avec `-w <ms>,<pertes>% -c <ms>,<pertes>%`.

## Port TCP

`check_tcp!<port>` vérifie qu'un port accepte les connexions : base de
données, messagerie (25), annuaire (389)… C'est aussi un bon check d'hôte
pour une machine qui ne répond pas au ping :

```
define host {
    use                 generic-host
    host_name           srv-filtre-01
    address             192.0.2.60
    check_command       check_tcp!22
}
```

Pour vérifier la bannière d'un service texte : `check_tcp -p 25 -e "220"`
(SMTP) ; pour un service chiffré : option `-S`.
