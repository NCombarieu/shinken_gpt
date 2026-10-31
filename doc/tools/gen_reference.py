#!/usr/bin/env python3
"""Generate the configuration reference pages of doc/admin/reference/.

The lists of directives, macros and external commands are read from the
code itself (``properties`` of the configuration objects, ``macros`` of the
macro resolver and of the objects, ``ExternalCommandManager.commands``), so
the reference cannot drift from what the arbiter really accepts. Short French
descriptions of the most common directives are maintained in DESCRIPTIONS
below.

Usage (from the repository root, with the package importable)::

    python doc/tools/gen_reference.py            # rewrite the pages
    python doc/tools/gen_reference.py --check    # exit 1 if a page is stale
"""

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from shinken.external_command import ExternalCommandManager  # noqa: E402
from shinken.macroresolver import MacroResolver  # noqa: E402
from shinken.objects.config import Config  # noqa: E402
from shinken.property import UnusedProp, none_object  # noqa: E402

OUT_DIR = os.path.join(ROOT, 'doc', 'admin', 'reference')

HEADER = ("<!-- Page générée par doc/tools/gen_reference.py depuis le code : "
          "ne pas modifier à la main. -->\n\n")

TYPE_NAMES = {
    'StringProp': 'texte',
    'ToGuessProp': 'texte',
    'PathProp': 'chemin',
    'ConfigPathProp': 'chemin',
    'AddrProp': 'adresse',
    'IntegerProp': 'entier',
    'FloatProp': 'décimal',
    'BoolProp': 'booléen (0/1)',
    'CharProp': 'caractère',
    'ListProp': 'liste',
    'IntListProp': 'liste d\'entiers',
    'DictProp': 'dictionnaire',
    'LogLevelProp': 'niveau de log',
    'UnusedProp': 'ignorée',
}

# Object types documented, in the order of the index page, with a title.
OBJECTS = [
    ('host', 'Hôte (host)'),
    ('service', 'Service (service)'),
    ('contact', 'Contact (contact)'),
    ('command', 'Commande (command)'),
    ('timeperiod', 'Période de temps (timeperiod)'),
    ('hostgroup', "Groupe d'hôtes (hostgroup)"),
    ('servicegroup', 'Groupe de services (servicegroup)'),
    ('contactgroup', 'Groupe de contacts (contactgroup)'),
    ('notificationway', 'Mode de notification (notificationway)'),
    ('hostdependency', "Dépendance d'hôte (hostdependency)"),
    ('servicedependency', 'Dépendance de service (servicedependency)'),
    ('escalation', 'Escalade (escalation)'),
    ('hostescalation', "Escalade d'hôte (hostescalation)"),
    ('serviceescalation', 'Escalade de service (serviceescalation)'),
    ('realm', 'Realm (realm)'),
    ('module', 'Module (module)'),
    ('arbiter', 'Daemon arbiter (arbiter)'),
    ('scheduler', 'Daemon scheduler (scheduler)'),
    ('poller', 'Daemon poller (poller)'),
    ('reactionner', 'Daemon reactionner (reactionner)'),
    ('broker', 'Daemon broker (broker)'),
    ('receiver', 'Daemon receiver (receiver)'),
    ('checkmodulation', 'Modulation de check (checkmodulation)'),
    ('macromodulation', 'Modulation de macros (macromodulation)'),
    ('resultmodulation', 'Modulation de résultat (resultmodulation)'),
    ('businessimpactmodulation', "Modulation d'impact métier (businessimpactmodulation)"),
    ('hostextinfo', "Informations étendues d'hôte (hostextinfo)"),
    ('serviceextinfo', 'Informations étendues de service (serviceextinfo)'),
    ('discoveryrule', 'Règle de découverte (discoveryrule)'),
    ('discoveryrun', 'Exécution de découverte (discoveryrun)'),
]

