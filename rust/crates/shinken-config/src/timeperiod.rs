//! Weekly Nagios periods, fixed-date exceptions, exclusions and timezone-aware evaluation.
use crate::{list, required, semantic, value, Attributes, LoadError};
use chrono::{DateTime, Datelike, Local, NaiveDate, Timelike, Utc};
use chrono_tz::Tz;
use std::collections::{BTreeMap, BTreeSet};

const DAYS: [&str; 7] = [
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
];
#[derive(Clone, Debug)]
struct Period {
    week: [Vec<(u32, u32)>; 7],
    dates: BTreeMap<NaiveDate, Vec<(u32, u32)>>,
    exclude: Vec<String>,
}
#[derive(Clone, Debug)]
pub struct TimePeriods {
    definitions: BTreeMap<String, Result<Period, String>>,
    timezone: Option<Tz>,
}
fn minute(text: &str) -> Result<u32, String> {
    let (hour, minute) = text
        .split_once(':')
        .ok_or_else(|| format!("invalid time {text}"))?;
    let hour = hour
        .parse::<u32>()
        .map_err(|_| format!("invalid time {text}"))?;
    let minute = minute
        .parse::<u32>()
        .map_err(|_| format!("invalid time {text}"))?;
    if hour > 24 || minute > 59 || (hour == 24 && minute > 0) {
        return Err(format!("invalid time {text}"));
    }
    Ok(hour * 60 + minute)
}
fn ranges(value: &str) -> Result<Vec<(u32, u32)>, String> {
    let mut result = Vec::new();
    for range in list(value) {
        let (start, end) = range
            .split_once('-')
            .ok_or_else(|| format!("invalid time range {range}"))?;
        let start = minute(start)?;
        let end = minute(end)?;
        if start > end {
            return Err(format!(
                "overnight range {range}: split it across two weekdays or dates"
            ));
        }
        if start != end {
            result.push((start, end));
        }
    }
    Ok(result)
}
fn parse(a: &Attributes) -> Result<Period, String> {
    let mut period = Period {
        week: std::array::from_fn(|_| Vec::new()),
        dates: BTreeMap::new(),
        exclude: list(value(a, "exclude", "")).map(str::to_owned).collect(),
    };
    for (key, v) in a {
        if let Some(day) = DAYS.iter().position(|name| *name == key) {
            period.week[day].extend(ranges(v)?);
        } else if let Ok(date) = NaiveDate::parse_from_str(key, "%Y-%m-%d") {
            period.dates.insert(date, ranges(v)?);
        } else if ![
            "name",
            "alias",
            "timeperiod_name",
            "register",
            "use",
            "exclude",
        ]
        .contains(&key.as_str())
            && !key.starts_with('_')
        {
            return Err(format!("calendar exception {key} is not supported yet"));
        }
    }
    Ok(period)
}
fn timezone(name: &str) -> Result<Option<Tz>, LoadError> {
    if name.is_empty() {
        Ok(None)
    } else {
        name.parse()
            .map(Some)
            .map_err(|_| semantic(format!("unknown timezone {name}")))
    }
}
impl TimePeriods {
    pub(crate) fn build(
        objects: &[(&str, Attributes)],
        globals: &Attributes,
    ) -> Result<Self, LoadError> {
        let mut definitions = BTreeMap::new();
        for (_, a) in objects.iter().filter(|(kind, _)| *kind == "timeperiod") {
            let name = required(a, "timeperiod_name")?;
            if definitions.insert(name.into(), parse(a)).is_some() {
                return Err(semantic(format!("duplicate timeperiod {name}")));
            }
        }
        Ok(Self {
            definitions,
            timezone: timezone(value(globals, "use_timezone", ""))?,
        })
    }
    pub fn validate_use(&self, name: &str, zone: &str) -> Result<(), LoadError> {
        timezone(zone)?;
        self.validate(name, &mut BTreeSet::new())
    }
    fn validate(&self, name: &str, visiting: &mut BTreeSet<String>) -> Result<(), LoadError> {
        if name.is_empty() || (name == "24x7" && !self.definitions.contains_key(name)) {
            return Ok(());
        }
        if !visiting.insert(name.into()) {
            return Err(semantic(format!("timeperiod exclusion cycle at {name}")));
        }
        let period = self
            .definitions
            .get(name)
            .ok_or_else(|| semantic(format!("unknown timeperiod {name}")))?
            .as_ref()
            .map_err(|e| semantic(format!("timeperiod {name}: {e}")))?;
        for exclude in &period.exclude {
            self.validate(exclude, visiting)?;
        }
        visiting.remove(name);
        Ok(())
    }
    pub fn allows(&self, name: &str, zone: &str, timestamp: u64) -> bool {
        let Some(time) = i64::try_from(timestamp)
            .ok()
            .and_then(|n| DateTime::<Utc>::from_timestamp(n, 0))
        else {
            return false;
        };
        let zone = if zone.is_empty() {
            self.timezone
        } else {
            zone.parse().ok()
        };
        let (date, weekday, minute) = match zone {
            Some(zone) => {
                let t = time.with_timezone(&zone);
                (
                    t.date_naive(),
                    t.weekday().num_days_from_monday() as usize,
                    t.hour() * 60 + t.minute(),
                )
            }
            None => {
                let t = time.with_timezone(&Local);
                (
                    t.date_naive(),
                    t.weekday().num_days_from_monday() as usize,
                    t.hour() * 60 + t.minute(),
                )
            }
        };
        self.allows_at(name, date, weekday, minute, 0)
    }
    pub fn format_time(&self, timestamp: u64, format: &str) -> String {
        let Some(time) = i64::try_from(timestamp)
            .ok()
            .and_then(|n| DateTime::<Utc>::from_timestamp(n, 0))
        else {
            return String::new();
        };
        match self.timezone {
            Some(zone) => time.with_timezone(&zone).format(format).to_string(),
            None => time.with_timezone(&Local).format(format).to_string(),
        }
    }
    fn allows_at(
        &self,
        name: &str,
        date: NaiveDate,
        day: usize,
        minute: u32,
        depth: usize,
    ) -> bool {
        if name.is_empty() || (name == "24x7" && !self.definitions.contains_key(name)) {
            return true;
        }
        if depth > self.definitions.len() {
            return false;
        }
        let Some(Ok(period)) = self.definitions.get(name) else {
            return false;
        };
        let ranges = period.dates.get(&date).unwrap_or(&period.week[day]);
        ranges
            .iter()
            .any(|(start, end)| *start <= minute && minute < *end)
            && !period
                .exclude
                .iter()
                .any(|name| self.allows_at(name, date, day, minute, depth + 1))
    }
    /// Search the next weekly or fixed-date opening in absolute minutes; this respects DST jumps.
    pub fn next_opening(&self, name: &str, zone: &str, timestamp: u64) -> Option<u64> {
        if self.allows(name, zone, timestamp) {
            return Some(timestamp);
        }
        if self.definitions.get(name).is_some_and(|p| {
            p.as_ref()
                .is_ok_and(|p| p.week.iter().all(Vec::is_empty) && p.dates.values().all(Vec::is_empty))
        }) {
            return None;
        }
        let start = timestamp / 60 * 60 + 60;
        (0..8 * 24 * 60)
            .map(|i| start + i * 60)
            .find(|t| self.allows(name, zone, *t))
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    use chrono::TimeZone;
    fn stamp(y: i32, m: u32, d: u32, h: u32, min: u32) -> u64 {
        Utc.with_ymd_and_hms(y, m, d, h, min, 0)
            .unwrap()
            .timestamp() as u64
    }
    #[test]
    fn weekly_boundaries_exclusions_and_dst_are_respected() {
        let work = Attributes::from([
            ("timeperiod_name".into(), "work".into()),
            ("monday".into(), "09:00-17:00".into()),
            ("exclude".into(), "lunch".into()),
        ]);
        let lunch = Attributes::from([
            ("timeperiod_name".into(), "lunch".into()),
            ("monday".into(), "12:00-13:00".into()),
        ]);
        let p = TimePeriods::build(
            &[("timeperiod", work), ("timeperiod", lunch)],
            &Attributes::from([("use_timezone".into(), "Europe/Paris".into())]),
        )
        .unwrap();
        p.validate_use("work", "").unwrap();
        // March 30, 2026 is Monday after the Paris DST transition: 07:00 UTC = 09:00 local.
        assert!(!p.allows("work", "", stamp(2026, 3, 30, 6, 59)));
        assert!(p.allows("work", "", stamp(2026, 3, 30, 7, 0)));
        assert!(!p.allows("work", "", stamp(2026, 3, 30, 10, 0)));
        assert_eq!(
            p.next_opening("work", "", stamp(2026, 3, 30, 10, 0)),
            Some(stamp(2026, 3, 30, 11, 0))
        );
        assert!(!p.allows("work", "", stamp(2026, 3, 30, 15, 0)));
        assert!(p.allows("work", "UTC", stamp(2026, 3, 30, 15, 0)));
    }
    #[test]
    fn fixed_date_exceptions_override_weekly_ranges() {
        let period = Attributes::from([
            ("timeperiod_name".into(), "special".into()),
            ("monday".into(), "09:00-17:00".into()),
            ("2026-03-30".into(), "00:00-00:00".into()),
            ("2026-04-04".into(), "10:00-12:00".into()),
        ]);
        let p = TimePeriods::build(
            &[("timeperiod", period)],
            &Attributes::from([("use_timezone".into(), "UTC".into())]),
        )
        .unwrap();
        p.validate_use("special", "").unwrap();
        assert!(!p.allows("special", "", stamp(2026, 3, 30, 10, 0)));
        assert!(p.allows("special", "", stamp(2026, 4, 4, 10, 30)));
        assert!(!p.allows("special", "", stamp(2026, 4, 4, 12, 0)));
        assert!(p.allows("special", "", stamp(2026, 4, 6, 10, 0)));
    }
    #[test]
    fn unsupported_used_periods_and_cycles_fail_validation() {
        let bad = Attributes::from([
            ("timeperiod_name".into(), "holidays".into()),
            ("january".into(), "1 00:00-24:00".into()),
        ]);
        let p = TimePeriods::build(&[("timeperiod", bad)], &Attributes::new()).unwrap();
        assert!(p.validate_use("holidays", "").is_err());
        assert!(p.validate_use("24x7", "").is_ok());
        let cycle = Attributes::from([
            ("timeperiod_name".into(), "cycle".into()),
            ("exclude".into(), "cycle".into()),
        ]);
        let p = TimePeriods::build(&[("timeperiod", cycle)], &Attributes::new()).unwrap();
        assert!(p.validate_use("cycle", "").is_err());
        assert!(p.validate_use("missing", "").is_err());
    }
}
