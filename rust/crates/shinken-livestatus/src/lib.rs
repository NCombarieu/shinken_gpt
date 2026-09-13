//! Livestatus query parsing and evaluation, independent of the engine.
use regex::RegexBuilder;
use serde_json::{json, Value};
use std::collections::BTreeMap;
use thiserror::Error;

pub type Row = BTreeMap<String, Value>;
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub enum OutputFormat {
    #[default]
    Csv,
    Json,
    WrappedJson,
}
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub enum ResponseHeader {
    #[default]
    Off,
    Fixed16,
}
#[derive(Clone, Debug)]
pub struct Query {
    pub table: String,
    pub columns: Vec<String>,
    filters: Vec<Expr>,
    stats: Vec<Statistic>,
    pub output_format: OutputFormat,
    pub response_header: ResponseHeader,
    pub column_headers: bool,
    pub keep_alive: bool,
    pub auth_user: Option<String>,
    limit: usize,
    offset: usize,
}
#[derive(Clone, Debug)]
enum Expr {
    Atom(String, String, String),
    And(Vec<Expr>),
    Or(Vec<Expr>),
    Not(Box<Expr>),
}
#[derive(Clone, Debug)]
enum Statistic {
    Count(Expr),
    Aggregate(String, String),
}
#[derive(Debug, Error)]
#[error("{0}")]
pub struct QueryError(pub String);
fn err(s: impl Into<String>) -> QueryError {
    QueryError(s.into())
}
fn atom(text: &str) -> Result<Expr, QueryError> {
    let mut parts = text.splitn(2, char::is_whitespace);
    let column = parts.next().unwrap_or("");
    let remainder = parts
        .next()
        .ok_or_else(|| err("missing filter operator"))?
        .trim_start();
    let mut parts = remainder.splitn(2, char::is_whitespace);
    let operator = parts.next().unwrap_or("");
    let value = parts.next().unwrap_or("").trim_start();
    if ![
        "=", "!=", "<", ">", "<=", ">=", "~", "~~", "!~", "!~~", "=~",
    ]
    .contains(&operator)
    {
        return Err(err(format!("unsupported filter operator {operator}")));
    }
    if operator.contains('~') && operator != "=~" {
        RegexBuilder::new(value)
            .case_insensitive(operator.contains("~~"))
            .build()
            .map_err(|e| err(format!("invalid filter regex: {e}")))?;
    }
    Ok(Expr::Atom(column.into(), operator.into(), value.into()))
}
fn combine(stack: &mut Vec<Expr>, n: &str, and: bool) -> Result<(), QueryError> {
    let n = n
        .parse::<usize>()
        .map_err(|_| err("invalid boolean operand count"))?;
    if n == 0 || n > stack.len() {
        return Err(err("boolean operand stack underflow"));
    }
    let operands = stack.split_off(stack.len() - n);
    stack.push(if and {
        Expr::And(operands)
    } else {
        Expr::Or(operands)
    });
    Ok(())
}
fn switch(v: &str) -> Result<bool, QueryError> {
    match v {
        "on" => Ok(true),
        "off" => Ok(false),
        _ => Err(err("expected on or off")),
    }
}
pub fn parse_query(input: &str) -> Result<Query, QueryError> {
    let mut lines = input.lines();
    let first = lines.next().ok_or_else(|| err("missing GET"))?;
    let table = first
        .strip_prefix("GET ")
        .ok_or_else(|| err("expected GET table"))?
        .trim();
    if table.is_empty() || table.contains(char::is_whitespace) {
        return Err(err("invalid table name"));
    }
    let mut q = Query {
        table: table.into(),
        columns: Vec::new(),
        filters: Vec::new(),
        stats: Vec::new(),
        output_format: OutputFormat::Csv,
        response_header: ResponseHeader::Off,
        column_headers: false,
        keep_alive: false,
        auth_user: None,
        limit: usize::MAX,
        offset: 0,
    };
    let mut headers_explicit = false;
    for line in lines.take_while(|l| !l.trim().is_empty()) {
        let (key, v) = line
            .split_once(':')
            .ok_or_else(|| err("expected header: value"))?;
        let v = v.trim();
        match key {
            "Columns" => q.columns = v.split_whitespace().map(str::to_owned).collect(),
            "Filter" => q.filters.push(atom(v)?),
            "And" | "Or" => combine(&mut q.filters, v, key == "And")?,
            "Negate" => {
                let e = q
                    .filters
                    .pop()
                    .ok_or_else(|| err("Negate without filter"))?;
                q.filters.push(Expr::Not(Box::new(e)));
            }
            "Stats" => {
                let (op, column) = v.split_once(' ').unwrap_or(("", v));
                q.stats
                    .push(if ["sum", "min", "max", "avg", "std"].contains(&op) {
                        Statistic::Aggregate(op.into(), column.trim().into())
                    } else {
                        Statistic::Count(atom(v)?)
                    });
            }
            "StatsAnd" | "StatsOr" => {
                let n = v
                    .parse::<usize>()
                    .map_err(|_| err("invalid Stats operand count"))?;
                if n == 0 || n > q.stats.len() {
                    return Err(err("Stats operand stack underflow"));
                }
                let operands = q
                    .stats
                    .split_off(q.stats.len() - n)
                    .into_iter()
                    .map(|s| match s {
                        Statistic::Count(e) => Ok(e),
                        _ => Err(err("cannot combine aggregations")),
                    })
                    .collect::<Result<Vec<_>, _>>()?;
                q.stats.push(Statistic::Count(if key == "StatsAnd" {
                    Expr::And(operands)
                } else {
                    Expr::Or(operands)
                }));
            }
            "StatsNegate" => {
                let Statistic::Count(e) = q
                    .stats
                    .pop()
                    .ok_or_else(|| err("StatsNegate without Stats"))?
                else {
                    return Err(err("cannot negate aggregate"));
                };
                q.stats.push(Statistic::Count(Expr::Not(Box::new(e))));
            }
            "OutputFormat" => {
                q.output_format = match v {
                    "json" => OutputFormat::Json,
                    "csv" => OutputFormat::Csv,
                    "wrapped_json" => OutputFormat::WrappedJson,
                    _ => return Err(err(format!("unsupported output format {v}"))),
                }
            }
            "ResponseHeader" => {
                q.response_header = match v {
                    "off" => ResponseHeader::Off,
                    "fixed16" => ResponseHeader::Fixed16,
                    _ => return Err(err("unsupported response header")),
                }
            }
            "ColumnHeaders" => {
                q.column_headers = switch(v)?;
                headers_explicit = true;
            }
            "KeepAlive" => q.keep_alive = switch(v)?,
            "Limit" => q.limit = v.parse().map_err(|_| err("invalid limit"))?,
            "Offset" => q.offset = v.parse().map_err(|_| err("invalid offset"))?,
            "AuthUser" => q.auth_user = Some(v.to_owned()),
            _ => return Err(err(format!("unsupported header {key}"))),
        }
    }
    if !headers_explicit && q.columns.is_empty() && q.stats.is_empty() {
        q.column_headers = true;
    }
    Ok(q)
}
fn text(v: &Value) -> String {
    match v {
        Value::String(s) => s.clone(),
        _ => v.to_string(),
    }
}
fn eval(e: &Expr, row: &Row) -> bool {
    match e {
        Expr::And(items) => items.iter().all(|v| eval(v, row)),
        Expr::Or(items) => items.iter().any(|v| eval(v, row)),
        Expr::Not(e) => !eval(e, row),
        Expr::Atom(column, op, wanted) => {
            let Some(actual) = row.get(column) else {
                return false;
            };
            if let Value::Array(items) = actual {
                let has = items.iter().any(|item| text(item) == *wanted);
                return match op.as_str() {
                    ">=" => has,
                    "<" => !has,
                    "=" => items.is_empty() && wanted.is_empty(),
                    "!=" => !(items.is_empty() && wanted.is_empty()),
                    _ => false,
                };
            }
            let actual_text = text(actual);
            let ordering = if let (Some(a), Ok(b)) = (actual.as_f64(), wanted.parse::<f64>()) {
                a.partial_cmp(&b)
            } else {
                Some(actual_text.cmp(wanted))
            };
            match op.as_str() {
                "=" => ordering == Some(std::cmp::Ordering::Equal),
                "!=" => ordering != Some(std::cmp::Ordering::Equal),
                ">" => ordering == Some(std::cmp::Ordering::Greater),
                "<" => ordering == Some(std::cmp::Ordering::Less),
                ">=" => matches!(
                    ordering,
                    Some(std::cmp::Ordering::Greater | std::cmp::Ordering::Equal)
                ),
                "<=" => matches!(
                    ordering,
                    Some(std::cmp::Ordering::Less | std::cmp::Ordering::Equal)
                ),
                "=~" => actual_text.eq_ignore_ascii_case(wanted),
                _ => {
                    let matched = RegexBuilder::new(wanted)
                        .case_insensitive(op.contains("~~"))
                        .build()
                        .is_ok_and(|r| r.is_match(&actual_text));
                    if op.starts_with('!') {
                        !matched
                    } else {
                        matched
                    }
                }
            }
        }
    }
}
fn validate(e: &Expr, schema: &Row) -> Result<(), QueryError> {
    match e {
        Expr::Atom(column, _, _) => {
            if schema.contains_key(column) {
                Ok(())
            } else {
                Err(err(format!("unknown column {column}")))
            }
        }
        Expr::And(items) | Expr::Or(items) => {
            for e in items {
                validate(e, schema)?;
            }
            Ok(())
        }
        Expr::Not(e) => validate(e, schema),
    }
}
pub fn execute(q: &Query, rows: &[Row], schema: &Row) -> Result<Vec<u8>, QueryError> {
    for col in &q.columns {
        if !schema.contains_key(col) {
            return Err(err(format!("unknown column {col}")));
        }
    }
    for f in &q.filters {
        validate(f, schema)?;
    }
    for s in &q.stats {
        match s {
            Statistic::Count(e) => validate(e, schema)?,
            Statistic::Aggregate(_, col) => {
                if !schema.contains_key(col) {
                    return Err(err(format!("unknown column {col}")));
                }
            }
        }
    }
    let filtered: Vec<_> = rows
        .iter()
        .filter(|r| q.filters.iter().all(|f| eval(f, r)))
        .collect();
    let columns: Vec<_> = if q.columns.is_empty() && q.stats.is_empty() {
        schema.keys().cloned().collect()
    } else {
        q.columns.clone()
    };
    let mut data: Vec<Vec<Value>> = Vec::new();
    if q.stats.is_empty() {
        for row in filtered {
            data.push(
                columns
                    .iter()
                    .map(|c| {
                        row.get(c)
                            .or_else(|| schema.get(c))
                            .cloned()
                            .unwrap_or(Value::Null)
                    })
                    .collect(),
            );
        }
    } else {
        let mut groups: BTreeMap<String, (Vec<Value>, Vec<&Row>)> = BTreeMap::new();
        if columns.is_empty() {
            groups.insert(String::new(), (Vec::new(), Vec::new()));
        }
        for row in filtered {
            let keys: Vec<_> = columns
                .iter()
                .map(|c| row.get(c).cloned().unwrap_or(Value::Null))
                .collect();
            let key = if keys.is_empty() {
                String::new()
            } else {
                serde_json::to_string(&keys).map_err(|e| err(e.to_string()))?
            };
            groups
                .entry(key)
                .or_insert_with(|| (keys, Vec::new()))
                .1
                .push(row);
        }
        for (_, (mut keys, rows)) in groups {
            for stat in &q.stats {
                keys.push(match stat {
                    Statistic::Count(e) => json!(rows.iter().filter(|r| eval(e, r)).count()),
                    Statistic::Aggregate(op, col) => {
                        let values: Vec<_> =
                            rows.iter().filter_map(|r| r.get(col)?.as_f64()).collect();
                        let sum: f64 = values.iter().sum();
                        let n = values.len() as f64;
                        json!(match op.as_str() {
                            "sum" => sum,
                            "min" => values.iter().copied().reduce(f64::min).unwrap_or(0.0),
                            "max" => values.iter().copied().reduce(f64::max).unwrap_or(0.0),
                            "std" if n > 0.0 =>
                                (values.iter().map(|v| (v - sum / n).powi(2)).sum::<f64>() / n)
                                    .sqrt(),
                            _ if n > 0.0 => sum / n,
                            _ => 0.0,
                        })
                    }
                });
            }
            data.push(keys);
        }
    }
    let total = data.len();
    let mut data: Vec<_> = data.into_iter().skip(q.offset).take(q.limit).collect();
    let mut headers = columns;
    for i in 0..q.stats.len() {
        headers.push(format!("stats_{i}"));
    }
    let body = match q.output_format {
        OutputFormat::WrappedJson => serde_json::to_vec(
            &json!({"data":data,"columns":headers,"total_count":total,"rows_scanned":rows.len()}),
        )
        .map_err(|e| err(e.to_string()))?,
        OutputFormat::Json => {
            if q.column_headers {
                data.insert(0, headers.into_iter().map(Value::String).collect());
            }
            serde_json::to_vec(&data).map_err(|e| err(e.to_string()))?
        }
        OutputFormat::Csv => {
            let mut output = String::new();
            if q.column_headers {
                output.push_str(&headers.join(";"));
                output.push('\n');
            }
            for row in data {
                output.push_str(
                    &row.iter()
                        .map(|v| match v {
                            Value::Array(items) => {
                                items.iter().map(text).collect::<Vec<_>>().join(",")
                            }
                            _ => text(v).replace('\n', "\\n").replace(';', "\\;"),
                        })
                        .collect::<Vec<_>>()
                        .join(";"),
                );
                output.push('\n');
            }
            output.into_bytes()
        }
    };
    Ok(if q.response_header == ResponseHeader::Fixed16 {
        fixed16_response(200, &body)
    } else {
        body
    })
}
pub fn fixed16_response(status: u16, body: &[u8]) -> Vec<u8> {
    let mut response = format!("{status:03} {:11}\n", body.len()).into_bytes();
    response.extend_from_slice(body);
    response
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn numeric_comparisons_boolean_stats_and_flat_json_headers() {
        let schema = Row::from([("name".into(), json!("")), ("state".into(), json!(0))]);
        let rows = vec![
            Row::from([("name".into(), json!("edge")), ("state".into(), json!(2))]),
            Row::from([("name".into(), json!("db")), ("state".into(), json!(10))]),
        ];
        let q=parse_query("GET services\nColumns: name state\nFilter: state >= 3\nOutputFormat: json\nColumnHeaders: on\n\n").unwrap();
        assert_eq!(
            execute(&q, &rows, &schema).unwrap(),
            br#"[["name","state"],["db",10]]"#
        );
        let q = parse_query(
            "GET services\nStats: state = 2\nStats: state = 10\nStatsOr: 2\nOutputFormat: json\n\n",
        )
        .unwrap();
        assert_eq!(execute(&q, &rows, &schema).unwrap(), b"[[2]]");
    }
    #[test]
    fn unsupported_queries_do_not_report_success() {
        assert!(parse_query("GET hosts\nFilter: name magic value\n\n").is_err());
        assert!(parse_query("GET hosts\nAnd: 1\n\n").is_err());
        assert!(parse_query("GET hosts\nWaitCondition: name = a\n\n").is_err());
        let q = parse_query("GET hosts\nColumns: invented\n\n").unwrap();
        assert!(execute(&q, &[], &Row::new()).is_err());
    }
    #[test]
    fn fixed16_counts_bytes_not_characters() {
        let response = fixed16_response(200, "été".as_bytes());
        assert_eq!(&response[..16], b"200           5\n");
        assert_eq!(&response[16..], "été".as_bytes());
    }
}