# Short French descriptions of the most used directives. Key: directive name,
# valid for every object type that has it, unless a "type:directive" key is
# more specific.
DESCRIPTIONS = {
    # common
    'use': "Modèle(s) dont l'objet hérite, séparés par des virgules (le premier est prioritaire).",
    'name': "Nom du modèle, utilisé par « use » dans les autres objets.",
    'register': "0 = l'objet est un modèle et n'est pas instancié.",
    'alias': 'Nom long affiché dans les interfaces.',
    'notes': 'Texte libre affiché dans les interfaces.',
    'notes_url': "URL d'une documentation, affichée dans les interfaces.",
    'action_url': "URL d'action, affichée dans les interfaces.",
    'icon_image': "Image affichée dans les interfaces.",
    'icon_set': "Jeu d'icônes pour les interfaces (server, database, network_service, disk…).",
    'realm': "Realm auquel l'objet appartient (supervision distribuée).",
    'imported_from': 'Renseigné automatiquement : fichier source de la définition.',
    # host / service
    'host_name': "Nom unique de l'hôte (pour un service : hôte(s) auquel il est rattaché).",
    'address': "Adresse IP ou nom DNS utilisé par les checks ($HOSTADDRESS$).",
    'address:host': "Adresse IP ou nom DNS utilisé par les checks ($HOSTADDRESS$). Déduite de host_name si absente.",
    'alias:host': 'Nom long affiché dans les interfaces. Déduit de host_name si absent.',
    'display_name': "Nom affiché dans les interfaces (par défaut le nom de l'objet).",
    'parents': "Hôtes parents dans la topologie réseau : si tous sont DOWN, l'hôte devient UNREACHABLE.",
    'hostgroups': "Groupes d'hôtes dont l'hôte fait partie.",
    'hostgroup_name': "Groupe(s) d'hôtes auxquels le service est appliqué.",
    'service_description': "Nom du service, unique pour un hôte. Caractères interdits : voir illegal_object_name_chars.",
    'servicegroups': 'Groupes de services dont le service fait partie.',
    'check_command': "Commande de check et ses arguments séparés par « ! » (ex. check_tcp!443).",
    'check_interval': 'Minutes entre deux checks quand l\'état est stable (OK/UP ou HARD).',
    'retry_interval': 'Minutes entre deux checks pendant un état SOFT.',
    'max_check_attempts': 'Nombre de checks en échec consécutifs avant de passer en état HARD.',
    'check_period': 'Période pendant laquelle les checks actifs sont exécutés.',
    'active_checks_enabled': 'Exécuter des checks actifs (planifiés par Shinken).',
    'passive_checks_enabled': 'Accepter les résultats de checks passifs.',
    'check_freshness': 'Vérifier que des résultats passifs arrivent bien (fraîcheur).',
    'freshness_threshold': 'Âge maximal (secondes) du dernier résultat avant de déclencher un check actif.',
    'obsess_over_host': 'Directive Nagios (OCHP), sans effet dans Shinken.',
    'obsess_over_service': 'Directive Nagios (OCSP), sans effet dans Shinken.',
    'event_handler': 'Commande lancée à chaque changement d\'état (SOFT et HARD).',
    'event_handler_enabled': 'Active le gestionnaire d\'événements.',
    'flap_detection_enabled': 'Active la détection du flapping.',
    'flap_detection_options': 'États pris en compte pour le flapping (o,d,u pour un hôte ; o,w,c,u pour un service).',
    'low_flap_threshold': 'Seuil bas (%) de changements d\'état : sous ce seuil, fin du flapping.',
    'high_flap_threshold': 'Seuil haut (%) de changements d\'état : au-dessus, début du flapping.',
    'process_perf_data': 'Transmettre les données de performance (perfdata) aux modules.',
    'retain_status_information': 'Conserver l\'état au redémarrage (nécessite un module de rétention).',
    'retain_nonstatus_information': 'Conserver commentaires et réglages au redémarrage.',
    'contacts': 'Contacts notifiés et autorisés à voir l\'objet.',
    'contact_groups': 'Groupes de contacts notifiés et autorisés à voir l\'objet.',
    'notification_interval': 'Minutes entre deux rappels de notification (0 = une seule notification).',
    'first_notification_delay': 'Minutes d\'attente avant la première notification.',
    'notification_period': 'Période pendant laquelle les notifications sont envoyées.',
    'notification_options': 'Événements notifiés (hôte : d,u,r,f,s,n ; service : w,u,c,r,f,s,n).',
    'notifications_enabled': 'Active les notifications.',
    'stalking_options': 'États pour lesquels toute variation de sortie est journalisée.',
    'is_volatile': 'Service volatil : chaque résultat en problème déclenche une notification.',
    'initial_state': 'État supposé avant le premier check (o, d, u pour un hôte ; o, w, c, u pour un service).',
    'business_impact': 'Importance métier de 0 (faible) à 5 (critique) ; 2 par défaut.',
    'maintenance_period': 'Période de maintenance récurrente : l\'objet est traité comme en downtime.',
    'poller_tag': 'Seuls les pollers portant ce tag exécutent les checks de l\'objet.',
    'reactionner_tag': 'Seuls les reactionners portant ce tag exécutent les notifications et event handlers.',
    'escalations': 'Escalades (objets escalation) appliquées à l\'objet.',
    'service_dependencies': 'Services dont dépend ce service, sous la forme hôte,service.',
    'host_dependency_enabled': 'Le service dépend implicitement de son hôte.',
    'duplicate_foreach': 'Crée une copie du service pour chaque valeur d\'une macro d\'hôte (ex. _DISKS).',
    'default_value': 'Valeur par défaut des clés de duplicate_foreach.',
    'trigger': 'Code de trigger (fonction avancée héritée, non validée en Python 3).',
    'trigger_name': 'Nom d\'un fichier de trigger (fonction avancée héritée, non validée en Python 3).',
    'checkmodulations': 'Modulations de check (commande différente selon la période).',
    'macromodulations': 'Modulations de macros (valeurs différentes selon la période).',
    'resultmodulations': 'Modulations du code retour (ex. CRITICAL ramené à WARNING la nuit).',
    'business_impact_modulations': 'Modulations de l\'impact métier selon la période.',
    'labels': 'Étiquettes utilisables dans les business rules (l:<label>).',
    'service_overrides': 'Redéfinit une directive d\'un service hérité pour cet hôte (service,directive valeur).',
    'service_excludes': 'Services hérités à ne pas créer sur cet hôte.',
    'service_includes': 'Seuls ces services hérités sont créés sur cet hôte.',
    'business_rule_output_template': 'Modèle de sortie d\'une business rule.',
    'business_rule_smart_notifications': 'Ne pas notifier une business rule si ses problèmes sont acquittés ou en downtime.',
    'business_rule_downtime_as_ack': 'Traiter les éléments en downtime comme acquittés dans la business rule.',
    'time_to_orphanage': 'Secondes après lesquelles un check non revenu est déclaré orphelin.',
    'custom_views': 'Vues personnalisées (interfaces web).',
    'snapshot_command': 'Commande de capture lancée lors d\'un problème (fonction avancée).',
    'snapshot_enabled': 'Active la commande de capture.',
    'snapshot_period': 'Période pendant laquelle les captures sont autorisées.',
    'snapshot_criteria': 'États qui déclenchent une capture.',
    'snapshot_interval': 'Minutes minimales entre deux captures.',
    # contact
    'contact_name': 'Identifiant unique du contact ; doit correspondre au login dans Thruk.',
    'contactgroups': 'Groupes de contacts dont le contact fait partie.',
    'email': 'Adresse e-mail ($CONTACTEMAIL$).',
    'pager': 'Numéro de téléphone ou de pager ($CONTACTPAGER$).',
    'password': 'Mot de passe pour les interfaces qui s\'authentifient auprès de Shinken.',
    'is_admin': 'Droits d\'administration dans les interfaces qui l\'exploitent.',
    'can_submit_commands': 'Autorise l\'envoi de commandes (acquittement, downtime…) depuis les interfaces.',
    'notificationways': 'Modes de notification (objets notificationway) du contact.',
    'host_notifications_enabled': 'Active les notifications d\'hôte pour ce contact.',
    'service_notifications_enabled': 'Active les notifications de service pour ce contact.',
    'host_notification_period': 'Période des notifications d\'hôte.',
    'service_notification_period': 'Période des notifications de service.',
    'host_notification_options': 'Événements d\'hôte notifiés (d,u,r,f,s,n).',
    'service_notification_options': 'Événements de service notifiés (w,u,c,r,f,s,n).',
    'host_notification_commands': 'Commandes de notification d\'hôte.',
    'service_notification_commands': 'Commandes de notification de service.',
    'min_business_impact': 'Impact métier minimal des objets pour lesquels ce contact ou ce mode est notifié.',
    'notificationway_name': 'Nom unique du mode de notification.',
    # command
    'command_name': 'Nom unique de la commande, utilisé dans check_command, event_handler…',
    'command_line': 'Ligne exécutée ; macros ($HOSTADDRESS$, $ARG1$, $USER1$…) remplacées avant exécution.',
    'module_type': 'Fait exécuter la commande par un module du poller ou du reactionner au lieu d\'un processus.',
    'timeout': 'Durée maximale d\'exécution en secondes (-1 = valeur globale).',
    'enable_environment_macros': 'Exporter les macros en variables d\'environnement pour cette commande.',
    # timeperiod
    'timeperiod_name': 'Nom unique de la période.',
    'exclude': 'Périodes retirées de celle-ci (ex. jours fériés).',
    'dateranges': 'Plages de dates et d\'heures (lignes « monday 09:00-18:00 », « 2027-03-29 00:00-24:00 »…).',
    # groups
    'hostgroup_name:hostgroup': 'Nom unique du groupe.',
    'servicegroup_name': 'Nom unique du groupe de services.',
    'contactgroup_name': 'Nom unique du groupe de contacts.',
    'members': 'Membres du groupe (pour un groupe de services : couples hôte,service).',
    'hostgroup_members': 'Groupes d\'hôtes inclus dans ce groupe.',
    'servicegroup_members': 'Groupes de services inclus dans ce groupe.',
    'contactgroup_members': 'Groupes de contacts inclus dans ce groupe.',
    # dependencies
    'dependent_host_name': 'Hôte(s) dépendant(s).',
    'dependent_hostgroup_name': 'Groupe(s) d\'hôtes dépendant(s).',
    'dependent_service_description': 'Service(s) dépendant(s).',
    'execution_failure_criteria': 'États du maître qui suspendent les checks du dépendant (o,d,u,p,n ou o,w,u,c,p,n).',
    'notification_failure_criteria': 'États du maître qui suspendent les notifications du dépendant.',
    'dependency_period': 'Période pendant laquelle la dépendance s\'applique.',
    'inherits_parent': 'Le dépendant hérite aussi des dépendances du maître.',
    # escalations
    'escalation_name': 'Nom unique de l\'escalade.',
    'first_notification': 'Numéro de la première notification concernée.',
    'last_notification': 'Numéro de la dernière notification concernée (0 = sans fin).',
    'first_notification_time': 'Minutes de problème à partir desquelles l\'escalade s\'applique.',
    'last_notification_time': 'Minutes de problème après lesquelles l\'escalade cesse (0 = sans fin).',
    'escalation_period': 'Période pendant laquelle l\'escalade s\'applique.',
    'escalation_options': 'États concernés par l\'escalade.',
    # realm / daemons
    'realm_name': 'Nom unique du realm.',
    'realm_members': 'Sous-realms de ce realm.',
    'default': 'Realm par défaut des objets qui n\'en précisent pas.',
    'port': 'Port TCP du daemon.',
    'spare': '1 = daemon de secours, activé si le daemon principal tombe.',
    'manage_sub_realms': 'Prend aussi en charge les sous-realms.',
    'manage_arbiters': 'Ce broker reçoit aussi les broks de l\'arbiter.',
    'modules': 'Modules chargés (noms définis par module_name).',
    'poller_tags': 'Tags traités par ce poller (« None » = objets sans tag).',
    'reactionner_tags': 'Tags traités par ce reactionner.',
    'passive': 'Le daemon ne se connecte pas aux schedulers : c\'est le scheduler qui lui pousse le travail.',
    'min_workers': 'Nombre minimal de processus d\'exécution (0 = un par processeur).',
    'max_workers': 'Nombre maximal de processus d\'exécution (0 = un par processeur).',
    'processes_by_worker': 'Nombre de checks traités en parallèle par processus.',
    'polling_interval': 'Secondes entre deux demandes de travail au scheduler.',
    'use_ssl': 'Chiffre les échanges avec ce daemon (nécessite une vraie PKI).',
    'hard_ssl_name_check': 'Vérifie le nom du certificat présenté.',
    'weight': 'Poids du scheduler dans la répartition des hôtes.',
    'skip_initial_broks': 'Ne pas envoyer l\'état initial complet aux brokers.',
    'satellitemap': 'Adresses à utiliser pour joindre les satellites (NAT).',
    'check_interval:scheduler': 'Secondes entre deux tests de vie du daemon par l\'arbiter.',
    'max_check_attempts:scheduler': 'Tests de vie en échec avant de déclarer le daemon mort.',
    'timeout:scheduler': 'Délai (secondes) d\'un test de vie.',
    'data_timeout': 'Délai (secondes) des envois de données.',
    'direct_routing': 'Le receiver envoie directement les commandes au scheduler qui gère l\'hôte.',
    'accept_passive_unknown_check_results': 'Accepter les résultats passifs d\'hôtes ou services inconnus.',
    # module
    'module_name': 'Nom unique du module, référencé par la directive modules des daemons.',
}
for _daemon in ('arbiter', 'poller', 'reactionner', 'broker', 'receiver'):
    for _key in ('check_interval', 'max_check_attempts', 'timeout'):
        DESCRIPTIONS['%s:%s' % (_key, _daemon)] = DESCRIPTIONS['%s:scheduler' % _key]

