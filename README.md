# Insight Bot

An AI-powered ChatOps assistant for observability. Ask questions in natural language to analyze metrics from Prometheus, logs from Loki, and traces from Jaeger to understand system health and performance.

## Overview

Insight Bot is a comprehensive monitoring platform that combines:

- **AI-Powered Analysis**: LangChain, LangGraph, and configurable LLM models for intelligent monitoring data analysis
- **Full Monitoring Stack**: Prometheus (metrics), Loki (logs), Jaeger (traces), and Grafana (visualization)
- **Mock Services**: Instrumented microservices for testing and demonstration
- **OpenTelemetry Integration**: Complete telemetry pipeline with OTEL Collector

## Demo

![Demo](media/demo.gif)

## How It Works

Insight Bot processes natural language queries through an AI pipeline that:

1. **Query Understanding**: Uses configurable LLM models (Google Gemini, OpenAI GPT, Anthropic Claude, etc.) to interpret user questions and identify the relevant monitoring data source
2. **Query Translation**: Converts natural language into appropriate query languages (PromQL, LogQL, or Jaeger API calls)
3. **Data Retrieval**: Executes queries against Prometheus, Loki, or Jaeger APIs
4. **Analysis & Response**: Analyzes results and provides human-readable insights with actionable recommendations

The system integrates seamlessly with your existing observability stack while providing an intuitive natural language interface for both technical and non-technical users.

## Features

### Monitoring Stack

- **Prometheus**: Metrics collection and storage with custom scraping configuration
- **Loki**: Log aggregation and querying with structured log analysis
- **Jaeger**: Distributed tracing for request flow analysis
- **Grafana**: Visualization dashboards with automated setup
- **OpenTelemetry Collector**: Unified telemetry data pipeline

### Mock Services

- **User Service** (FastAPI): Demonstrates HTTP request patterns and service dependencies
- **Profile Service** (Flask): Simulates realistic latency and error patterns for testing
- **Full Instrumentation**: OpenTelemetry auto-instrumentation for metrics, logs, and traces

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Python 3.13+ (for chatbot development)
- Google API key for Gemini model

### 1. Start the monitoring stack and mock services

```bash
docker-compose up -d
```

### 2. Access Services

| Service | URL | Purpose |
|---------|-----|---------|
| **Grafana** | <http://localhost:3000> | Visualization dashboards (admin/admin) |
| **Prometheus** | <http://localhost:9090> | Metrics queries |
| **Jaeger** | <http://localhost:16686> | Distributed trace analysis |
| **User Service** | <http://localhost:5001> | Mock API endpoint |
| **Profile Service** | <http://localhost:5002> | Mock API endpoint |

### 3. Start the AI Chatbot

```bash
cd chatbot
cp .env.example .env
# Edit .env and add your GOOGLE_API_KEY

# Install dependencies
uv sync

# Start the chatbot
streamlit run app/main.py --server.address 0.0.0.0 --server.port 8000 --server.headless true
```

Access the chatbot at <http://localhost:8000>

## Usage Examples

### Generate Test Data

First, generate some monitoring data to analyze:

#### Option 1: Use the chatbot

- Get user details for user ID 1
- Generate 5 mock user data entries

#### Option 2: Use curl commands

```bash
# Generate traffic to create monitoring data
for i in {1..20}; do
  curl http://localhost:5001/users/1
  curl http://localhost:5001/users/2
  curl http://localhost:5001/users/999  # Generates 404 errors
  sleep 0.1
done
```

### AI Assistant Queries

**Service Monitoring (Jaeger - Traces):**

- List all monitored services.
- Get details for trace ID 'a1b2c3d4'.
- Analyze dependencies for service user-service in the last 2 hours.
- List operations for service user-service.
- Search for traces from the user-service with errors in the last 2 hours.

**Log Monitoring (Loki - Logs):**

- Show all error logs from the user-service in the last 2 hours.
- What log labels are available?
- Get values for log label 'service_name'.
- Find logs for trace 'a1b2c3d4' in the 'user-service'.

**Metric Monitoring (Prometheus - Metrics):**

- Query http_server_duration_milliseconds_count for the number of 5xx responses in user-service.
- Show me the CPU usage of my server over the last hour, sampled every minute.
- List all available metrics.
- Get metadata for the 'http_requests_total' metric.
- Are all my services being scraped correctly by Prometheus?

### Manual Queries

**Prometheus (Metrics):**

```promql
# Request rate
rate(http_requests_total[5m])

# Error rate
rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m])

# Response time percentiles
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))
```

**Loki (Logs):**

```logql
# Error logs from user service
{service_name="user-service"} |= "ERROR"

# Logs with response times
{service_name="profile-service"} | json | duration > 500ms
```

## Configuration

### Environment Variables

```bash
# Required for chatbot
GOOGLE_API_KEY=your_google_api_key_here

# Optional (with defaults)
LANGCHAIN_MODEL=google_genai:gemini-2.5-flash
PROMETHEUS_URL=http://localhost:9090
LOKI_URL=http://localhost:3100
JAEGER_URL=http://localhost:16686
```

### Service Configuration

- **Prometheus**: Configure scraping targets in `monitoring_stack/prometheus/prometheus.yml`
- **OTEL Collector**: Modify pipeline configuration in `monitoring_stack/otel-collector/otel-collector-config.yaml`
- **Grafana**: Dashboards auto-configured via `monitoring_stack/grafana/setup-grafana.sh`
- **MCP Servers**: AI tool configuration in `chatbot/app/config/mcp_client.json`

## License

See the LICENSE file for licensing information.
