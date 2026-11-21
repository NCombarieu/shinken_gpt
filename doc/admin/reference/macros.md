<!-- Page générée par doc/tools/gen_reference.py depuis le code : ne pas modifier à la main. -->


# Macros

Les macros `$NOM$` sont remplacées dans les lignes de commande avant exécution. Voir [macros](../11-macros.md) pour leur usage.

## Macros sans objet (globales)

| Macro | Source |
|---|---|
| `$DATE$` | _get_date |
| `$EVENTSTARTTIME$` | _get_events_start_time |
| `$LONGDATETIME$` | _get_long_date_time |
| `$PROCESSSTARTTIME$` | _get_process_start_time |
| `$SHORTDATETIME$` | _get_short_date_time |
| `$TIME$` | _get_time |
| `$TIMET$` | _get_timet |
| `$TOTALHOSTPROBLEMS$` | _get_total_host_problems |
| `$TOTALHOSTPROBLEMSUNHANDLED$` | _get_total_host_problems_unhandled |
| `$TOTALHOSTSDOWN$` | _get_total_hosts_down |
| `$TOTALHOSTSDOWNUNHANDLED$` | _get_total_hosts_unhandled |
| `$TOTALHOSTSUNREACHABLE$` | _get_total_hosts_unreachable |
| `$TOTALHOSTSUNREACHABLEUNHANDLED$` | _get_total_hosts_unreachable_unhandled |
| `$TOTALHOSTSUP$` | _get_total_hosts_up |
| `$TOTALSERVICEPROBLEMS$` | _get_total_service_problems |
| `$TOTALSERVICEPROBLEMSUNHANDLED$` | _get_total_service_problems_unhandled |
| `$TOTALSERVICESCRITICAL$` | _get_total_services_critical |
| `$TOTALSERVICESCRITICALUNHANDLED$` | _get_total_services_critical_unhandled |
| `$TOTALSERVICESOK$` | _get_total_service_ok |
| `$TOTALSERVICESUNKNOWN$` | _get_total_services_unknown |
| `$TOTALSERVICESUNKNOWNUNHANDLED$` | _get_total_services_unknown_unhandled |
| `$TOTALSERVICESWARNING$` | _get_total_services_warning |
| `$TOTALSERVICESWARNINGUNHANDLED$` | _get_total_services_warning_unhandled |

## Autres macros spéciales

| Macro | Valeur |
|---|---|
| `$ARG1$` … `$ARGn$` | Arguments passés à la commande après « ! » dans check_command. |
| `$USER1$` … `$USERn$`, `$NOM$` | Macros de ressource définies dans `resource.d/*.cfg`. |
| `$_HOSTNOM$`, `$_SERVICENOM$`, `$_CONTACTNOM$` | Macro personnalisée `_NOM` de l'hôte, du service ou du contact. |
| `$HOSTSTATE:hôte$`, `$SERVICESTATE:hôte:service$` | Macro « à la demande » : valeur prise sur un autre objet. |

## Macros de hôte