# shinken.cfg (Config.properties) descriptions
CONFIG_DESCRIPTIONS = {
    'cfg_dir': 'Dossier dont tous les fichiers .cfg sont chargés (récursivement).',
    'cfg_file': 'Fichier de configuration supplémentaire à charger.',
    'resource_file': 'Fichier de macros $USERn$ (on préfère cfg_dir=resource.d).',
    'retention_update_interval': 'Minutes entre deux sauvegardes de l\'état par le module de rétention (0 = seulement à l\'arrêt).',
    'max_service_check_spread': 'Minutes sur lesquelles sont étalés les premiers checks de services au démarrage.',
    'max_host_check_spread': 'Minutes sur lesquelles sont étalés les premiers checks d\'hôtes au démarrage.',
    'service_check_timeout': 'Durée maximale (s) d\'un check de service.',
    'host_check_timeout': 'Durée maximale (s) d\'un check d\'hôte.',
    'event_handler_timeout': 'Durée maximale (s) d\'un event handler.',
    'notification_timeout': 'Durée maximale (s) d\'une commande de notification.',
    'timeout_exit_status': 'Code retour attribué à un check qui dépasse son délai (2 = CRITICAL).',
    'flap_history': 'Nombre d\'états mémorisés pour la détection du flapping.',
    'max_plugins_output_length': 'Taille maximale (octets) de la sortie conservée d\'un plugin.',
    'enable_problem_impacts_states_change': 'Les éléments impactés par un parent en panne passent en UNREACHABLE/UNKNOWN.',
    'disable_old_nagios_parameters_whining': '1 = ne plus avertir des paramètres Nagios ignorés.',
    'use_timezone': 'Fuseau horaire des daemons (ex. Europe/Paris).',
    'enable_environment_macros': 'Exporter les macros en variables d\'environnement des plugins (coûteux).',
    'log_initial_states': 'Journaliser l\'état initial de chaque objet au démarrage.',
    'no_event_handlers_during_downtimes': 'Ne pas lancer d\'event handler pendant un downtime.',
    'pack_distribution_file': 'Fichier mémorisant la répartition des hôtes entre schedulers.',
    'command_file': 'Tube nommé des commandes externes (nagios.cmd), créé par le module named-pipe.',
    'lock_file': 'Fichier PID de l\'arbiter.',
    'local_log': 'Journal local de l\'arbiter.',
    'log_level': 'Niveau de journalisation de l\'arbiter.',
    'modules_dir': 'Répertoire des modules.',
    'daemon_enabled': '0 = ne pas lancer l\'arbiter.',
    'use_ssl': 'Chiffrer les échanges de l\'arbiter.',
    'http_backend': 'Conservé pour compatibilité : le serveur HTTP est toujours Cheroot.',
    'enable_notifications': 'Interrupteur global des notifications.',
    'execute_service_checks': 'Interrupteur global des checks actifs de services.',
    'execute_host_checks': 'Interrupteur global des checks actifs d\'hôtes.',
    'accept_passive_service_checks': 'Interrupteur global des résultats passifs de services.',
    'accept_passive_host_checks': 'Interrupteur global des résultats passifs d\'hôtes.',
    'enable_event_handlers': 'Interrupteur global des event handlers.',
    'enable_flap_detection': 'Interrupteur global de la détection du flapping.',
    'check_external_commands': 'Accepter les commandes externes.',
    'log_external_commands': 'Journaliser les commandes externes reçues.',
    'log_notifications': 'Journaliser les notifications.',
    'log_passive_checks': 'Journaliser les résultats passifs.',
    'low_service_flap_threshold': 'Seuil bas global du flapping des services (%).',
    'high_service_flap_threshold': 'Seuil haut global du flapping des services (%).',
    'low_host_flap_threshold': 'Seuil bas global du flapping des hôtes (%).',
    'high_host_flap_threshold': 'Seuil haut global du flapping des hôtes (%).',
    'check_service_freshness': 'Interrupteur global de la vérification de fraîcheur des services.',
    'check_host_freshness': 'Interrupteur global de la vérification de fraîcheur des hôtes.',
    'service_freshness_check_interval': 'Secondes entre deux vérifications de fraîcheur des services.',
    'host_freshness_check_interval': 'Secondes entre deux vérifications de fraîcheur des hôtes.',
    'interval_length': 'Durée en secondes d\'une « unité de temps » des intervalles (60 par défaut).',
    'illegal_object_name_chars': 'Caractères interdits dans les noms d\'objets.',
    'illegal_macro_output_chars': 'Caractères retirés des macros de sortie avant usage dans une commande.',
    'statsd_enabled': 'Envoi des statistiques internes vers StatsD.',
    'statsd_host': 'Serveur StatsD.',
    'statsd_port': 'Port UDP StatsD.',
    'statsd_prefix': 'Préfixe des métriques.',
    'accept_passive_unknown_check_results': 'Accepter les résultats passifs d\'objets inconnus (crée un brok).',
    'max_concurrent_checks': 'Ignorée par Shinken (la charge se règle dans les pollers).',
    'conflict_policy': 'Non prise en charge dans cette version (directive Shinken 2.4.4).',
}


