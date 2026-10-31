<!-- Page générée par doc/tools/gen_reference.py depuis le code : ne pas modifier à la main. -->


# Commandes externes

Commandes reconnues par Shinken (`shinken/external_command.py`). Elles s'envoient sous la forme `[<horodatage>] NOM;arg1;arg2;...` : par Livestatus (`COMMAND [...]`), par le tube nommé `nagios.cmd` ou depuis Thruk. Voir [checks passifs et commandes externes](../15-checks-passifs-commandes-externes.md).

« Globale » : la commande concerne toute la supervision et est traitée par l'arbiter ou envoyée à tous les schedulers.

| Commande | Arguments | Globale |
|---|---|---|
| `ACKNOWLEDGE_HOST_PROBLEM` | `<host_name>;<entier>;<0\|1>;<0\|1>;<auteur>;<valeur>` |  |
| `ACKNOWLEDGE_HOST_PROBLEM_EXPIRE` | `<host_name>;<entier>;<0\|1>;<0\|1>;<entier>;<auteur>;<valeur>` |  |
| `ACKNOWLEDGE_SVC_PROBLEM` | `<host_name>;<service_description>;<entier>;<0\|1>;<0\|1>;<auteur>;<valeur>` |  |
| `ACKNOWLEDGE_SVC_PROBLEM_EXPIRE` | `<host_name>;<service_description>;<entier>;<0\|1>;<0\|1>;<entier>;<auteur>;<valeur>` |  |
| `ADD_HOST_COMMENT` | `<host_name>;<0\|1>;<auteur>;<valeur>` |  |
| `ADD_SIMPLE_HOST_DEPENDENCY` | `<host_name>;<host_name>` |  |
| `ADD_SIMPLE_POLLER` | `<valeur>;<valeur>;<valeur>;<valeur>` | oui |
| `ADD_SVC_COMMENT` | `<host_name>;<service_description>;<0\|1>;<auteur>;<valeur>` |  |
| `CHANGE_CONTACT_HOST_NOTIFICATION_TIMEPERIOD` | `<contact_name>;<timeperiod_name>` | oui |
| `CHANGE_CONTACT_MODATTR` | `<contact_name>;<valeur>` | oui |
| `CHANGE_CONTACT_MODHATTR` | `<contact_name>;<valeur>` | oui |
| `CHANGE_CONTACT_MODSATTR` | `<contact_name>;<valeur>` | oui |
| `CHANGE_CONTACT_SVC_NOTIFICATION_TIMEPERIOD` | `<contact_name>;<timeperiod_name>` | oui |
| `CHANGE_CUSTOM_CONTACT_VAR` | `<contact_name>;<valeur>;<valeur>` | oui |
| `CHANGE_CUSTOM_HOST_VAR` | `<host_name>;<valeur>;<valeur>` |  |
| `CHANGE_CUSTOM_SVC_VAR` | `<host_name>;<service_description>;<valeur>;<valeur>` |  |
| `CHANGE_GLOBAL_HOST_EVENT_HANDLER` | `<command_name>` | oui |
| `CHANGE_GLOBAL_SVC_EVENT_HANDLER` | `<command_name>` | oui |
| `CHANGE_HOST_CHECK_COMMAND` | `<host_name>;<command_name>` |  |
| `CHANGE_HOST_CHECK_TIMEPERIOD` | `<host_name>;<timeperiod_name>` |  |
| `CHANGE_HOST_EVENT_HANDLER` | `<host_name>;<command_name>` |  |
| `CHANGE_HOST_MODATTR` | `<host_name>;<entier>` |  |
| `CHANGE_MAX_HOST_CHECK_ATTEMPTS` | `<host_name>;<entier>` |  |
| `CHANGE_MAX_SVC_CHECK_ATTEMPTS` | `<host_name>;<service_description>;<entier>` |  |
| `CHANGE_NORMAL_HOST_CHECK_INTERVAL` | `<host_name>;<entier>` |  |
| `CHANGE_NORMAL_SVC_CHECK_INTERVAL` | `<host_name>;<service_description>;<entier>` |  |
| `CHANGE_RETRY_HOST_CHECK_INTERVAL` | `<host_name>;<entier>` |  |
| `CHANGE_RETRY_SVC_CHECK_INTERVAL` | `<host_name>;<service_description>;<entier>` |  |
| `CHANGE_SVC_CHECK_COMMAND` | `<host_name>;<service_description>;<command_name>` |  |
| `CHANGE_SVC_CHECK_TIMEPERIOD` | `<host_name>;<service_description>;<timeperiod_name>` |  |
| `CHANGE_SVC_EVENT_HANDLER` | `<host_name>;<service_description>;<command_name>` |  |
| `CHANGE_SVC_MODATTR` | `<host_name>;<service_description>;<entier>` |  |
| `CHANGE_SVC_NOTIFICATION_TIMEPERIOD` | `<host_name>;<service_description>;<timeperiod_name>` |  |
| `DELAY_HOST_NOTIFICATION` | `<host_name>;<entier>` |  |
| `DELAY_SVC_NOTIFICATION` | `<host_name>;<service_description>;<entier>` |  |
| `DEL_ALL_HOST_COMMENTS` | `<host_name>` |  |
| `DEL_ALL_HOST_DOWNTIMES` | `<host_name>` |  |
| `DEL_ALL_SVC_COMMENTS` | `<host_name>;<service_description>` |  |
| `DEL_ALL_SVC_DOWNTIMES` | `<host_name>;<service_description>` |  |
| `DEL_CONTACT_DOWNTIME` | `<entier>` | oui |
| `DEL_HOST_COMMENT` | `<entier>` | oui |
| `DEL_HOST_DEPENDENCY` | `<host_name>;<host_name>` |  |
| `DEL_HOST_DOWNTIME` | `<entier>` | oui |
| `DEL_SVC_COMMENT` | `<entier>` | oui |
| `DEL_SVC_DOWNTIME` | `<entier>` | oui |
| `DISABLE_ALL_NOTIFICATIONS_BEYOND_HOST` | `<host_name>` |  |
| `DISABLE_CONTACTGROUP_HOST_NOTIFICATIONS` | `<contactgroup_name>` | oui |
| `DISABLE_CONTACTGROUP_SVC_NOTIFICATIONS` | `<contactgroup_name>` | oui |
| `DISABLE_CONTACT_HOST_NOTIFICATIONS` | `<contact_name>` | oui |
| `DISABLE_CONTACT_SVC_NOTIFICATIONS` | `<contact_name>` | oui |
| `DISABLE_EVENT_HANDLERS` | — | oui |
| `DISABLE_FAILURE_PREDICTION` | — | oui |
| `DISABLE_FLAP_DETECTION` | — | oui |
| `DISABLE_HOSTGROUP_HOST_CHECKS` | `<hostgroup_name>` | oui |
| `DISABLE_HOSTGROUP_HOST_NOTIFICATIONS` | `<hostgroup_name>` | oui |
| `DISABLE_HOSTGROUP_PASSIVE_HOST_CHECKS` | `<hostgroup_name>` | oui |
| `DISABLE_HOSTGROUP_PASSIVE_SVC_CHECKS` | `<hostgroup_name>` | oui |
| `DISABLE_HOSTGROUP_SVC_CHECKS` | `<hostgroup_name>` | oui |
| `DISABLE_HOSTGROUP_SVC_NOTIFICATIONS` | `<hostgroup_name>` | oui |
| `DISABLE_HOST_AND_CHILD_NOTIFICATIONS` | `<host_name>` |  |
| `DISABLE_HOST_CHECK` | `<host_name>` |  |
| `DISABLE_HOST_EVENT_HANDLER` | `<host_name>` |  |
| `DISABLE_HOST_FLAP_DETECTION` | `<host_name>` |  |
| `DISABLE_HOST_FRESHNESS_CHECKS` | — | oui |
| `DISABLE_HOST_NOTIFICATIONS` | `<host_name>` |  |
| `DISABLE_HOST_SVC_CHECKS` | `<host_name>` |  |
| `DISABLE_HOST_SVC_NOTIFICATIONS` | `<host_name>` |  |
| `DISABLE_NOTIFICATIONS` | — | oui |
| `DISABLE_PASSIVE_HOST_CHECKS` | `<host_name>` |  |
| `DISABLE_PASSIVE_SVC_CHECKS` | `<host_name>;<service_description>` |  |
| `DISABLE_PERFORMANCE_DATA` | — | oui |
| `DISABLE_SERVICEGROUP_HOST_CHECKS` | `<servicegroup_name>` | oui |
| `DISABLE_SERVICEGROUP_HOST_NOTIFICATIONS` | `<servicegroup_name>` | oui |
| `DISABLE_SERVICEGROUP_PASSIVE_HOST_CHECKS` | `<servicegroup_name>` | oui |
| `DISABLE_SERVICEGROUP_PASSIVE_SVC_CHECKS` | `<servicegroup_name>` | oui |
| `DISABLE_SERVICEGROUP_SVC_CHECKS` | `<servicegroup_name>` | oui |
| `DISABLE_SERVICEGROUP_SVC_NOTIFICATIONS` | `<servicegroup_name>` | oui |
| `DISABLE_SERVICE_FLAP_DETECTION` | `<host_name>;<service_description>` |  |
| `DISABLE_SERVICE_FRESHNESS_CHECKS` | — | oui |
| `DISABLE_SVC_CHECK` | `<host_name>;<service_description>` |  |
| `DISABLE_SVC_EVENT_HANDLER` | `<host_name>;<service_description>` |  |
| `DISABLE_SVC_FLAP_DETECTION` | `<host_name>;<service_description>` |  |
| `DISABLE_SVC_NOTIFICATIONS` | `<host_name>;<service_description>` |  |
| `ENABLE_ALL_NOTIFICATIONS_BEYOND_HOST` | `<host_name>` |  |
| `ENABLE_CONTACTGROUP_HOST_NOTIFICATIONS` | `<contactgroup_name>` | oui |
| `ENABLE_CONTACTGROUP_SVC_NOTIFICATIONS` | `<contactgroup_name>` | oui |
| `ENABLE_CONTACT_HOST_NOTIFICATIONS` | `<contact_name>` | oui |
| `ENABLE_CONTACT_SVC_NOTIFICATIONS` | `<contact_name>` | oui |
| `ENABLE_EVENT_HANDLERS` | — | oui |
| `ENABLE_FAILURE_PREDICTION` | — | oui |
| `ENABLE_FLAP_DETECTION` | — | oui |
| `ENABLE_HOSTGROUP_HOST_CHECKS` | `<hostgroup_name>` | oui |
| `ENABLE_HOSTGROUP_HOST_NOTIFICATIONS` | `<hostgroup_name>` | oui |
| `ENABLE_HOSTGROUP_PASSIVE_HOST_CHECKS` | `<hostgroup_name>` | oui |
| `ENABLE_HOSTGROUP_PASSIVE_SVC_CHECKS` | `<hostgroup_name>` | oui |
| `ENABLE_HOSTGROUP_SVC_CHECKS` | `<hostgroup_name>` | oui |
| `ENABLE_HOSTGROUP_SVC_NOTIFICATIONS` | `<hostgroup_name>` | oui |
| `ENABLE_HOST_AND_CHILD_NOTIFICATIONS` | `<host_name>` |  |
| `ENABLE_HOST_CHECK` | `<host_name>` |  |
| `ENABLE_HOST_EVENT_HANDLER` | `<host_name>` |  |
| `ENABLE_HOST_FLAP_DETECTION` | `<host_name>` |  |
| `ENABLE_HOST_FRESHNESS_CHECKS` | — | oui |
| `ENABLE_HOST_NOTIFICATIONS` | `<host_name>` |  |
| `ENABLE_HOST_SVC_CHECKS` | `<host_name>` |  |
| `ENABLE_HOST_SVC_NOTIFICATIONS` | `<host_name>` |  |
| `ENABLE_NOTIFICATIONS` | — | oui |
| `ENABLE_PASSIVE_HOST_CHECKS` | `<host_name>` |  |
| `ENABLE_PASSIVE_SVC_CHECKS` | `<host_name>;<service_description>` |  |
| `ENABLE_PERFORMANCE_DATA` | — | oui |
| `ENABLE_SERVICEGROUP_HOST_CHECKS` | `<servicegroup_name>` | oui |
| `ENABLE_SERVICEGROUP_HOST_NOTIFICATIONS` | `<servicegroup_name>` | oui |
| `ENABLE_SERVICEGROUP_PASSIVE_HOST_CHECKS` | `<servicegroup_name>` | oui |
| `ENABLE_SERVICEGROUP_PASSIVE_SVC_CHECKS` | `<servicegroup_name>` | oui |
| `ENABLE_SERVICEGROUP_SVC_CHECKS` | `<servicegroup_name>` | oui |
| `ENABLE_SERVICEGROUP_SVC_NOTIFICATIONS` | `<servicegroup_name>` | oui |
| `ENABLE_SERVICE_FRESHNESS_CHECKS` | — | oui |
| `ENABLE_SVC_CHECK` | `<host_name>;<service_description>` |  |
| `ENABLE_SVC_EVENT_HANDLER` | `<host_name>;<service_description>` |  |
| `ENABLE_SVC_FLAP_DETECTION` | `<host_name>;<service_description>` |  |
| `ENABLE_SVC_NOTIFICATIONS` | `<host_name>;<service_description>` |  |
| `LAUNCH_HOST_EVENT_HANDLER` | `<host_name>` |  |
| `LAUNCH_SVC_EVENT_HANDLER` | `<host_name>;<service_description>` |  |
| `PROCESS_FILE` | `<valeur>;<0\|1>` | oui |
| `PROCESS_HOST_CHECK_RESULT` | `<host_name>;<entier>;<valeur>` |  |
| `PROCESS_HOST_OUTPUT` | `<host_name>;<valeur>` |  |
| `PROCESS_SERVICE_CHECK_RESULT` | `<host_name>;<service_description>;<entier>;<valeur>` |  |
| `PROCESS_SERVICE_OUTPUT` | `<host_name>;<service_description>;<valeur>` |  |
| `READ_STATE_INFORMATION` | — | oui |
| `RELOAD_CONFIG` | — | oui |
| `REMOVE_HOST_ACKNOWLEDGEMENT` | `<host_name>` |  |
| `REMOVE_SVC_ACKNOWLEDGEMENT` | `<host_name>;<service_description>` |  |
| `RESTART_PROCESS` | — | oui |
| `RESTART_PROGRAM` | — | oui |
| `SAVE_STATE_INFORMATION` | — | oui |
| `SCHEDULE_AND_PROPAGATE_HOST_DOWNTIME` | `<host_name>;<entier>;<entier>;<0\|1>;<entier>;<entier>;<auteur>;<valeur>` |  |
| `SCHEDULE_AND_PROPAGATE_TRIGGERED_HOST_DOWNTIME` | `<host_name>;<entier>;<entier>;<0\|1>;<entier>;<entier>;<auteur>;<valeur>` |  |
| `SCHEDULE_CONTACT_DOWNTIME` | `<contact_name>;<entier>;<entier>;<auteur>;<valeur>` | oui |
| `SCHEDULE_FORCED_HOST_CHECK` | `<host_name>;<entier>` |  |
| `SCHEDULE_FORCED_HOST_SVC_CHECKS` | `<host_name>;<entier>` |  |
| `SCHEDULE_FORCED_SVC_CHECK` | `<host_name>;<service_description>;<entier>` |  |
| `SCHEDULE_HOSTGROUP_HOST_DOWNTIME` | `<hostgroup_name>;<entier>;<entier>;<0\|1>;<entier>;<entier>;<auteur>;<valeur>` | oui |
| `SCHEDULE_HOSTGROUP_SVC_DOWNTIME` | `<hostgroup_name>;<entier>;<entier>;<0\|1>;<entier>;<entier>;<auteur>;<valeur>` | oui |
| `SCHEDULE_HOST_CHECK` | `<host_name>;<entier>` |  |
| `SCHEDULE_HOST_DOWNTIME` | `<host_name>;<entier>;<entier>;<0\|1>;<entier>;<entier>;<auteur>;<valeur>` |  |
| `SCHEDULE_HOST_SVC_CHECKS` | `<host_name>;<entier>` |  |
| `SCHEDULE_HOST_SVC_DOWNTIME` | `<host_name>;<entier>;<entier>;<0\|1>;<entier>;<entier>;<auteur>;<valeur>` |  |
| `SCHEDULE_SERVICEGROUP_HOST_DOWNTIME` | `<servicegroup_name>;<entier>;<entier>;<0\|1>;<entier>;<entier>;<auteur>;<valeur>` | oui |
| `SCHEDULE_SERVICEGROUP_SVC_DOWNTIME` | `<servicegroup_name>;<entier>;<entier>;<0\|1>;<entier>;<entier>;<auteur>;<valeur>` | oui |
| `SCHEDULE_SVC_CHECK` | `<host_name>;<service_description>;<entier>` |  |
| `SCHEDULE_SVC_DOWNTIME` | `<host_name>;<service_description>;<entier>;<entier>;<0\|1>;<entier>;<entier>;<auteur>;<valeur>` |  |
| `SEND_CUSTOM_HOST_NOTIFICATION` | `<host_name>;<entier>;<auteur>;<valeur>` |  |
| `SEND_CUSTOM_SVC_NOTIFICATION` | `<host_name>;<service_description>;<entier>;<auteur>;<valeur>` |  |
| `SET_HOST_NOTIFICATION_NUMBER` | `<host_name>;<entier>` |  |
| `SET_SVC_NOTIFICATION_NUMBER` | `<host_name>;<service_description>;<entier>` |  |
| `SHUTDOWN_PROGRAM` | — | oui |
| `START_ACCEPTING_PASSIVE_HOST_CHECKS` | — | oui |
| `START_ACCEPTING_PASSIVE_SVC_CHECKS` | — | oui |
| `START_EXECUTING_HOST_CHECKS` | — | oui |
| `START_EXECUTING_SVC_CHECKS` | — | oui |
| `START_OBSESSING_OVER_HOST` | `<host_name>` |  |
| `START_OBSESSING_OVER_HOST_CHECKS` | — | oui |
| `START_OBSESSING_OVER_SVC` | `<host_name>;<service_description>` |  |
| `START_OBSESSING_OVER_SVC_CHECKS` | — | oui |
| `STOP_ACCEPTING_PASSIVE_HOST_CHECKS` | — | oui |
| `STOP_ACCEPTING_PASSIVE_SVC_CHECKS` | — | oui |
| `STOP_EXECUTING_HOST_CHECKS` | — | oui |
| `STOP_EXECUTING_SVC_CHECKS` | — | oui |
| `STOP_OBSESSING_OVER_HOST` | `<host_name>` |  |
| `STOP_OBSESSING_OVER_HOST_CHECKS` | — | oui |
| `STOP_OBSESSING_OVER_SVC` | `<host_name>;<service_description>` |  |
| `STOP_OBSESSING_OVER_SVC_CHECKS` | — | oui |

Retour à l'[index de la référence](README.md).
