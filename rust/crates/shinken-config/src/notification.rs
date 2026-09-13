//! Native notification configuration, including Shinken notificationways.
use std::collections::{BTreeMap,BTreeSet};
use crate::{Attributes,CommandConfig,LoadError,TimePeriods,flag,list,positive,required,semantic,value};

#[derive(Clone,Debug)]
pub struct NotificationConfig {
    pub enabled:bool,
    pub interval_ms:u64,
    pub first_delay_ms:u64,
    pub period:String,
    pub options:BTreeSet<char>,
}
#[derive(Clone,Debug)]
pub struct NotificationRoute {
    pub id:String,
    pub command:String,
    pub period:String,
    pub options:BTreeSet<char>,
    pub enabled:bool,
}
#[derive(Clone,Debug,Default)]
pub struct ContactNotifications {
    pub host:Vec<NotificationRoute>,
    pub service:Vec<NotificationRoute>,
}
pub fn option_for(state:u8,host:bool)->char{
    if host{match state{0=>'r',1=>'d',_=>'u'}}else{match state{0=>'r',1=>'w',2=>'c',_=>'u'}}
}
fn options(a:&Attributes,key:&str,host:bool)->Result<BTreeSet<char>,LoadError>{
    let raw=value(a,key,if host{"d,u,r"}else{"w,c,u,r"});
    let options:BTreeSet<_>=list(raw).map(|s|{
        let mut chars=s.chars();
        let c=chars.next().ok_or_else(||semantic("empty notification option"))?;
        if chars.next().is_some()||!(if host{"durnfs"}else{"wcurnfs"}).contains(c){return Err(semantic(format!("invalid {key}: {s}")));}
        Ok(c)
    }).collect::<Result<_,LoadError>>()?;
    Ok(if options.contains(&'n'){BTreeSet::new()}else{options})
}
impl NotificationConfig {
    pub(crate) fn build(a:&Attributes,interval:f64,host:bool,periods:&TimePeriods)->Result<Self,LoadError>{
        let enabled=flag(a,"notifications_enabled",true)?;
        let period=value(a,"notification_period","").to_owned();
        if enabled{periods.validate_use(&period,value(a,"use_timezone",""))?;}
        Ok(Self{
            enabled,period,options:options(a,"notification_options",host)?,
            interval_ms:(positive(value(a,"notification_interval","60"),"notification_interval",true)?*interval*1000.0).round() as u64,
            first_delay_ms:(positive(value(a,"first_notification_delay","0"),"first_notification_delay",true)?*interval*1000.0).round() as u64,
        })
    }
}
pub(crate) fn routes(
    resolved:&[(&str,Attributes)],contacts:&BTreeMap<String,Attributes>,
    commands:&BTreeMap<String,CommandConfig>,periods:&TimePeriods,
)->Result<BTreeMap<String,ContactNotifications>,LoadError>{
    let mut ways=BTreeMap::new();
    for (_,a) in resolved.iter().filter(|(kind,_)|*kind=="notificationway"){
        let name=required(a,"notificationway_name")?;
        if ways.insert(name,a).is_some(){return Err(semantic(format!("duplicate notificationway {name}")));}
    }
    let mut routes=BTreeMap::new();
    for (name,contact) in contacts{
        let mut channels=vec![("direct",contact)];
        for way in list(value(contact,"notificationways","")){
            channels.push((way,*ways.get(way).ok_or_else(||semantic(format!("unknown notificationway {way}")))?));
        }
        let mut output=ContactNotifications::default();
        for (host,kind) in [(true,"host"),(false,"service")]{
            let enabled=flag(contact,&format!("{kind}_notifications_enabled"),true)?;
            for (channel,a) in &channels{
                let selected=options(a,&format!("{kind}_notification_options"),host)?;
                let contact_options=options(contact,&format!("{kind}_notification_options"),host)?;
                let selected=selected.intersection(&contact_options).copied().collect::<BTreeSet<_>>();
                let period=value(a,&format!("{kind}_notification_period"),"");
                for command in list(value(a,&format!("{kind}_notification_commands"),"")){
                    if !commands.contains_key(command.split('!').next().unwrap_or("")){
                        return Err(semantic(format!("contact {name} references unknown notification command {command}")));
                    }
                    periods.validate_use(period,"")?;
                    let route=NotificationRoute{
                        id:format!("{name}/{channel}/{command}"),command:command.into(),period:period.into(),
                        options:selected.clone(),enabled,
                    };
                    if host{output.host.push(route);}else{output.service.push(route);}
                }
            }
        }
        routes.insert(name.clone(),output);
    }
    Ok(routes)
}