def describe(obj_type, prop_name):
    return (DESCRIPTIONS.get('%s:%s' % (prop_name, obj_type))
            or DESCRIPTIONS.get(prop_name, ''))


def fmt_default(prop):
    if isinstance(prop, UnusedProp):
        return ''
    if prop.default is none_object:
        return '**obligatoire**'
    value = prop.default
    if isinstance(value, bool):
        return '1' if value else '0'
    if value is None:
        return ''
    if isinstance(value, (list, tuple)):
        value = ','.join(str(v) for v in value)
    if isinstance(value, dict):
        return ''
    value = str(value)
    if value == '':
        return ''
    return '`%s`' % value.replace('|', '\\|').replace('`', "'")


def esc(text):
    return text.replace('|', '\\|')


def prop_rows(obj_type, properties, descriptions=None):
    rows = []
    for name in sorted(properties):
        prop = properties[name]
        if name.startswith('_') or name in ('id',):
            continue
        type_name = TYPE_NAMES.get(prop.__class__.__name__, prop.__class__.__name__)
        if descriptions is not None:
            desc = descriptions.get(name, '')
        else:
            desc = describe(obj_type, name)
        if isinstance(prop, UnusedProp):
            desc = desc or 'Paramètre Nagios accepté pour compatibilité, sans effet dans Shinken.'
        rows.append('| `%s` | %s | %s | %s |' % (name, type_name, fmt_default(prop), esc(desc)))
    return rows


