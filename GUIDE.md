# Guide

This document provides a list of available tools, their descriptions, and example chat messages to help you get started.

User Management:

- `get_user`: Retrieve user details by ID.
  - Get user details for user ID 1.
  - Can you pull up the info for user 1?
- `generate_mock_data`: Generate mock user data.
  - Generate 5 mock user data entries.

Service Monitoring (Jaeger - Traces):

- `get_services`: List all monitored services.
  - List all monitored services.
  - What services are we monitoring?
- `get_trace`: Get details of a specific trace.
  - Get details for trace ID 'a1b2c3d4'.
  - Look up trace 'a1b2c3d4'.
- `analyze_service_dependencies`: Analyze dependencies for a service.
  - Analyze dependencies for service user-service in the last 2 hours.
  - What are the dependencies for the user-service over the last 2 hours?
- `get_service_operations`: List operations for a service.
  - List operations for service user-service.
  - What operations does the user-service have?
- `search_traces`: Search for traces based on various criteria.
  - Search for traces from the user-service with errors in the last 2 hours.
  - Find traces for the user-service that failed with a 502 error in the last hour.
  - Search for traces in the user-service tagged with http.status_code=502 from the last hour.
  - Search for traces from the service user-service with tags {'http.status_code': '502'} in the last 2 hours.

Log Monitoring (Loki - Logs):

- `query_logs`: Query logs using LogQL.
  - Query logs with LogQL: '{service_name=\"user-service\"} | json | severity_text=\"ERROR\"'.
  - Show all error logs from the user-service in the last 2 hours.
  - Query logs from user-service in the past 2 hours where severity_text is "ERROR".
- `get_log_labels`: Get all available log labels.
  - Get all available log labels.
  - What log labels are available?
- `get_label_values`: Get values for a specific log label.
  - Get values for log label 'service_name'.
  - What are the possible values for the 'service_name' label?
- `search_logs_by_trace_id`: Search for logs associated with a specific trace ID. The `label` parameter is used as a Loki stream selector (e.g., `service_name="user-service"`).
  - Find logs for trace 'a1b2c3d4' in the 'user-service'.
  - Search for logs with trace ID 'a1b2c3d4' from the 'user-service'.
  - Get logs from the 'profile-service' related to trace 'a1b2c3d4'.

Metric Monitoring (Prometheus - Metrics):

- `execute_query`: Executes an instant PromQL query. This means it returns the latest value for a given metric or expression at a specific point in time (or now, if time is not specified).
  - Query http_server_duration_milliseconds_count for the number of 5xx responses in user-service, filtered by http_status_code and exported_job.
- `execute_range_query`: Executes a PromQL query over a specified time range, returning a series of values. You define the start time, end time, and the interval (step) between data points.
  - Show me the CPU usage of my server over the last hour, sampled every minute.
  - Plot the request rate of the user-service over the last 24 hours.
- `list_metrics`: Retrieves a list of all metric names that Prometheus is currently collecting.
  - List all available metrics.
  - What metrics are being scraped?
- `get_metric_metadata`: Provides detailed information about a specific metric, such as its type (counter, gauge, histogram), help text, and unit.
  - Get metadata for the 'http_requests_total' metric.
  - What does the 'cpu_usage' metric represent?
- `get_targets`: Fetches information about all the configured scrape targets in Prometheus. This includes their health status (up/down), last scrape time, and any labels associated with them.
  - Are all my services being scraped correctly by Prometheus?
  - Check the status of scrape targets.
