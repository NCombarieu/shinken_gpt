//! Livestatus request boundary used by Thruk.

use thiserror::Error;

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Query {
    pub table: String,
    pub columns: Vec<String>,
    pub filters: Vec<String>,
    pub output_format: OutputFormat,
    pub response_header: ResponseHeader,
    pub column_headers: bool,
    pub limit: Option<usize>,
    /// Extensions not yet interpreted by the engine, retained in input order.
    pub extensions: Vec<(String, String)>,
}

#[derive(Clone, Copy, Debug, Default, Eq, PartialEq)]
pub enum OutputFormat {
    #[default]
    Csv,
    Json,
    Python,
    WrappedJson,
}

#[derive(Clone, Copy, Debug, Default, Eq, PartialEq)]
pub enum ResponseHeader {
    #[default]
    Off,
    Fixed16,
}

#[derive(Debug, Error, Eq, PartialEq)]
pub enum QueryError {
    #[error("Livestatus request must start with GET")]
    MissingGet,
    #[error("GET requires a table name")]
    MissingTable,
    #[error("unsupported output format: {0}")]
    UnsupportedOutputFormat(String),
    #[error("unsupported response header: {0}")]
    UnsupportedResponseHeader(String),
    #[error("invalid limit: {0}")]
    InvalidLimit(String),
}

pub fn parse_query(input: &str) -> Result<Query, QueryError> {
    let mut lines = input.lines();
    let first = lines.next().ok_or(QueryError::MissingGet)?;
    let table = first
        .strip_prefix("GET ")
        .ok_or(QueryError::MissingGet)?
        .trim();
    if table.is_empty() {
        return Err(QueryError::MissingTable);
    }

    let mut query = Query {
        table: table.to_owned(),
        columns: Vec::new(),
        filters: Vec::new(),
        output_format: OutputFormat::default(),
        response_header: ResponseHeader::default(),
        column_headers: false,
        limit: None,
        extensions: Vec::new(),
    };

    for line in lines.map(str::trim).take_while(|line| !line.is_empty()) {
        let (name, value) = line.split_once(':').unwrap_or((line, ""));
        let value = value.trim();
        match name {
            "Columns" => query.columns = value.split_whitespace().map(str::to_owned).collect(),
            "Filter" => query.filters.push(value.to_owned()),
            "OutputFormat" => {
                query.output_format = match value.to_ascii_lowercase().as_str() {
                    "csv" => OutputFormat::Csv,
                    "json" => OutputFormat::Json,
                    "python" => OutputFormat::Python,
                    "wrapped_json" => OutputFormat::WrappedJson,
                    _ => return Err(QueryError::UnsupportedOutputFormat(value.to_owned())),
                };
            }
            "ResponseHeader" => {
                query.response_header = match value.to_ascii_lowercase().as_str() {
                    "off" => ResponseHeader::Off,
                    "fixed16" => ResponseHeader::Fixed16,
                    _ => return Err(QueryError::UnsupportedResponseHeader(value.to_owned())),
                };
            }
            "ColumnHeaders" => query.column_headers = value.eq_ignore_ascii_case("on"),
            "Limit" => {
                query.limit = Some(
                    value
                        .parse()
                        .map_err(|_| QueryError::InvalidLimit(value.to_owned()))?,
                );
            }
            _ => query.extensions.push((name.to_owned(), value.to_owned())),
        }
    }
    Ok(query)
}

#[must_use]
pub fn fixed16_response(status: u16, body: &[u8]) -> Vec<u8> {
    let mut response = format!("{status:03} {:11}\n", body.len()).into_bytes();
    response.extend_from_slice(body);
    response
}

#[cfg(test)]
mod tests {
    use super::{fixed16_response, parse_query, OutputFormat, ResponseHeader};

    #[test]
    fn parses_a_thruk_style_query_without_losing_extensions() {
        let query = parse_query(
            "GET services\nColumns: host_name description state\nFilter: state != 0\nOutputFormat: json\nResponseHeader: fixed16\nColumnHeaders: on\nLimit: 50\nAuthUser: alice\n\n",
        )
        .unwrap();
        assert_eq!(query.table, "services");
        assert_eq!(query.columns, ["host_name", "description", "state"]);
        assert_eq!(query.filters, ["state != 0"]);
        assert_eq!(query.output_format, OutputFormat::Json);
        assert_eq!(query.response_header, ResponseHeader::Fixed16);
        assert!(query.column_headers);
        assert_eq!(query.limit, Some(50));
        assert_eq!(query.extensions, [("AuthUser".into(), "alice".into())]);
    }

    #[test]
    fn fixed_header_is_sixteen_bytes() {
        let response = fixed16_response(200, b"[]\n");
        assert_eq!(&response[..16], b"200           3\n");
        assert_eq!(&response[16..], b"[]\n");
    }
}