def page_object(obj_type, title, cls):
    lines = [HEADER, '# %s\n' % title,
             "Directives acceptées dans un bloc `define %s { ... }`. "
             "Une directive absente prend la valeur par défaut indiquée ; "
             "« obligatoire » signifie qu'aucune valeur par défaut n'est prévue : la définir "
             "(directement ou par un modèle), sauf si la description indique qu'elle est déduite.\n"
             % obj_type,
             "Toute directive commençant par `_` est une macro personnalisée "
             "(voir [macros](macros.md)).\n" if obj_type in ('host', 'service', 'contact') else '',
             '| Directive | Type | Défaut | Description |',
             '|---|---|---|---|']
    lines += prop_rows(obj_type, cls.properties)
    lines.append('\nRetour à l\'[index de la référence](README.md).')
    return '\n'.join(line for line in lines if line != '') + '\n'


def page_config():
    lines = [HEADER, '# Directives de shinken.cfg\n',
             "Paramètres globaux acceptés dans `shinken.cfg` (et dans tout fichier chargé "
             "en dehors d'un bloc `define`). Les directives marquées « ignorée » sont "
             "des paramètres Nagios acceptés pour compatibilité mais sans effet.\n",
             '| Directive | Type | Défaut | Description |',
             '|---|---|---|---|']
    lines += prop_rows('config', Config.properties, CONFIG_DESCRIPTIONS)
    lines.append('\nRetour à l\'[index de la référence](README.md).')
    return '\n'.join(lines) + '\n'


