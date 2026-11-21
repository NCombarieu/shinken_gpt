<!-- Page générée par doc/tools/gen_reference.py depuis le code : ne pas modifier à la main. -->


# Service (service)

Directives acceptées dans un bloc `define service { ... }`. Une directive absente prend la valeur par défaut indiquée ; « obligatoire » signifie qu'aucune valeur par défaut n'est prévue : la définir (directement ou par un modèle), sauf si la description indique qu'elle est déduite.

Toute directive commençant par `_` est une macro personnalisée (voir [macros](macros.md)).

| Directive | Type | Défaut | Description |
|---|---|---|---|
| `action_url` | texte |  | URL d'action, affichée dans les interfaces. |
| `active_checks_enabled` | booléen (0/1) | 1 | Exécuter des checks actifs (planifiés par Shinken). |
| `aggregation` | texte |  |  |
| `business_impact` | entier | `2` | Importance métier de 0 (faible) à 5 (critique) ; 2 par défaut. |
| `business_impact_modulations` | liste |  | Modulations de l'impact métier selon la période. |
| `business_rule_downtime_as_ack` | booléen (0/1) | 0 | Traiter les éléments en downtime comme acquittés dans la business rule. |
| `business_rule_host_notification_options` | liste |  |  |
| `business_rule_output_template` | texte |  | Modèle de sortie d'une business rule. |
| `business_rule_service_notification_options` | liste |  |  |
| `business_rule_smart_notifications` | booléen (0/1) | 0 | Ne pas notifier une business rule si ses problèmes sont acquittés ou en downtime. |
| `check_command` | texte | **obligatoire** | Commande de check et ses arguments séparés par « ! » (ex. check_tcp!443). |
| `check_freshness` | booléen (0/1) | 0 | Vérifier que des résultats passifs arrivent bien (fraîcheur). |
| `check_interval` | entier | **obligatoire** | Minutes entre deux checks quand l'état est stable (OK/UP ou HARD). |
| `check_period` | texte | **obligatoire** | Période pendant laquelle les checks actifs sont exécutés. |
| `checkmodulations` | liste |  | Modulations de check (commande différente selon la période). |
| `contact_groups` | liste |  | Groupes de contacts notifiés et autorisés à voir l'objet. |
| `contacts` | liste |  | Contacts notifiés et autorisés à voir l'objet. |
| `custom_views` | liste |  | Vues personnalisées (interfaces web). |
| `default_value` | texte |  | Valeur par défaut des clés de duplicate_foreach. |
| `definition_order` | entier | `100` |  |
| `display_name` | texte |  | Nom affiché dans les interfaces (par défaut le nom de l'objet). |
| `duplicate_foreach` | texte |  | Crée une copie du service pour chaque valeur d'une macro d'hôte (ex. _DISKS). |
| `escalations` | liste |  | Escalades (objets escalation) appliquées à l'objet. |
| `event_handler` | texte |  | Commande lancée à chaque changement d'état (SOFT et HARD). |
| `event_handler_enabled` | booléen (0/1) | 0 | Active le gestionnaire d'événements. |
| `failure_prediction_enabled` | booléen (0/1) | 0 |  |
| `first_notification_delay` | entier | `0` | Minutes d'attente avant la première notification. |
| `flap_detection_enabled` | booléen (0/1) | 1 | Active la détection du flapping. |
| `flap_detection_options` | liste | `o,w,c,u` | États pris en compte pour le flapping (o,d,u pour un hôte ; o,w,c,u pour un service). |
| `freshness_threshold` | entier | `0` | Âge maximal (secondes) du dernier résultat avant de déclencher un check actif. |
| `high_flap_threshold` | entier | `-1` | Seuil haut (%) de changements d'état : au-dessus, début du flapping. |
| `host_dependency_enabled` | booléen (0/1) | 1 | Le service dépend implicitement de son hôte. |
| `host_name` | texte | **obligatoire** | Nom unique de l'hôte (pour un service : hôte(s) auquel il est rattaché). |
| `hostgroup_name` | texte |  | Groupe(s) d'hôtes auxquels le service est appliqué. |
| `icon_image` | texte |  | Image affichée dans les interfaces. |
| `icon_image_alt` | texte |  |  |
| `icon_set` | texte |  | Jeu d'icônes pour les interfaces (server, database, network_service, disk…). |
| `imported_from` | texte | `unknown` | Renseigné automatiquement : fichier source de la définition. |
| `initial_output` | texte |  |  |
| `initial_state` | caractère |  | État supposé avant le premier check (o, d, u pour un hôte ; o, w, c, u pour un service). |
| `is_volatile` | booléen (0/1) | 0 | Service volatil : chaque résultat en problème déclenche une notification. |
| `labels` | liste |  | Étiquettes utilisables dans les business rules (l:<label>). |
| `low_flap_threshold` | entier | `-1` | Seuil bas (%) de changements d'état : sous ce seuil, fin du flapping. |
| `macromodulations` | liste |  | Modulations de macros (valeurs différentes selon la période). |
| `maintenance_check_command` | texte |  |  |
| `maintenance_check_interval` | entier | `0` |  |
| `maintenance_check_period` | texte |  |  |
| `maintenance_checks_enabled` | booléen (0/1) | 0 |  |
| `maintenance_period` | texte |  | Période de maintenance récurrente : l'objet est traité comme en downtime. |
| `maintenance_retry_interval` | entier | `0` |  |
| `max_check_attempts` | entier | `1` | Nombre de checks en échec consécutifs avant de passer en état HARD. |
| `merge_host_contacts` | booléen (0/1) | 0 |  |
| `name` | texte |  | Nom du modèle, utilisé par « use » dans les autres objets. |
| `notes` | texte |  | Texte libre affiché dans les interfaces. |
| `notes_url` | texte |  | URL d'une documentation, affichée dans les interfaces. |
| `notification_interval` | entier | `60` | Minutes entre deux rappels de notification (0 = une seule notification). |
| `notification_options` | liste | `w,u,c,r,f,s` | Événements notifiés (hôte : d,u,r,f,s,n ; service : w,u,c,r,f,s,n). |
| `notification_period` | texte | **obligatoire** | Période pendant laquelle les notifications sont envoyées. |
| `notifications_enabled` | booléen (0/1) | 1 | Active les notifications. |
| `obsess_over_service` | booléen (0/1) | 0 | Directive Nagios (OCSP), sans effet dans Shinken. |
| `parallelize_check` | booléen (0/1) | 1 |  |
| `passive_checks_enabled` | booléen (0/1) | 1 | Accepter les résultats de checks passifs. |
| `poller_tag` | texte | `None` | Seuls les pollers portant ce tag exécutent les checks de l'objet. |
| `priority` | entier | `100` |  |
| `process_perf_data` | booléen (0/1) | 1 | Transmettre les données de performance (perfdata) aux modules. |
| `reactionner_tag` | texte | `None` | Seuls les reactionners portant ce tag exécutent les notifications et event handlers. |
| `register` | booléen (0/1) | 1 | 0 = l'objet est un modèle et n'est pas instancié. |
| `resultmodulations` | liste |  | Modulations du code retour (ex. CRITICAL ramené à WARNING la nuit). |
| `retain_nonstatus_information` | booléen (0/1) | 1 | Conserver commentaires et réglages au redémarrage. |
| `retain_status_information` | booléen (0/1) | 1 | Conserver l'état au redémarrage (nécessite un module de rétention). |
| `retry_interval` | entier | **obligatoire** | Minutes entre deux checks pendant un état SOFT. |
| `service_dependencies` | liste |  | Services dont dépend ce service, sous la forme hôte,service. |
| `service_description` | texte | **obligatoire** | Nom du service, unique pour un hôte. Caractères interdits : voir illegal_object_name_chars. |
| `servicegroups` | liste |  | Groupes de services dont le service fait partie. |
| `snapshot_command` | texte |  | Commande de capture lancée lors d'un problème (fonction avancée). |
| `snapshot_criteria` | liste | `w,c,u` | États qui déclenchent une capture. |
| `snapshot_enabled` | booléen (0/1) | 0 | Active la commande de capture. |
| `snapshot_interval` | entier | `5` | Minutes minimales entre deux captures. |
| `snapshot_period` | texte |  | Période pendant laquelle les captures sont autorisées. |
| `stalking_options` | liste |  | États pour lesquels toute variation de sortie est journalisée. |
| `time_to_orphanage` | entier | `300` | Secondes après lesquelles un check non revenu est déclaré orphelin. |
| `trending_policies` | liste |  |  |
| `trigger` | texte |  | Code de trigger (fonction avancée héritée, non validée en Python 3). |
| `trigger_broker_raise_enabled` | booléen (0/1) | 0 |  |
| `trigger_name` | texte |  | Nom d'un fichier de trigger (fonction avancée héritée, non validée en Python 3). |
| `use` | liste |  | Modèle(s) dont l'objet hérite, séparés par des virgules (le premier est prioritaire). |

Retour à l'[index de la référence](README.md).
