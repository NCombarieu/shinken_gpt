# Thruk : exposition et dépannage

**Public :** exploitant système.

## Publier Thruk en HTTPS

Thruk n'est publié que sur `127.0.0.1:8443` de l'hôte (TLS auto-signé du
conteneur). Un reverse proxy sur l'hôte le publie avec un vrai certificat.
Les principes généraux (certificats, restriction d'accès) sont dans
[reverse proxy TLS](../exploitation/10-reverse-proxy-tls.md) ; voici ce qui
est propre à Thruk.

### Caddy

```
supervision.example.com {
    reverse_proxy https://127.0.0.1:8443 {
        header_up X-Forwarded-Port  "443"
        header_up X-Forwarded-Proto "https"
        transport http {
            tls_insecure_skip_verify
        }
    }
}
```

### nginx

```nginx
location / {
    proxy_pass https://127.0.0.1:8443;
    proxy_ssl_verify off;                  # certificat auto-signé, en local seulement
    proxy_set_header Host              $host;
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Forwarded-Port  443;
    proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
}
```

### Trois règles

1. **Les en-têtes `X-Forwarded-Port` et `X-Forwarded-Proto`.** Sans eux,
   l'Apache du conteneur construit ses redirections (page de connexion,
   retour après connexion) avec **son** port, 8443, injoignable de
   l'extérieur. Symptôme : la page de connexion redirige vers
   `https://supervision.example.com:8443/…`. Les tests avec `curl` et un
   mot de passe peuvent sembler fonctionner alors qu'un navigateur reste
   bloqué.
2. **Une seule authentification.** Thruk a la sienne (formulaire et
   cookie). N'ajoutez pas de `basic_auth` au proxy devant Thruk : les
   requêtes de fond de Thruk (rafraîchissements AJAX) ne renvoient pas
   toujours les identifiants du proxy, d'où des demandes de mot de passe en
   boucle. Pour restreindre l'accès, filtrez plutôt par **adresse source**
   (VPN, réseau d'administration) au niveau du proxy.
3. **`tls_insecure_skip_verify` / `proxy_ssl_verify off` uniquement vers
   `127.0.0.1`.** Le saut de vérification est acceptable parce que le flux
   ne quitte pas la machine.

### Sous-chemin et URL d'OMD

OMD sert Thruk sous `/<site>/thruk/` (par exemple `/demo/thruk/`). Pour
que la racine du domaine mène à Thruk, ajoutez une redirection de `/` vers
`/demo/thruk/` au niveau du proxy ; ne réécrivez pas les chemins internes,
Thruk génère des liens absolus vers `/demo/…`.

## Accès de secours par tunnel SSH

Pour intervenir quand l'authentification de Thruk est cassée (mot de passe
perdu, compte disparu), on peut prévoir un vhost Apache supplémentaire
**sans authentification**, publié **uniquement** sur `127.0.0.1` de
l'hôte, et joint par tunnel SSH :

```apache
# /omd/sites/demo/etc/apache/conf.d/zz_tunnel_admin.conf (monté en lecture seule)
Listen 0.0.0.0:5001
<VirtualHost *:5001>
  SSLEngine off
  SetEnv REMOTE_USER alice        # identité imposée : un administrateur Thruk
  <Location /demo>
    Require all granted
  </Location>
  RewriteEngine On
  RewriteRule ^/$ /demo/thruk/ [R=302,L]
</VirtualHost>
```

Publication : `-p 127.0.0.1:8444:5001`. Depuis votre poste :

```bash
ssh -L 8444:127.0.0.1:8444 serveur-supervision
# puis http://127.0.0.1:8444/ dans le navigateur
```

> **Attention** — Ce vhost donne les droits de `alice` à **quiconque joint
> le port**. Il ne doit jamais être publié ailleurs que sur `127.0.0.1`, ni
> être routé par le reverse proxy. Tout compte local du serveur peut s'y
> connecter : ne l'utilisez que sur un serveur dont vous maîtrisez les
> comptes, ou ne le montez que le temps de l'intervention.

## Dépannage

### Symptômes et causes

| Symptôme | Cause probable | Vérification / correction |
|---|---|---|
| Thruk s'affiche mais **ne montre aucun hôte** | login sans contact Shinken du même nom | [comptes et droits](03-comptes-et-droits.md#2-visibilité--le-login-doit-être-un-contact-shinken) ; requête `AuthUser` |
| Bandeau rouge « backend shinken is not available » | broker arrêté, mauvais réseau, mauvais `peer` | `thruk -l` dans le conteneur ; tests de [connexion](02-connexion-livestatus.md#3-tester-du-plus-bas-au-plus-haut) |
| `Name or service not known` depuis Thruk | Thruk n'est pas sur le réseau des conteneurs Shinken | recréer le conteneur Thruk avec le bon `--network` |
| Un second backend en erreur | moteur local d'OMD encore déclaré | `omd config set CORE none`, retirer le backend local |
| La connexion redirige vers `:8443` | en-têtes `X-Forwarded-*` manquants | règle 1 ci-dessus |
| Demande de mot de passe en boucle | double authentification proxy + Thruk | règle 2 ci-dessus |
| « Password mismatch » alors que le mot de passe n'a pas changé | compte ajouté à la main, perdu au redémarrage | créer les comptes par le playbook drop-in ; `cut -d: -f1 etc/htpasswd` pour lister les comptes présents |
| Les boutons de commande n'apparaissent pas | rôle manquant dans `cgi.cfg`, ou `authorized_for_read_only` | [rôles](03-comptes-et-droits.md#3-rôles--cgicfg) |
| Une commande (ack, downtime) semble sans effet | délai de propagation, ou commande refusée | attendre quelques secondes ; journaux de l'arbiter et du scheduler |
| *Restart the monitoring process* sans effet | commande `restart-shinken` | journal de l'arbiter (voir [dépannage](../exploitation/11-depannage.md)) |
| Pas d'historique, rapports vides | `logstore-null` au lieu de `logstore-sqlite` | [Livestatus](../admin/26-livestatus.md#historique--logstore-sqlite) |
| La carte *Expanded Command* est absente | rôle de configuration manquant | `show_full_commandline = 2` |
| Le conteneur ne redémarre pas après un arrêt brutal | `apache.pid` orphelin | supprimer `tmp/run/apache.pid` du site (tâche du playbook drop-in) |
| Premier démarrage très long, puis échec du service systemd | création du site plus longue que le délai | `TimeoutStartSec=300` dans le quadlet |

### Journaux utiles

```bash
podman logs omd-thruk                                    # démarrage, playbook drop-in
podman exec omd-thruk su - demo -c 'tail -n 50 var/log/thruk.log'
podman exec omd-thruk su - demo -c 'tail -n 50 var/log/apache/error_log'
podman logs shinken-broker 2>&1 | grep -i livestatus     # côté Shinken
```

### Remise à zéro du site

Si le site est irrécupérable : arrêter le conteneur, **sauvegarder** puis
supprimer le volume du site, redémarrer. L'image recrée un site vierge ;
le playbook drop-in et le fichier du backend, montés depuis l'extérieur,
rétablissent la configuration. Les comptes créés à la main, les favoris et
les rapports sont perdus.

```bash
podman stop omd-thruk
podman volume export omd-thruk-site -o omd-thruk-site-avant-raz.tar
podman rm omd-thruk && podman volume rm omd-thruk-site
# puis recréer le conteneur (podman run ou systemctl --user start omd-thruk)
```