| Macro | Directive ou valeur source |
|---|---|
| `$FULLNAME$` | `get_full_name` |
| `$HOSTACKAUTHOR$` | `get_ack_author_name` |
| `$HOSTACKAUTHORALIAS$` | `get_ack_author_name` |
| `$HOSTACKAUTHORNAME$` | `get_ack_author_name` |
| `$HOSTACKCOMMENT$` | `get_ack_comment` |
| `$HOSTACTIONURL$` | `action_url` |
| `$HOSTADDRESS$` | `address` |
| `$HOSTADDRESS0$` | `address0` |
| `$HOSTADDRESS1$` | `address1` |
| `$HOSTADDRESS10$` | `address10` |
| `$HOSTADDRESS11$` | `address11` |
| `$HOSTADDRESS12$` | `address12` |
| `$HOSTADDRESS13$` | `address13` |
| `$HOSTADDRESS14$` | `address14` |
| `$HOSTADDRESS15$` | `address15` |
| `$HOSTADDRESS16$` | `address16` |
| `$HOSTADDRESS17$` | `address17` |
| `$HOSTADDRESS18$` | `address18` |
| `$HOSTADDRESS19$` | `address19` |
| `$HOSTADDRESS2$` | `address2` |
| `$HOSTADDRESS20$` | `address20` |
| `$HOSTADDRESS21$` | `address21` |
| `$HOSTADDRESS22$` | `address22` |
| `$HOSTADDRESS23$` | `address23` |
| `$HOSTADDRESS24$` | `address24` |
| `$HOSTADDRESS25$` | `address25` |
| `$HOSTADDRESS26$` | `address26` |
| `$HOSTADDRESS27$` | `address27` |
| `$HOSTADDRESS28$` | `address28` |
| `$HOSTADDRESS29$` | `address29` |
| `$HOSTADDRESS3$` | `address3` |
| `$HOSTADDRESS30$` | `address30` |
| `$HOSTADDRESS31$` | `address31` |
| `$HOSTADDRESS4$` | `address4` |
| `$HOSTADDRESS5$` | `address5` |
| `$HOSTADDRESS6$` | `address6` |
| `$HOSTADDRESS7$` | `address7` |
| `$HOSTADDRESS8$` | `address8` |
| `$HOSTADDRESS9$` | `address9` |
| `$HOSTALIAS$` | `alias` |
| `$HOSTATTEMPT$` | `attempt` |
| `$HOSTBUSINESSIMPACT$` | `business_impact` |
| `$HOSTCHECKCOMMAND$` | `get_check_command` |
| `$HOSTDISPLAYNAME$` | `display_name` |
| `$HOSTDOWNTIME$` | `get_downtime` |
| `$HOSTDURATION$` | `get_duration` |
| `$HOSTDURATIONSEC$` | `get_duration_sec` |
| `$HOSTEVENTID$` | `current_event_id` |
| `$HOSTEXECUTIONTIME$` | `execution_time` |
| `$HOSTGROUPNAME$` | `get_groupname` |
| `$HOSTGROUPNAMES$` | `get_groupnames` |
| `$HOSTLATENCY$` | `latency` |
| `$HOSTNAME$` | `host_name` |
| `$HOSTNOTES$` | `notes` |
| `$HOSTNOTESURL$` | `notes_url` |
| `$HOSTOUTPUT$` | `output` |
| `$HOSTPERCENTCHANGE$` | `percent_state_change` |
| `$HOSTPERFDATA$` | `perf_data` |
| `$HOSTPROBLEMID$` | `current_problem_id` |
| `$HOSTREALM$` | `get_realm` |
| `$HOSTSTATE$` | `state` |
| `$HOSTSTATEID$` | `state_id` |
| `$HOSTSTATETYPE$` | `state_type` |
| `$LASTHOSTCHECK$` | `last_chk` |
| `$LASTHOSTDOWN$` | `last_time_down` |
| `$LASTHOSTEVENTID$` | `last_event_id` |
| `$LASTHOSTPERFDATA$` | `last_perf_data` |
| `$LASTHOSTPROBLEMID$` | `last_problem_id` |
| `$LASTHOSTSTATE$` | `last_state` |
| `$LASTHOSTSTATECHANGE$` | `last_state_change` |
| `$LASTHOSTSTATEID$` | `last_state_id` |
| `$LASTHOSTUNREACHABLE$` | `last_time_unreachable` |
| `$LASTHOSTUP$` | `last_time_up` |
| `$LONGHOSTOUTPUT$` | `long_output` |
| `$MAXHOSTATTEMPTS$` | `max_check_attempts` |
| `$SHORTSTATUS$` | `get_short_status` |
| `$STATUS$` | `get_status` |
| `$TOTALHOSTSERVICES$` | `get_total_services` |
| `$TOTALHOSTSERVICESCRITICAL$` | `get_total_services_critical` |
| `$TOTALHOSTSERVICESOK$` | `get_total_services_ok` |
| `$TOTALHOSTSERVICESUNKNOWN$` | `get_total_services_unknown` |
| `$TOTALHOSTSERVICESWARNING$` | `get_total_services_warning` |

## Macros de service

