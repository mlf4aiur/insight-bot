import atexit
import json
import logging
import os
from dataclasses import dataclass
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

JAEGER_URL = os.getenv("JAEGER_URL", "http://localhost:16686")

# Create an MCP server
mcp = FastMCP()

# HTTP client for making requests to Jaeger
http_client = httpx.AsyncClient(timeout=10.0)


class JaegerAPIError(Exception):
    """Custom exception for Jaeger API errors."""


def _raise_jaeger_error(msg: str) -> None:
    """Helper function to raise JaegerAPIError."""
    raise JaegerAPIError(msg)


async def make_jaeger_request(
    endpoint: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Make a request to Jaeger API."""
    url = f"{JAEGER_URL}/api{endpoint}"

    try:
        logger.debug(f"Making request to: {url} with params: {params}")
        response = await http_client.get(url, params=params)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as exc:
        logger.exception("HTTP error when calling Jaeger API:")
        msg = f"Failed to call Jaeger API: {exc}"
        raise JaegerAPIError(msg) from exc
    except Exception as exc:
        logger.exception("Unexpected error when calling Jaeger API")
        msg = f"Unexpected error: {exc}"
        raise JaegerAPIError(msg) from exc


@mcp.tool()
async def get_services() -> list[dict[str, Any]]:
    """
    Retrieve all service names from Jaeger tracing system.

    Returns:
        list[dict[str, Any]]: A list of dictionaries containing service information,
                             each with 'name' and 'retrieved_at' fields.

    """
    try:
        logger.info("Fetching services from Jaeger")

        # Call Jaeger API to get services
        response = await make_jaeger_request("/services")

        if "data" not in response:
            _raise_jaeger_error("Invalid response format from Jaeger API")

        services = response["data"]

        # Format the response
        service_list = []
        for service in services:
            service_list.append(
                {"name": service, "retrieved_at": datetime.now(UTC).isoformat()},
            )

    except JaegerAPIError:
        raise
    except Exception as exc:
        logger.exception("Error getting services:")
        msg = f"Failed to get services: {exc}"
        raise JaegerAPIError(msg) from exc
    else:
        logger.info(f"Successfully retrieved {len(service_list)} services")
        return service_list


@mcp.tool()
async def get_trace(trace_id: str) -> dict[str, Any]:
    """
    Retrieve trace information and spans by trace ID from Jaeger.

    Args:
        trace_id (str): The unique identifier of the trace to retrieve.

    Returns:
        dict[str, Any]: A dictionary containing trace information including
                       trace_id, spans, processes, and retrieved_at timestamp.

    """
    try:
        logger.info(f"Fetching trace with ID: {trace_id}")

        if not trace_id:
            _raise_jaeger_error("Trace ID is required")

        # Call Jaeger API to get trace
        response = await make_jaeger_request(f"/traces/{trace_id}")

        if "data" not in response:
            _raise_jaeger_error("Invalid response format from Jaeger API")

        trace_data = response["data"]

        if not trace_data:
            _raise_jaeger_error(f"No trace found with ID: {trace_id}")

        # Extract and format trace information
        traces = trace_data[0] if isinstance(trace_data, list) else trace_data

        result = {
            "trace_id": trace_id,
            "spans": [],
            "processes": traces.get("processes", {}),
            "retrieved_at": datetime.now(UTC).isoformat(),
        }

        # Process spans
        for span in traces.get("spans", []):
            span_info = {
                "span_id": span.get("spanID"),
                "trace_id": span.get("traceID"),
                "operation_name": span.get("operationName"),
                "service_name": span.get("process", {}).get("serviceName", ""),
                "start_time": span.get("startTime"),
                "duration": span.get("duration"),
                "tags": span.get("tags", []),
                "logs": span.get("logs", []),
                "references": span.get("references", []),
            }
            result["spans"].append(span_info)

    except JaegerAPIError:
        raise
    except Exception as exc:
        logger.exception("Error getting trace:")
        msg = f"Failed to get trace: {exc}"
        raise JaegerAPIError(msg) from exc
    else:
        logger.info(f"Successfully retrieved trace with {len(result['spans'])} spans")
        return result


@mcp.tool()
async def analyze_service_dependencies(
    service_name: str | None,
    lookback_hours: int = 24,
) -> dict[str, Any]:
    """
    Analyze service dependencies from Jaeger traces within a specified time window.

    Args:
        service_name (str | None): The name of the service to analyze dependencies for.
                                  If None, analyzes all service dependencies.
        lookback_hours (int): The number of hours to look back for dependency analysis.
                             Defaults to 24.

    Returns:
        dict[str, Any]: A dictionary containing dependency analysis results including
                       service_name, lookback_hours, analysis_time, dependencies list,
                       and summary statistics.

    """
    try:
        logger.info(f"Analyzing service dependencies for service: {service_name}")

        # Calculate time range for dependency analysis
        end_time = datetime.now(UTC)

        # Convert to milliseconds (Jaeger format)
        end_ms = int(end_time.timestamp() * 1_000)
        lookback_ms = lookback_hours * 3600 * 1000  # Convert hours to milliseconds

        # Call Jaeger API to get dependencies
        params = {"endTs": end_ms, "lookback": lookback_ms}

        response = await make_jaeger_request("/dependencies", params)

        if "data" not in response:
            _raise_jaeger_error("Invalid response format from Jaeger API")

        dependencies = response["data"]

        # Filter by service if specified
        if service_name:
            filtered_deps = []
            for dep in dependencies:
                if (
                    dep.get("parent") == service_name
                    or dep.get("child") == service_name
                ):
                    filtered_deps.append(dep)
            dependencies = filtered_deps

        # Format the response
        result = {
            "service_name": service_name,
            "lookback_hours": lookback_hours,
            "analysis_time": datetime.now(UTC).isoformat(),
            "dependencies": [],
            "summary": {
                "total_dependencies": len(dependencies),
                "unique_services": set(),
            },
        }

        for dep in dependencies:
            parent = dep.get("parent")
            child = dep.get("child")
            call_count = dep.get("callCount", 0)

            result["dependencies"].append(
                {
                    "parent_service": parent,
                    "child_service": child,
                    "call_count": call_count,
                    "relationship": f"{parent} -> {child}",
                },
            )

            # Add to unique services
            result["summary"]["unique_services"].add(parent)
            result["summary"]["unique_services"].add(child)

        # Convert set to list for JSON serialization
        result["summary"]["unique_services"] = list(
            result["summary"]["unique_services"],
        )

    except JaegerAPIError:
        raise
    except Exception as exc:
        logger.exception("Error analyzing service dependencies:")
        msg = f"Failed to analyze service dependencies: {exc}"
        raise JaegerAPIError(msg) from exc
    else:
        logger.info(f"Successfully analyzed {len(dependencies)} dependencies")
        return result


@mcp.tool()
async def get_service_operations(service_name: str) -> list[dict[str, Any]]:
    """
    Retrieve all operations for a specific service from Jaeger.

    Args:
        service_name (str): The name of the service to retrieve operations for.

    Returns:
        list[dict[str, Any]]: A list of dictionaries containing operation information,
                             each with 'name', 'service', and 'retrieved_at' fields.

    """
    try:
        logger.info(f"Fetching operations for service: {service_name}")

        if not service_name:
            _raise_jaeger_error("Service name is required")

        # Call Jaeger API to get operations
        params = {"service": service_name}
        response = await make_jaeger_request("/operations", params)

        if "data" not in response:
            _raise_jaeger_error("Invalid response format from Jaeger API")

        operations = response["data"]

        # Format the response
        operation_list = []
        for operation in operations:
            operation_list.append(
                {
                    "name": operation,
                    "service": service_name,
                    "retrieved_at": datetime.now(UTC).isoformat(),
                },
            )

    except JaegerAPIError:
        raise
    except Exception as exc:
        logger.exception("Error getting operations:")
        msg = f"Failed to get operations: {exc}"
        raise JaegerAPIError(msg) from exc
    else:
        logger.info(
            f"Successfully retrieved {len(operation_list)} operations for service {service_name}",
        )
        return operation_list


def _build_trace_search_params(params_obj: "TraceSearchParams") -> dict[str, Any]:
    """Build query parameters for trace search."""
    params = {"limit": params_obj.limit}

    if params_obj.service:
        params["service"] = params_obj.service
    if params_obj.operation:
        params["operation"] = params_obj.operation
    if params_obj.min_duration is not None:
        params["minDuration"] = params_obj.min_duration
    if params_obj.max_duration is not None:
        params["maxDuration"] = params_obj.max_duration
    if params_obj.lookback:
        params["lookback"] = params_obj.lookback

    # Handle time range
    if params_obj.start_time:
        start_dt = datetime.fromisoformat(params_obj.start_time)
        params["start"] = int(start_dt.timestamp() * 1_000_000)

    if params_obj.end_time and params_obj.end_time != "now":
        end_dt = datetime.fromisoformat(params_obj.end_time)
        params["end"] = int(end_dt.timestamp() * 1_000_000)

    # Handle tags
    if params_obj.tags:
        # Jaeger API expects tag values to be strings. Booleans should be converted to "true" or "false".
        stringified_tags = {}
        for k, v in params_obj.tags.items():
            if isinstance(v, bool):
                stringified_tags[k] = str(v).lower()
            else:
                stringified_tags[k] = str(v)
        params["tags"] = json.dumps(stringified_tags)

    return params


def _find_root_span(spans: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Find the root span (span with no parent references)."""
    for span in spans:
        references = span.get("references", [])
        if not any(ref.get("refType") == "CHILD_OF" for ref in references):
            return {
                "operation_name": span.get("operationName"),
                "service_name": span.get("process", {}).get("serviceName", ""),
                "start_time": span.get("startTime"),
                "duration": span.get("duration"),
                "tags": span.get("tags", []),
            }
    return None


def _process_trace_data(trace: dict[str, Any]) -> dict[str, Any]:
    """Process a single trace into formatted trace info."""
    spans = trace.get("spans", [])
    return {
        "trace_id": trace.get("traceID"),
        "spans_count": len(spans),
        "duration": spans[0].get("duration", 0) if spans else 0,
        "services": list(
            {
                span.get("process", {}).get("serviceName", "")
                for span in spans
                if span.get("process", {}).get("serviceName")
            },
        ),
        "root_span": _find_root_span(spans),
    }


@dataclass
class TraceSearchParams:
    service: str | None = None
    operation: str | None = None
    tags: dict[str, str] | None = None
    start_time: str | None = None
    end_time: str | None = None
    limit: int = 20
    min_duration: str | None = None
    max_duration: str | None = None
    lookback: str | None = None


@mcp.tool()
async def search_traces(params: TraceSearchParams) -> dict[str, Any]:
    """
    Search for traces in Jaeger based on various criteria.

    Args:
        params (TraceSearchParams): Encapsulates all search parameters.
            Tags should be a dictionary of string key-value pairs. For example: `{"error": "true"}`.
            Supported tags include:
            - `error`: "true" or "false"
            - `http.method`: e.g., "GET", "POST"
            - `http.status_code`: e.g., "200", "404"
            - `http.url`: The URL of the request.

    Returns:
        dict[str, Any]: Search results with traces list and summary statistics.

    """
    try:
        logger.info(
            f"Searching traces with service={params.service}, operation={params.operation}",
        )

        # Build query parameters for Jaeger trace search
        query_params = _build_trace_search_params(params)

        # Call Jaeger API to get traces
        response = await make_jaeger_request("/traces", query_params)

        if "data" not in response:
            _raise_jaeger_error("Invalid response format from Jaeger API")

        traces_data = response["data"]

        # Format the response
        result = {
            "search_parameters": {
                "service": params.service,
                "operation": params.operation,
                "tags": params.tags,
                "start_time": params.start_time,
                "end_time": params.end_time,
                "limit": params.limit,
                "min_duration": params.min_duration,
                "max_duration": params.max_duration,
                "lookback": params.lookback,
            },
            "traces": [_process_trace_data(trace) for trace in traces_data],
            "summary": {
                "total_found": len(traces_data),
                "search_time": datetime.now(UTC).isoformat(),
            },
        }

    except JaegerAPIError:
        raise
    except Exception as exc:
        logger.exception("Error searching traces:")
        msg = f"Failed to search traces: {exc}"
        raise JaegerAPIError(msg) from exc
    else:
        logger.info(f"Successfully found {len(result['traces'])} traces")
        return result


# Cleanup function
async def cleanup():
    """Cleanup resources."""
    await http_client.aclose()


# Register cleanup
atexit.register(lambda: http_client.aclose())


if __name__ == "__main__":
    # Run the server
    logger.info(f"Starting Jaeger MCP server with Jaeger URL: {JAEGER_URL}")
    mcp.run()
