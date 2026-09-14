//! Weekly Nagios periods, calendar exceptions, exclusions and timezone-aware evaluation.
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
const MONTHS: [&str; 12] = [
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
];
#[derive(Clone, Debug)]
struct MonthDate {
    month: u32,
    day: i32,
    ranges: Vec<(u32, u32)>,
}
#[derive(Clone, Debug)]
struct Period {
    week: [Vec<(u32, u32)>; 7],
    dates: BTreeMap<NaiveDate, Vec<(u32, u32)>>,
    month_dates: Vec<MonthDate>,
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
fn month_date(month: u32, value: &str) -> Result<MonthDate, String> {
    let value = value.trim();
    let split = value
        .find(char::is_whitespace)
        .ok_or_else(|| format!("missing time range in {value}"))?;
    let day = value[..split]
        .parse::<i32>()
        .map_err(|_| format!("invalid month day {}", &value[..split]))?;
    if day == 0 {
        return Err("month day 0 is invalid".into());
    }
    Ok(MonthDate {
        month,
        day,
        ranges: ranges(value[split..].trim())?,
    })
}
fn parse(a: &Attributes) -> Result<Period, String> {
    let mut period = Period {
        week: std::array::from_fn(|_| Vec::new()),
        dates: BTreeMap::new(),
        month_dates: Vec::new(),
        exclude: list(value(a, "exclude", "")).map(str::to_owned).collect(),
    };
    for (key, v) in a {
        if let Some(day) = DAYS.iter().position(|name| *name == key) {
            period.week[day].extend(ranges(v)?);
        } else if let Ok(date) = NaiveDate::parse_from_str(key, "%Y-%m-%d") {
            period.dates.insert(date, ranges(v)?);
        } else if let Some(month) = MONTHS.iter().position(|name| *name == key) {
            period.month_dates.push(month_date(month as u32 + 1, v)?);
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
fn days_in_month(year: i32, month: u32) -> Option<u32> {
    let (year, month) = if month == 12 {
        (year.checked_add(1)?, 1)
    } else {
        (year, month + 1)
    };
    NaiveDate::from_ymd_opt(year, month, 1)?.pred_opt().map(|d| d.day())
}
fn month_date_matches(rule: &MonthDate, date: NaiveDate) -> bool {
    if rule.month != date.month() {
        return false;
    }
    let Some(last) = days_in_month(date.year(), date.month()) else {
        return false;
    };
    let target = if rule.day > 0 {
        (rule.day as u32).min(last)
    } else {
        last.saturating_sub(rule.day.unsigned_abs().saturating_sub(1))
            .max(1)
    };
    target == date.day()
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
        let weekly = period.week[day]
            .iter()
            .any(|(start, end)| *start <= minute && minute < *end);
        let fixed = period.dates.get(&date).is_some_and(|ranges| {
            ranges
                .iter()
                .any(|(start, end)| *start <= minute && minute < *end)
        });
        let recurring = period.month_dates.iter().any(|rule| {
            month_date_matches(rule, date)
                && rule
                    .ranges
                    .iter()
                    .any(|(start, end)| *start <= minute && minute < *end)
        });
        (weekly || fixed || recurring)
            && !period
                .exclude
                .iter()
                .any(|name| self.allows_at(name, date, day, minute, depth + 1))
    }
    /// Search the next weekly or calendar opening in absolute minutes; this respects DST jumps.
    pub fn next_opening(&self, name: &str, zone: &str, timestamp: u64) -> Option<u64> {
        if self.allows(name, zone, timestamp) {
            return Some(timestamp);
        }
        let period = self.definitions.get(name).and_then(|p| p.as_ref().ok());
        if period.is_some_and(|p| {
            p.week.iter().all(Vec::is_empty)
                && p.dates.values().all(Vec::is_empty)
                && p.month_dates.iter().all(|r| r.ranges.is_empty())
        }) {
            return None;
        }
        let calendar = period.is_some_and(|p| !p.dates.is_empty() || !p.month_dates.is_empty());
        let days = if calendar { 367 } else { 8 };
        let start = timestamp / 60 * 60 + 60;
        (0..days * 24 * 60)
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
    fn fixed_date_exceptions_extend_weekly_ranges() {
        let period = Attributes::from([
            ("timeperiod_name".into(), "special".into()),
            ("monday".into(), "09:00-17:00".into()),
            ("2026-03-30".into(), "18:00-19:00".into()),
            ("2026-04-04".into(), "10:00-12:00".into()),
        ]);
        let p = TimePeriods::build(
            &[("timeperiod", period)],
            &Attributes::from([("use_timezone".into(), "UTC".into())]),
        )
        .unwrap();
        p.validate_use("special", "").unwrap();
        assert!(p.allows("special", "", stamp(2026, 3, 30, 10, 0)));
        assert!(p.allows("special", "", stamp(2026, 3, 30, 18, 30)));
        assert!(p.allows("special", "", stamp(2026, 4, 4, 10, 30)));
        assert!(!p.allows("special", "", stamp(2026, 4, 4, 12, 0)));
        assert!(p.allows("special", "", stamp(2026, 4, 6, 10, 0)));
    }
    #[test]
    fn annual_month_dates_follow_shinken_offsets() {
        let period = Attributes::from([
            ("timeperiod_name".into(), "annual".into()),
            ("february".into(), "10 10:00-12:00".into()),
            ("april".into(), "-1 18:00-20:00".into()),
        ]);
        let p = TimePeriods::build(
            &[("timeperiod", period)],
            &Attributes::from([("use_timezone".into(), "UTC".into())]),
        )
        .unwrap();
        p.validate_use("annual", "").unwrap();
        assert!(p.allows("annual", "", stamp(2026, 2, 10, 10, 30)));
        assert!(p.allows("annual", "", stamp(2027, 2, 10, 10, 30)));
        assert!(!p.allows("annual", "", stamp(2026, 2, 11, 10, 30)));
        assert!(p.allows("annual", "", stamp(2026, 4, 30, 18, 30)));
        assert_eq!(
            p.next_opening("annual", "", stamp(2026, 2, 1, 0, 0)),
            Some(stamp(2026, 2, 10, 10, 0))
        );
    }
    #[test]
    fn unsupported_used_periods_and_cycles_fail_validation() {
        let bad = Attributes::from([
            ("timeperiod_name".into(), "holidays".into()),
            ("day".into(), "1 00:00-24:00".into()),
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