| Macro | Directive ou valeur source |
|---|---|
| `$FULLNAME$` | `get_full_name` |
| `$LASTSERVICECHECK$` | `last_chk` |
| `$LASTSERVICECRITICAL$` | `last_time_critical` |
| `$LASTSERVICEEVENTID$` | `last_event_id` |
| `$LASTSERVICEOK$` | `last_time_ok` |
| `$LASTSERVICEPERFDATA$` | `last_perf_data` |
| `$LASTSERVICEPROBLEMID$` | `last_problem_id` |
| `$LASTSERVICESTATE$` | `last_state` |
| `$LASTSERVICESTATECHANGE$` | `last_state_change` |
| `$LASTSERVICESTATEID$` | `last_state_id` |
| `$LASTSERVICEUNKNOWN$` | `last_time_unknown` |
| `$LASTSERVICEWARNING$` | `last_time_warning` |
| `$LONGSERVICEOUTPUT$` | `long_output` |
| `$MAXSERVICEATTEMPTS$` | `max_check_attempts` |
| `$SERVICEACKAUTHOR$` | `get_ack_author_name` |
| `$SERVICEACKAUTHORALIAS$` | `get_ack_author_name` |
| `$SERVICEACKAUTHORNAME$` | `get_ack_author_name` |
| `$SERVICEACKCOMMENT$` | `get_ack_comment` |
| `$SERVICEACTIONURL$` | `action_url` |
| `$SERVICEATTEMPT$` | `attempt` |
| `$SERVICEBUSINESSIMPACT$` | `business_impact` |
| `$SERVICECHECKCOMMAND$` | `get_check_command` |
| `$SERVICEDESC$` | `service_description` |
| `$SERVICEDISPLAYNAME$` | `display_name` |
| `$SERVICEDOWNTIME$` | `get_downtime` |
| `$SERVICEDURATION$` | `get_duration` |
| `$SERVICEDURATIONSEC$` | `get_duration_sec` |
| `$SERVICEEVENTID$` | `current_event_id` |
| `$SERVICEEXECUTIONTIME$` | `execution_time` |
| `$SERVICEGROUPNAME$` | `get_groupname` |
| `$SERVICEGROUPNAMES$` | `get_groupnames` |
| `$SERVICEISVOLATILE$` | `is_volatile` |
| `$SERVICELATENCY$` | `latency` |
| `$SERVICENOTES$` | `notes` |
| `$SERVICENOTESURL$` | `notes_url` |
| `$SERVICEOUTPUT$` | `output` |
| `$SERVICEPERCENTCHANGE$` | `percent_state_change` |
| `$SERVICEPERFDATA$` | `perf_data` |
| `$SERVICEPROBLEMID$` | `current_problem_id` |
| `$SERVICESTATE$` | `state` |
| `$SERVICESTATEID$` | `state_id` |
| `$SERVICESTATETYPE$` | `state_type` |
| `$SHORTSTATUS$` | `get_short_status` |
| `$STATUS$` | `get_status` |

## Macros de contact

| Macro | Directive ou valeur source |
|---|---|
| `$CONTACTADDRESS1$` | `address1` |
| `$CONTACTADDRESS2$` | `address2` |
| `$CONTACTADDRESS3$` | `address3` |
| `$CONTACTADDRESS4$` | `address4` |
| `$CONTACTADDRESS5$` | `address5` |
| `$CONTACTADDRESS6$` | `address6` |
| `$CONTACTALIAS$` | `alias` |
| `$CONTACTEMAIL$` | `email` |
| `$CONTACTGROUPNAME$` | `get_groupname` |
| `$CONTACTGROUPNAMES$` | `get_groupnames` |
| `$CONTACTNAME$` | `contact_name` |
| `$CONTACTPAGER$` | `pager` |

## Macros de groupe d'hôtes

| Macro | Directive ou valeur source |
|---|---|
| `$HOSTGROUPACTIONURL$` | `action_url` |
| `$HOSTGROUPALIAS$` | `alias` |
| `$HOSTGROUPMEMBERS$` | `members` |
| `$HOSTGROUPNOTES$` | `notes` |
| `$HOSTGROUPNOTESURL$` | `notes_url` |

## Macros de groupe de services

| Macro | Directive ou valeur source |
|---|---|
| `$SERVICEGROUPACTIONURL$` | `action_url` |
| `$SERVICEGROUPALIAS$` | `alias` |
| `$SERVICEGROUPMEMBERS$` | `members` |
| `$SERVICEGROUPNOTES$` | `notes` |
| `$SERVICEGROUPNOTESURL$` | `notes_url` |

## Macros de groupe de contacts

| Macro | Directive ou valeur source |
|---|---|
| `$CONTACTGROUPALIAS$` | `alias` |
| `$CONTACTGROUPMEMBERS$` | `get_members` |

Retour à l'[index de la référence](README.md).