ARG_NAMES = {
    'host': '<host_name>',
    'service': '<host_name>;<service_description>',
    'host_group': '<hostgroup_name>',
    'service_group': '<servicegroup_name>',
    'contact': '<contact_name>',
    'contact_group': '<contactgroup_name>',
    'time_period': '<timeperiod_name>',
    'command': '<command_name>',
    'author': '<auteur>',
    'to_int': '<entier>',
    'to_bool': '<0|1>',
    None: '<valeur>',
}


def page_external_commands():
    lines = [HEADER, '# Commandes externes\n',
             "Commandes reconnues par Shinken (`shinken/external_command.py`). Elles "
             "s'envoient sous la forme `[<horodatage>] NOM;arg1;arg2;...` : par Livestatus "
             "(`COMMAND [...]`), par le tube nommé `nagios.cmd` ou depuis Thruk. Voir "
             "[checks passifs et commandes externes](../15-checks-passifs-commandes-externes.md).\n",
             "« Globale » : la commande concerne toute la supervision et est traitée par "
             "l'arbiter ou envoyée à tous les schedulers.\n",
             '| Commande | Arguments | Globale |',
             '|---|---|---|']
    for name in sorted(ExternalCommandManager.commands):
        entry = ExternalCommandManager.commands[name]
        args = ';'.join(ARG_NAMES.get(a, '<%s>' % a) for a in entry['args'])
        args = args.replace('|', '\\|')
        lines.append('| `%s` | %s | %s |' % (name, '`%s`' % args if args else '—',
                                             'oui' if entry.get('global') else ''))
    lines.append('\nRetour à l\'[index de la référence](README.md).')
    return '\n'.join(lines) + '\n'


