from __future__ import annotations

import atexit
import logging
import os
from datetime import UTC, datetime
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://localhost:9090")

# Create an MCP server
mcp = FastMCP()

# HTTP client for making requests to Prometheus
http_client = httpx.AsyncClient(timeout=30.0)


class PrometheusAPIError(Exception):
    """Custom exception for Prometheus API errors."""


def _raise_prometheus_error(msg: str) -> None:
    """Helper function to raise PrometheusAPIError."""
    raise PrometheusAPIError(msg)


async def _execute_single_query(query: str, metric_name: str) -> dict[str, Any]:
    """Execute a single query and handle errors without try-except in loop."""
    try:
        query_result = await query_prometheus(query)
        return {
            "query": query,
            "data": query_result["data"],
            "status": query_result["status"],
        }
    except PrometheusAPIError as exc:
        logger.warning(f"Failed to execute query for {metric_name}: {exc}")
        return {
            "query": query,
            "error": str(exc),
            "status": "error",
        }


async def _execute_alert_query(
    alert_name: str, alert_config: dict[str, Any],
) -> dict[str, Any]:
    """Execute an alert query and handle errors without try-except in loop."""
    try:
        query_result = await query_prometheus(alert_config["query"])

        # Check if alert is firing (has results)
        is_firing = len(query_result["data"].get("result", [])) > 0

        return {
            "query": alert_config["query"],
            "description": alert_config["description"],
            "severity": alert_config["severity"],
            "firing": is_firing,
            "data": query_result["data"] if is_firing else None,
        }
    except PrometheusAPIError as exc:
        logger.warning(f"Failed to execute alert query for {alert_name}: {exc}")
        return {
            "query": alert_config["query"],
            "description": alert_config["description"],
            "severity": alert_config["severity"],
            "error": str(exc),
            "firing": False,
        }


