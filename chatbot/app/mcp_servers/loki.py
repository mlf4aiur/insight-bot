from __future__ import annotations

import atexit
import logging
import os
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote

import httpx
from mcp.server.fastmcp import FastMCP

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

LOKI_URL = os.getenv("LOKI_URL", "http://localhost:3100")

# Create an MCP server
mcp = FastMCP()

# HTTP client for making requests to Loki
http_client = httpx.AsyncClient(timeout=30.0)


class LokiAPIError(Exception):
    """Custom exception for Loki API errors."""


def _raise_loki_error(msg: str) -> None:
    """Helper function to raise LokiAPIError."""
    raise LokiAPIError(msg)


async def make_loki_request(
    endpoint: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Make a request to Loki API."""
    url = f"{LOKI_URL}{endpoint}"

    try:
        logger.debug(f"Making request to: {url} with params: {params}")
        response = await http_client.get(url, params=params)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as exc:
        logger.exception("HTTP error when calling Loki API:")
        msg = f"Failed to call Loki API: {exc}"
        raise LokiAPIError(msg) from exc
    except Exception as exc:
        logger.exception("Unexpected error when calling Loki API")
        msg = f"Unexpected error: {exc}"
        raise LokiAPIError(msg) from exc


def _format_time_for_loki(time_str: str | None) -> str | None:
    """Convert time string to RFC3339 format for Loki API."""
    if not time_str:
        return None

    try:
        # Handle relative time formats like "5m", "1h", "24h"
        if time_str.endswith(("m", "h", "s")):
            unit = time_str[-1]
            value = int(time_str[:-1])

            if unit == "s":
                delta = timedelta(seconds=value)
            elif unit == "m":
                delta = timedelta(minutes=value)
            elif unit == "h":
                delta = timedelta(hours=value)
            else:
                return None

            target_time = datetime.now(UTC) - delta
            return target_time.strftime("%Y-%m-%dT%H:%M:%S.%fZ")

        # Handle ISO format
        if "T" in time_str:
            dt = datetime.fromisoformat(time_str)
            return dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    except (ValueError, TypeError):
        logger.warning(f"Could not parse time string: {time_str}")
        return time_str
    else:
        return time_str


def _build_query_params(
    query: str,
    start_time: str | None,
    end_time: str | None,
    limit: int,
    direction: str,
) -> dict[str, Any]:
    """Build query parameters for Loki API."""
    params = {"query": query, "limit": limit, "direction": direction}

    if start_time:
        formatted_start = _format_time_for_loki(start_time)
        if formatted_start:
            params["start"] = formatted_start

    if end_time:
        formatted_end = _format_time_for_loki(end_time)
        if formatted_end:
            params["end"] = formatted_end

    return params


def _format_log_entries(
    results: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    """Format log entries from Loki API response."""
    formatted_logs = []
    total_entries = 0

    for stream in results:
        stream_labels = stream.get("stream", {})
        values = stream.get("values", [])
        total_entries += len(values)

        for value in values:
            timestamp_ns, log_line = value
            # Convert nanosecond timestamp to datetime
            timestamp_dt = datetime.fromtimestamp(
                int(timestamp_ns) / 1_000_000_000,
                tz=UTC,
            )

            formatted_logs.append(
                {
                    "timestamp": timestamp_dt.isoformat(),
                    "timestamp_ns": timestamp_ns,
                    "log_line": log_line,
                    "stream_labels": stream_labels,
                    "service_name": stream_labels.get("service_name", ""),
                    "severity_text": stream_labels.get("severity_text", ""),
                },
            )

    return formatted_logs, total_entries


@mcp.tool()
async def query_logs(
    query: str,
    start_time: str | None = None,
    end_time: str | None = None,
    limit: int = 100,
    direction: str = "backward",
) -> dict[str, Any]:
    """
    Query Loki for logs using LogQL syntax.

    Args:
        query (str): LogQL query string.
            To filter by labels (e.g., `service_name`), use the stream selector: `{service_name="user-service"}`.
            To filter by fields within JSON logs (e.g., `severity_text`), parse the log and then filter: `| json | severity_text="ERROR"`.
            Example: `{service_name="user-service"} | json | severity_text="ERROR"`
        start_time (str | None): Start time for query (RFC3339 or relative like "5m", "1h")
        end_time (str | None): End time for query (RFC3339 format)
        limit (int): Maximum number of log entries to return (default: 100)
        direction (str): Query direction - "forward" or "backward" (default: "backward")

    Returns:
        dict[str, Any]: Query results with logs, statistics, and metadata.

    """
    try:
        logger.info(f"Querying Loki with query: {query}")

        if not query:
            _raise_loki_error("Query is required")

        # Build query parameters
        params = _build_query_params(query, start_time, end_time, limit, direction)

        # Call Loki API
        response = await make_loki_request("/loki/api/v1/query_range", params)

        if "data" not in response:
            _raise_loki_error("Invalid response format from Loki API")

        data = response["data"]
        result_type = data.get("resultType", "")
        results = data.get("result", [])

        # Format the response
        formatted_logs, total_entries = _format_log_entries(results)

        result = {
            "query": query,
            "result_type": result_type,
            "logs": formatted_logs,
            "summary": {
                "total_entries": total_entries,
                "streams_count": len(results),
                "query_time": datetime.now(UTC).isoformat(),
                "time_range": {"start": start_time, "end": end_time},
            },
            "query_parameters": {"limit": limit, "direction": direction},
        }

    except LokiAPIError:
        raise
    except Exception as exc:
        logger.exception("Error querying logs:")
        msg = f"Failed to query logs: {exc}"
        raise LokiAPIError(msg) from exc
    else:
        logger.info(
            f"Successfully retrieved {total_entries} log entries from {len(results)} streams",
        )
        return result


@mcp.tool()
async def get_log_labels() -> dict[str, Any]:
    """
    Retrieve all available labels from Loki.

    Returns:
        dict[str, Any]: Dictionary containing all available labels and their values.

    """
    try:
        logger.info("Fetching available labels from Loki")

        # Call Loki API to get labels
        response = await make_loki_request("/loki/api/v1/labels")

        if "data" not in response:
            _raise_loki_error("Invalid response format from Loki API")

        labels = response["data"]

        result = {
            "labels": labels,
            "labels_count": len(labels),
            "retrieved_at": datetime.now(UTC).isoformat(),
        }

    except LokiAPIError:
        raise
    except Exception as exc:
        logger.exception("Error getting labels:")
        msg = f"Failed to get labels: {exc}"
        raise LokiAPIError(msg) from exc
    else:
        logger.info(f"Successfully retrieved {len(labels)} labels")
        return result


@mcp.tool()
async def get_label_values(label: str) -> dict[str, Any]:
    """
    Retrieve all possible values for a specific label.

    Args:
        label (str): The label name to get values for (e.g., "service_name"")

    Returns:
        dict[str, Any]: Dictionary containing all values for the specified label.

    """
    try:
        logger.info(f"Fetching values for label: {label}")

        if not label:
            _raise_loki_error("Label name is required")

        # Call Loki API to get label values
        endpoint = f"/loki/api/v1/label/{quote(label)}/values"
        response = await make_loki_request(endpoint)

        if "data" not in response:
            _raise_loki_error("Invalid response format from Loki API")

        values = response["data"]

        result = {
            "label": label,
            "values": values,
            "values_count": len(values),
            "retrieved_at": datetime.now(UTC).isoformat(),
        }

    except LokiAPIError:
        raise
    except Exception as exc:
        logger.exception("Error getting label values:")
        msg = f"Failed to get label values: {exc}"
        raise LokiAPIError(msg) from exc
    else:
        logger.info(f"Successfully retrieved {len(values)} values for label {label}")
        return result


@mcp.tool()
async def search_logs_by_trace_id(
    trace_id: str,
    label: str,
    start_time: str | None = None,
    end_time: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """
    Search for logs associated with a specific trace ID.

    Args:
        trace_id (str): The trace ID to search for
        label (str): Loki labels for stream selector (e.g., 'service_name="user-service"')
        start_time (str | None): Start time for search (RFC3339 or relative like "5m", "1h")
        end_time (str | None): End time for search (RFC3339 format)
        limit (int): Maximum number of log entries to return (default: 100)

    Returns:
        dict[str, Any]: Logs associated with the trace ID.

    """
    try:
        logger.info(f"Searching logs for trace ID '{trace_id}' with label '{label}'")

        if not trace_id:
            _raise_loki_error("Trace ID is required")

        if not label:
            _raise_loki_error("Label is required")

        # Build LogQL query to search for trace_id
        query = f'{{{label}}} | json | trace_id="{trace_id}"'

        # If start_time is not provided, default to the last hour
        search_start_time = start_time or "1h"

        # Use the existing query_logs function
        result = await query_logs(
            query=query,
            start_time=search_start_time,
            end_time=end_time,
            limit=limit,
        )

        # Add trace-specific metadata
        result["trace_id"] = trace_id
        result["search_type"] = "trace_correlation"

    except LokiAPIError:
        raise
    except Exception as exc:
        logger.exception("Error searching logs by trace ID:")
        msg = f"Failed to search logs by trace ID: {exc}"
        raise LokiAPIError(msg) from exc
    else:
        logger.info(
            f"Successfully found logs for trace ID '{trace_id}' with label '{label}'",
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
    logger.info(f"Starting Loki MCP server with Loki URL: {LOKI_URL}")
    mcp.run(transport="stdio")