def page_macros():
    lines = [HEADER, '# Macros\n',
             "Les macros `$NOM$` sont remplacées dans les lignes de commande avant "
             "exécution. Voir [macros](../11-macros.md) pour leur usage.\n",
             '## Macros sans objet (globales)\n',
             '| Macro | Source |', '|---|---|']
    for name in sorted(MacroResolver.macros):
        lines.append('| `$%s$` | %s |' % (name, MacroResolver.macros[name]))
    lines += ['',
              '## Autres macros spéciales\n',
              '| Macro | Valeur |', '|---|---|',
              '| `$ARG1$` … `$ARGn$` | Arguments passés à la commande après « ! » dans check_command. |',
              '| `$USER1$` … `$USERn$`, `$NOM$` | Macros de ressource définies dans `resource.d/*.cfg`. |',
              '| `$_HOSTNOM$`, `$_SERVICENOM$`, `$_CONTACTNOM$` | Macro personnalisée `_NOM` de l\'hôte, du service ou du contact. |',
              '| `$HOSTSTATE:hôte$`, `$SERVICESTATE:hôte:service$` | Macro « à la demande » : valeur prise sur un autre objet. |',
              '']
    from shinken.objects.config import Config as _C
    for obj_type, title in (('host', 'hôte'), ('service', 'service'), ('contact', 'contact'),
                            ('hostgroup', "groupe d'hôtes"), ('servicegroup', 'groupe de services'),
                            ('contactgroup', 'groupe de contacts')):
        cls = _C.types_creations[obj_type][0]
        lines += ['## Macros de %s\n' % title, '| Macro | Directive ou valeur source |', '|---|---|']
        for name in sorted(cls.macros):
            lines.append('| `$%s$` | `%s` |' % (name, cls.macros[name]))
        lines.append('')
    lines.append('Retour à l\'[index de la référence](README.md).')
    return '\n'.join(lines) + '\n'