async def make_prometheus_request(
    endpoint: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Make a request to Prometheus API."""
    url = f"{PROMETHEUS_URL}/api/v1{endpoint}"

    try:
        logger.debug(f"Making request to: {url} with params: {params}")
        response = await http_client.get(url, params=params)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as exc:
        logger.exception("HTTP error when calling Prometheus API:")
        msg = f"Failed to call Prometheus API: {exc}"
        raise PrometheusAPIError(msg) from exc
    except Exception as exc:
        logger.exception("Unexpected error when calling Prometheus API")
        msg = f"Unexpected error: {exc}"
        raise PrometheusAPIError(msg) from exc


@mcp.tool()
async def query_prometheus(
    query: str,
    time: str | None = None,
) -> dict[str, Any]:
    """
    Execute a PromQL query against Prometheus for instant values.

    Args:
        query (str): The PromQL query to execute
        time (str | None): Evaluation timestamp (RFC3339 or Unix timestamp).
                          Defaults to current time if not specified.

    Returns:
        dict[str, Any]: Query results with data, status, and metadata

    """
    try:
        logger.info(f"Executing Prometheus query: {query}")

        if not query:
            _raise_prometheus_error("Query is required")

        params = {"query": query}
        if time:
            params["time"] = time

        # Call Prometheus API to execute query
        response = await make_prometheus_request("/query", params)

        if response.get("status") != "success":
            error_msg = response.get("error", "Unknown error")
            _raise_prometheus_error(f"Prometheus query failed: {error_msg}")

        result = {
            "query": query,
            "status": response["status"],
            "data": response["data"],
            "executed_at": datetime.now(UTC).isoformat(),
        }

        # Add warnings if present
        if "warnings" in response:
            result["warnings"] = response["warnings"]

    except PrometheusAPIError:
        raise
    except Exception as exc:
        logger.exception("Error executing Prometheus query:")
        msg = f"Failed to execute query: {exc}"
        raise PrometheusAPIError(msg) from exc
    else:
        result_type = response["data"].get("resultType", "unknown")
        result_count = len(response["data"].get("result", []))
        logger.info(
            f"Successfully executed query, result type: {result_type}, count: {result_count}",
        )
        return result


@mcp.tool()
async def query_range_prometheus(
    query: str,
    start: str,
    end: str,
    step: str = "15s",
) -> dict[str, Any]:
    """
    Execute a PromQL query against Prometheus for a range of time.

    Args:
        query (str): The PromQL query to execute
        start (str): Start timestamp (RFC3339 or Unix timestamp)
        end (str): End timestamp (RFC3339 or Unix timestamp)
        step (str): Query resolution step width in duration format (e.g., '15s', '1m', '5m')

    Returns:
        dict[str, Any]: Range query results with data, status, and metadata

    """
    try:
        logger.info(f"Executing Prometheus range query: {query} from {start} to {end}")

        if not query:
            _raise_prometheus_error("Query is required")
        if not start:
            _raise_prometheus_error("Start time is required")
        if not end:
            _raise_prometheus_error("End time is required")

        params = {
            "query": query,
            "start": start,
            "end": end,
            "step": step,
        }

        # Call Prometheus API to execute range query
        response = await make_prometheus_request("/query_range", params)

        if response.get("status") != "success":
            error_msg = response.get("error", "Unknown error")
            _raise_prometheus_error(f"Prometheus range query failed: {error_msg}")

        result = {
            "query": query,
            "start": start,
            "end": end,
            "step": step,
            "status": response["status"],
            "data": response["data"],
            "executed_at": datetime.now(UTC).isoformat(),
        }

        # Add warnings if present
        if "warnings" in response:
            result["warnings"] = response["warnings"]

    except PrometheusAPIError:
        raise
    except Exception as exc:
        logger.exception("Error executing Prometheus range query:")
        msg = f"Failed to execute range query: {exc}"
        raise PrometheusAPIError(msg) from exc
    else:
        result_type = response["data"].get("resultType", "unknown")
        result_count = len(response["data"].get("result", []))
        logger.info(
            f"Successfully executed range query, result type: {result_type}, count: {result_count}",
        )
        return result


@mcp.tool()
async def get_metrics_metadata() -> dict[str, Any]:
    """
    Retrieve metadata about available metrics from Prometheus.

    Returns:
        dict[str, Any]: Dictionary containing metric metadata including names, types, and help text

    """
    try:
        logger.info("Fetching metrics metadata from Prometheus")

        # Call Prometheus API to get metadata
        response = await make_prometheus_request("/metadata")

        if response.get("status") != "success":
            error_msg = response.get("error", "Unknown error")
            _raise_prometheus_error(f"Failed to get metadata: {error_msg}")

        metadata = response["data"]

        # Format the response
        result = {
            "total_metrics": len(metadata),
            "metrics": {},
            "retrieved_at": datetime.now(UTC).isoformat(),
        }

        # Process metadata for each metric
        for metric_name, metric_info in metadata.items():
            if isinstance(metric_info, list) and metric_info:
                # Take the first entry if multiple exist
                info = metric_info[0]
                result["metrics"][metric_name] = {
                    "type": info.get("type", "unknown"),
                    "help": info.get("help", ""),
                    "unit": info.get("unit", ""),
                }

    except PrometheusAPIError:
        raise
    except Exception as exc:
        logger.exception("Error getting metrics metadata:")
        msg = f"Failed to get metrics metadata: {exc}"
        raise PrometheusAPIError(msg) from exc
    else:
        logger.info(
            f"Successfully retrieved metadata for {result['total_metrics']} metrics",
        )
        return result


@mcp.tool()
async def get_label_names() -> dict[str, Any]:
    """
    Retrieve all label names from Prometheus.

    Returns:
        dict[str, Any]: Dictionary containing list of available label names

    """
    try:
        logger.info("Fetching label names from Prometheus")

        # Call Prometheus API to get label names
        response = await make_prometheus_request("/labels")

        if response.get("status") != "success":
            error_msg = response.get("error", "Unknown error")
            _raise_prometheus_error(f"Failed to get label names: {error_msg}")

        result = {
            "labels": response["data"],
            "total_labels": len(response["data"]),
            "retrieved_at": datetime.now(UTC).isoformat(),
        }

    except PrometheusAPIError:
        raise
    except Exception as exc:
        logger.exception("Error getting label names:")
        msg = f"Failed to get label names: {exc}"
        raise PrometheusAPIError(msg) from exc
    else:
        logger.info(f"Successfully retrieved {result['total_labels']} label names")
        return result


@mcp.tool()
async def get_label_values(label_name: str) -> dict[str, Any]:
    """
    Retrieve all values for a specific label from Prometheus.

    Args:
        label_name (str): The name of the label to get values for

    Returns:
        dict[str, Any]: Dictionary containing list of values for the specified label

    """
    try:
        logger.info(f"Fetching values for label: {label_name}")

        if not label_name:
            _raise_prometheus_error("Label name is required")

        # Call Prometheus API to get label values
        response = await make_prometheus_request(f"/label/{label_name}/values")

        if response.get("status") != "success":
            error_msg = response.get("error", "Unknown error")
            _raise_prometheus_error(f"Failed to get label values: {error_msg}")

        result = {
            "label_name": label_name,
            "values": response["data"],
            "total_values": len(response["data"]),
            "retrieved_at": datetime.now(UTC).isoformat(),
        }

    except PrometheusAPIError:
        raise
    except Exception as exc:
        logger.exception("Error getting label values:")
        msg = f"Failed to get label values: {exc}"
        raise PrometheusAPIError(msg) from exc
    else:
        logger.info(
            f"Successfully retrieved {result['total_values']} values for label {label_name}",
        )
        return result


@mcp.tool()
async def get_series(
    match: list[str],
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any]:
    """
    Find series matching label selectors.

    Args:
        match (list[str]): List of series selectors (e.g., ['up', 'http_requests_total{job="api"}'])
        start (str | None): Start timestamp (RFC3339 or Unix timestamp)
        end (str | None): End timestamp (RFC3339 or Unix timestamp)

    Returns:
        dict[str, Any]: Dictionary containing matching series information

    """
    try:
        logger.info(f"Finding series matching: {match}")

        if not match:
            _raise_prometheus_error("At least one match selector is required")

        params = {}
        for i, selector in enumerate(match):
            params["match[]"] = selector if i == 0 else params["match[]"] + [selector]

        # Handle single match case
        if len(match) == 1:
            params["match[]"] = match[0]
        else:
            # For multiple matches, we need to format properly
            params = {"match[]": match}

        if start:
            params["start"] = start
        if end:
            params["end"] = end

        # Call Prometheus API to find series
        response = await make_prometheus_request("/series", params)

        if response.get("status") != "success":
            error_msg = response.get("error", "Unknown error")
            _raise_prometheus_error(f"Failed to find series: {error_msg}")

        result = {
            "match_selectors": match,
            "start": start,
            "end": end,
            "series": response["data"],
            "total_series": len(response["data"]),
            "retrieved_at": datetime.now(UTC).isoformat(),
        }

    except PrometheusAPIError:
        raise
    except Exception as exc:
        logger.exception("Error finding series:")
        msg = f"Failed to find series: {exc}"
        raise PrometheusAPIError(msg) from exc
    else:
        logger.info(f"Successfully found {result['total_series']} series")
        return result


@mcp.tool()
async def analyze_http_metrics(
    service_name: str | None = None,
    time_range: str = "5m",
) -> dict[str, Any]:
    """
    Analyze HTTP metrics for services including request rates, response times, and error rates.

    Args:
        service_name (str | None): Specific service to analyze. If None, analyzes all services.
        time_range (str): Time range for rate calculations (e.g., '5m', '1h'). Defaults to '5m'.

    Returns:
        dict[str, Any]: Comprehensive HTTP metrics analysis

    """
    try:
        logger.info(f"Analyzing HTTP metrics for service: {service_name}")

        service_filter = f'{{service_name="{service_name}"}}' if service_name else ""

        # Define queries for HTTP metrics analysis
        queries = {
            "request_rate": f"rate(http_server_duration_milliseconds_count{service_filter}[{time_range}])",
            "avg_response_time": f"rate(http_server_duration_milliseconds_sum{service_filter}[{time_range}]) / rate(http_server_duration_milliseconds_count{service_filter}[{time_range}])",
            "p95_response_time": f"histogram_quantile(0.95, rate(http_server_duration_milliseconds_bucket{service_filter}[{time_range}]))",
            "p99_response_time": f"histogram_quantile(0.99, rate(http_server_duration_milliseconds_bucket{service_filter}[{time_range}]))",
            "error_rate": f'rate(http_server_duration_milliseconds_count{service_filter}{{http_response_status_code=~"5.."}}[{time_range}])',
            "client_error_rate": f'rate(http_server_duration_milliseconds_count{service_filter}{{http_response_status_code=~"4.."}}[{time_range}])',
            "active_requests": f"http_server_active_requests{service_filter}",
            "avg_response_size": f"rate(http_server_response_size_bytes_sum{service_filter}[{time_range}]) / rate(http_server_response_size_bytes_count{service_filter}[{time_range}])",
        }

        result = {
            "service_name": service_name,
            "time_range": time_range,
            "analysis_time": datetime.now(UTC).isoformat(),
            "metrics": {},
        }

        # Execute each query
        for metric_name, query in queries.items():
            query_result = await _execute_single_query(query, metric_name)
            result["metrics"][metric_name] = query_result

    except PrometheusAPIError:
        raise
    except Exception as exc:
        logger.exception("Error analyzing HTTP metrics:")
        msg = f"Failed to analyze HTTP metrics: {exc}"
        raise PrometheusAPIError(msg) from exc
    else:
        logger.info(f"Successfully analyzed HTTP metrics for service: {service_name}")
        return result


@mcp.tool()
async def check_alerting_thresholds(
    service_name: str | None = None,
) -> dict[str, Any]:
    """
    Check current metrics against common alerting thresholds.

    Args:
        service_name (str | None): Specific service to check. If None, checks all services.

    Returns:
        dict[str, Any]: Alert status for various thresholds

    """
    try:
        logger.info(f"Checking alerting thresholds for service: {service_name}")

        service_filter = f'{{service_name="{service_name}"}}' if service_name else ""

        # Define alerting threshold queries
        alert_queries = {
            "high_error_rate": {
                "query": f'rate(http_server_duration_milliseconds_count{service_filter}{{http_response_status_code=~"5.."}}[5m]) > 0.05',
                "description": "Error rate > 5%",
                "severity": "critical",
            },
            "high_response_time": {
                "query": f"histogram_quantile(0.95, rate(http_server_duration_milliseconds_bucket{service_filter}[5m])) > 1000",
                "description": "95th percentile response time > 1000ms",
                "severity": "warning",
            },
            "high_active_requests": {
                "query": f"http_server_active_requests{service_filter} > 100",
                "description": "Active requests > 100",
                "severity": "warning",
            },
            "low_request_rate": {
                "query": f"rate(http_server_duration_milliseconds_count{service_filter}[5m]) < 0.1",
                "description": "Request rate < 0.1 req/sec (possible service down)",
                "severity": "critical",
            },
            "high_client_error_rate": {
                "query": f'rate(http_client_duration_milliseconds_count{service_filter}{{http_response_status_code=~"4.."}}[5m]) > 0.1',
                "description": "Client error rate > 10%",
                "severity": "warning",
            },
        }

        result = {
            "service_name": service_name,
            "check_time": datetime.now(UTC).isoformat(),
            "alerts": {},
            "summary": {
                "total_checks": len(alert_queries),
                "firing_alerts": 0,
                "critical_alerts": 0,
                "warning_alerts": 0,
            },
        }

        # Execute each alert query
        for alert_name, alert_config in alert_queries.items():
            alert_result = await _execute_alert_query(alert_name, alert_config)
            result["alerts"][alert_name] = alert_result

            if alert_result["firing"]:
                result["summary"]["firing_alerts"] += 1
                if alert_config["severity"] == "critical":
                    result["summary"]["critical_alerts"] += 1
                elif alert_config["severity"] == "warning":
                    result["summary"]["warning_alerts"] += 1

    except PrometheusAPIError:
        raise
    except Exception as exc:
        logger.exception("Error checking alerting thresholds:")
        msg = f"Failed to check alerting thresholds: {exc}"
        raise PrometheusAPIError(msg) from exc
    else:
        logger.info(
            f"Successfully checked alerting thresholds, {result['summary']['firing_alerts']} alerts firing",
        )
        return result


# Cleanup function
async def cleanup():
    """Cleanup resources."""
    await http_client.aclose()


# Register cleanup
atexit.register(lambda: http_client.aclose())


if __name__ == "__main__":
    # Run the server
    logger.info(f"Starting Prometheus MCP server with Prometheus URL: {PROMETHEUS_URL}")
    mcp.run()
