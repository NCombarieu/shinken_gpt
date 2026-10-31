#!/usr/bin/env python3
"""TimeSeries Database adapter for Shinken metrics.

Provides abstraction for storing performance data (perfdata) and metrics
in InfluxDB for graphing, trending, and alerting.

Usage:
    from shinken.timeseries_adapter import InfluxDBAdapter

    adapter = InfluxDBAdapter(host='localhost', port=8086, database='shinken')
    adapter.write_metric(
        measurement='host_cpu',
        tags={'host': 'web-01', 'check': 'check_cpu'},
        fields={'value': 87.5, 'warning': 80, 'critical': 95},
        timestamp=1234567890000000000  # nanoseconds
    )
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, Optional, List, Any
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class Metric:
    """Represents a single metric point."""
    measurement: str
    tags: Dict[str, str]
    fields: Dict[str, float]
    timestamp: int  # Unix timestamp in nanoseconds (InfluxDB format)

    def to_influx_line(self) -> str:
        """Convert to InfluxDB line protocol format."""
        # Format: measurement,tag1=val1,tag2=val2 field1=1.0,field2=2.0 timestamp
        tag_str = ','.join(f"{k}={v}" for k, v in self.tags.items())
        field_str = ','.join(f"{k}={v}" for k, v in self.fields.items())

        if tag_str:
            return f"{self.measurement},{tag_str} {field_str} {self.timestamp}"
        return f"{self.measurement} {field_str} {self.timestamp}"


class TimeSeriesAdapter(ABC):
    """Abstract base class for TimeSeries database adapters."""

    @abstractmethod
    def connect(self) -> None:
        """Establish connection to the database."""
        pass

    @abstractmethod
    def write_metric(self, metric: Metric) -> bool:
        """Write a single metric point."""
        pass

    @abstractmethod
    def write_metrics(self, metrics: List[Metric]) -> bool:
        """Write multiple metric points (batch)."""
        pass

    @abstractmethod
    def query(self, query: str) -> List[Dict[str, Any]]:
        """Execute a query and return results."""
        pass

    @abstractmethod
    def close(self) -> None:
        """Close the database connection."""
        pass


class InfluxDBAdapter(TimeSeriesAdapter):
    """InfluxDB 2.x adapter for Shinken metrics."""

    def __init__(
        self,
        host: str = 'localhost',
        port: int = 8086,
        database: str = 'shinken',
        username: str = '',
        password: str = '',
        ssl: bool = False,
        timeout: int = 10,
    ):
        """Initialize InfluxDB adapter.

        Args:
            host: InfluxDB host
            port: InfluxDB port
            database: Database name (bucket in InfluxDB 2.x)
            username: Username for authentication
            password: Password for authentication
            ssl: Use HTTPS
            timeout: Connection timeout in seconds
        """
        self.host = host
        self.port = port
        self.database = database
        self.username = username
        self.password = password
        self.ssl = ssl
        self.timeout = timeout
        self.client = None
        self.connected = False

    def connect(self) -> None:
        """Establish connection to InfluxDB."""
        try:
            from influxdb_client import InfluxDBClient
            from influxdb_client.client.write_api import SYNCHRONOUS

            scheme = 'https' if self.ssl else 'http'
            url = f"{scheme}://{self.host}:{self.port}"

            self.client = InfluxDBClient(
                url=url,
                token=self.password if self.username == 'token' else None,
                username=self.username if self.username != 'token' else None,
                password=self.password if self.username != 'token' else None,
                org='',  # Default org
                timeout=self.timeout * 1000,  # Convert to ms
            )
            self.write_api = self.client.write_api(write_options=SYNCHRONOUS)
            self.connected = True
            logger.info(f"Connected to InfluxDB at {url}/{self.database}")
        except ImportError:
            logger.error("influxdb-client not installed. Install with: pip install influxdb-client")
            self.connected = False
        except Exception as e:
            logger.error(f"Failed to connect to InfluxDB: {e}")
            self.connected = False

    def write_metric(self, metric: Metric) -> bool:
        """Write a single metric point to InfluxDB."""
        if not self.connected:
            logger.warning("Not connected to InfluxDB, skipping metric write")
            return False

        try:
            line = metric.to_influx_line()
            self.write_api.write(
                bucket=self.database,
                record=line,
            )
            return True
        except Exception as e:
            logger.error(f"Failed to write metric {metric.measurement}: {e}")
            return False

    def write_metrics(self, metrics: List[Metric]) -> bool:
        """Write multiple metrics to InfluxDB (batch)."""
        if not self.connected:
            logger.warning("Not connected to InfluxDB, skipping batch write")
            return False

        try:
            lines = '\n'.join(m.to_influx_line() for m in metrics)
            self.write_api.write(
                bucket=self.database,
                record=lines,
            )
            logger.debug(f"Wrote {len(metrics)} metrics to InfluxDB")
            return True
        except Exception as e:
            logger.error(f"Failed to write {len(metrics)} metrics: {e}")
            return False

    def query(self, query: str) -> List[Dict[str, Any]]:
        """Query metrics from InfluxDB."""
        if not self.connected:
            logger.warning("Not connected to InfluxDB")
            return []

        try:
            from influxdb_client import Query

            query_api = self.client.query_api()
            result = query_api.query(query)

            # Convert to list of dicts
            records = []
            for table in result:
                for record in table.records:
                    records.append({
                        'measurement': record.measurement,
                        'tags': record.tags,
                        'field': record.field,
                        'value': record.value,
                        'time': record.get_time(),
                    })
            return records
        except Exception as e:
            logger.error(f"Query failed: {e}")
            return []

    def close(self) -> None:
        """Close InfluxDB connection."""
        if self.client:
            self.client.close()
            self.connected = False
            logger.info("Closed InfluxDB connection")


class MetricsBuilder:
    """Helper to build metrics from Shinken check results."""

    @staticmethod
    def from_check_result(
        host_name: str,
        service_description: Optional[str],
        perfdata: str,
        output: str,
        timestamp: Optional[int] = None,
        tags: Optional[Dict[str, str]] = None,
    ) -> List[Metric]:
        """Build metrics from a Shinken check result's perfdata.

        Perfdata format (Nagios standard):
        'metric1=value1[UOM];warn;crit;min;max metric2=value2[UOM]...'

        Example:
        'cpu=87.5%;80;95;0;100 memory=3456MB;4096;5120;0;8192'

        Args:
            host_name: Host name
            service_description: Service name (optional)
            perfdata: Perfdata string from check output
            output: Full check output
            timestamp: Unix timestamp (ns), defaults to now
            tags: Additional tags to add

        Returns:
            List of Metric objects
        """
        if timestamp is None:
            timestamp = int(datetime.utcnow().timestamp() * 1e9)

        if not tags:
            tags = {}

        tags.update({
            'host': host_name,
            'service': service_description or 'host',
        })

        metrics = []

        # Parse perfdata: "name=value[UOM];warn;crit;min;max"
        if perfdata:
            for part in perfdata.split():
                if '=' not in part:
                    continue

                metric_name, values = part.split('=', 1)
                # Remove UOM (unit of measurement) and warnings/critical
                value_str = values.split(';')[0].rstrip('kmgtKMGT%')

                try:
                    value = float(value_str)
                    metric = Metric(
                        measurement=f"check_{metric_name}",
                        tags=tags,
                        fields={'value': value},
                        timestamp=timestamp,
                    )
                    metrics.append(metric)
                except ValueError:
                    logger.debug(f"Could not parse metric value: {value_str}")

        return metrics