def page_index():
    lines = [HEADER, '# Référence de la configuration\n',
             "Pages générées depuis le code de cette version. Pour comprendre les "
             "concepts, commencer par le [parcours administrateur](../README.md).\n",
             '- [Directives de shinken.cfg](directives-shinken-cfg.md)',
             '- [Macros](macros.md)',
             '- [Commandes externes](commandes-externes.md)',
             '- [Glossaire](../../glossaire.md) et [FAQ](../../faq.md)',
             '', '## Objets de configuration\n']
    for obj_type, title in OBJECTS:
        lines.append('- [%s](objet-%s.md)' % (title, obj_type))
    lines.append('\nRégénérer ces pages : `python doc/tools/gen_reference.py`.')
    return '\n'.join(lines) + '\n'


def build_pages():
    pages = {'README.md': page_index(),
             'directives-shinken-cfg.md': page_config(),
             'commandes-externes.md': page_external_commands(),
             'macros.md': page_macros()}
    for obj_type, title in OBJECTS:
        cls = Config.types_creations[obj_type][0]
        pages['objet-%s.md' % obj_type] = page_object(obj_type, title, cls)
    return pages


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--check', action='store_true',
                        help='do not write, exit 1 if a generated page differs')
    args = parser.parse_args()
    os.makedirs(OUT_DIR, exist_ok=True)
    stale = []
    for name, content in build_pages().items():
        path = os.path.join(OUT_DIR, name)
        current = None
        if os.path.exists(path):
            with open(path, encoding='utf-8') as handle:
                current = handle.read()
        if current == content:
            continue
        stale.append(name)
        if not args.check:
            with open(path, 'w', encoding='utf-8') as handle:
                handle.write(content)
    if args.check and stale:
        print('Stale reference pages: %s' % ', '.join(stale))
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
