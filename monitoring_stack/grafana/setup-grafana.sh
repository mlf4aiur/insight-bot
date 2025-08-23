#!/usr/bin/env ash

set -euo pipefail

# Configuration variables
SCRIPT_NAME="$(basename "$0")"
GRAFANA_HOST="${GRAFANA_HOST:-grafana}"
GRAFANA_PORT="${GRAFANA_PORT:-3000}"
GRAFANA_USER="${GRAFANA_USER:-admin}"
GRAFANA_PASSWORD="${GRAFANA_PASSWORD:-admin}"
PROMETHEUS_URL="${PROMETHEUS_URL:-http://prometheus:9090}"
LOKI_URL="${LOKI_URL:-http://loki:3100}"
TIMEOUT="${TIMEOUT:-300}"  # 5 minutes timeout for service readiness

# Colors for output (if terminal supports it)
if [ -t 1 ]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    BLUE='\033[0;34m'
    NC='\033[0m' # No Color
else
    RED=''
    GREEN=''
    YELLOW=''
    BLUE=''
    NC=''
fi

# Logging functions
log_info() {
    echo "${BLUE}[INFO]${NC} $*"
}

log_success() {
    echo "${GREEN}[SUCCESS]${NC} $*"
}

log_warning() {
    echo "${YELLOW}[WARNING]${NC} $*"
}

log_error() {
    echo "${RED}[ERROR]${NC} $*" >&2
}

# Function to wait for a service to become available
wait_for_service() {
    local host=$1
    local port=$2
    local name=$3
    local timeout=${4:-$TIMEOUT}
    local elapsed=0

    log_info "Waiting for $name ($host:$port) - timeout: ${timeout}s"

    while [ $elapsed -lt $timeout ]; do
        if wget -q --timeout=5 --tries=1 -O /dev/null "http://$host:$port" 2>/dev/null; then
            log_success "$name is ready (took ${elapsed}s)"
            return 0
        fi
        sleep 1
        elapsed=$((elapsed + 1))
    done

    log_error "$name failed to become ready within ${timeout}s"
    return 1
}

# Function to check if data source already exists
check_datasource_exists() {
    local name=$1
    local response

    response=$(wget -q -O - \
        --header="Authorization: Basic $(echo -n "$GRAFANA_USER:$GRAFANA_PASSWORD" | base64)" \
        "http://$GRAFANA_HOST:$GRAFANA_PORT/api/datasources/name/$name" 2>/dev/null)

    if [ $? -eq 0 ] && echo "$response" | grep -q '"name"'; then
        return 0  # Data source exists
    else
        return 1  # Data source doesn't exist
    fi
}

# Function to add a data source to Grafana
add_datasource() {
    local name=$1
    local type=$2
    local url=$3
    local response
    local http_code

    log_info "Adding $name as a Grafana data source..."

    # Check if data source already exists
    if check_datasource_exists "$name"; then
        log_warning "$name data source already exists, skipping..."
        return 0
    fi

    # Create temporary file for response
    response_file=$(mktemp)

    # Add the data source
    http_code=$(wget -q -O "$response_file" \
        --server-response \
        --header="Content-Type: application/json" \
        --header="Authorization: Basic $(echo -n "$GRAFANA_USER:$GRAFANA_PASSWORD" | base64)" \
        --post-data "{
            \"name\": \"$name\",
            \"type\": \"$type\",
            \"access\": \"proxy\",
            \"url\": \"$url\",
            \"basicAuth\": false,
            \"isDefault\": false
        }" \
        "http://$GRAFANA_HOST:$GRAFANA_PORT/api/datasources" 2>&1 | \
        grep "HTTP/" | tail -1 | awk '{print $2}')

    # Check response
    if [ "$http_code" = "200" ] || [ "$http_code" = "201" ]; then
        log_success "$name data source added successfully"
        rm -f "$response_file"
        return 0
    else
        log_error "Failed to add $name data source (HTTP $http_code)"
        if [ -f "$response_file" ]; then
            log_error "Response: $(cat "$response_file")"
            rm -f "$response_file"
        fi
        return 1
    fi
}

# Function to test data source connectivity
test_datasource() {
    local name=$1
    local response
    local http_code

    log_info "Testing $name data source connectivity..."

    # Get data source ID first
    ds_response=$(wget -q -O - \
        --header="Authorization: Basic $(echo -n "$GRAFANA_USER:$GRAFANA_PASSWORD" | base64)" \
        "http://$GRAFANA_HOST:$GRAFANA_PORT/api/datasources/name/$name" 2>/dev/null)

    if [ $? -ne 0 ]; then
        log_warning "Could not retrieve $name data source info for testing"
        return 1
    fi

    # Extract ID (basic parsing - assumes single line JSON response)
    ds_id=$(echo "$ds_response" | sed -n 's/.*"id":\([0-9]*\).*/\1/p')

    if [ -z "$ds_id" ]; then
        log_warning "Could not extract data source ID for $name"
        return 1
    fi

    # Test the data source
    response_file=$(mktemp)
    http_code=$(wget -q -O "$response_file" \
        --server-response \
        --header="Authorization: Basic $(echo -n "$GRAFANA_USER:$GRAFANA_PASSWORD" | base64)" \
        "http://$GRAFANA_HOST:$GRAFANA_PORT/api/datasources/$ds_id/health" 2>&1 | \
        grep "HTTP/" | tail -1 | awk '{print $2}')

    if [ "$http_code" = "200" ]; then
        log_success "$name data source connectivity test passed"
        rm -f "$response_file"
        return 0
    else
        log_warning "$name data source connectivity test failed (HTTP $http_code)"
        rm -f "$response_file"
        return 1
    fi
}

# Function to create service account and token
create_service_account_token() {
    local sa_name="grafana"
    local sa_display_name="Grafana"
    local token_name="grafana-token"
    local response
    local http_code
    local sa_id
    local token

    log_info "Creating service account for Grafana..."

    # Create service account
    response_file=$(mktemp)
    http_code=$(wget -q -O "$response_file" \
        --server-response \
        --header="Content-Type: application/json" \
        --header="Authorization: Basic $(echo -n "$GRAFANA_USER:$GRAFANA_PASSWORD" | base64)" \
        --post-data "{
            \"name\": \"$sa_name\",
            \"displayName\": \"$sa_display_name\",
            \"role\": \"Viewer\"
        }" \
        "http://$GRAFANA_HOST:$GRAFANA_PORT/api/serviceaccounts" 2>&1 | \
        grep "HTTP/" | tail -1 | awk '{print $2}')

    if [ "$http_code" = "200" ] || [ "$http_code" = "201" ]; then
        log_success "Service account created successfully"
        sa_id=$(cat "$response_file" | sed -n 's/.*"id":\([0-9]*\).*/\1/p')
    elif [ "$http_code" = "409" ]; then
        log_warning "Service account already exists, retrieving existing one..."
        # Get existing service account
        rm -f "$response_file"
        response_file=$(mktemp)
        wget -q -O "$response_file" \
            --header="Authorization: Basic $(echo -n "$GRAFANA_USER:$GRAFANA_PASSWORD" | base64)" \
            "http://$GRAFANA_HOST:$GRAFANA_PORT/api/serviceaccounts/search?query=$sa_name" 2>/dev/null

        sa_id=$(cat "$response_file" | sed -n 's/.*"id":\([0-9]*\).*/\1/p')
    else
        log_error "Failed to create service account (HTTP $http_code)"
        if [ -f "$response_file" ]; then
            log_error "Response: $(cat "$response_file")"
        fi
        rm -f "$response_file"
        return 1
    fi

    if [ -z "$sa_id" ]; then
        log_error "Could not extract service account ID"
        rm -f "$response_file"
        return 1
    fi

    log_info "Service account ID: $sa_id"
    rm -f "$response_file"

    # Create token for service account
    log_info "Creating token for service account..."
    response_file=$(mktemp)
    http_code=$(wget -q -O "$response_file" \
        --server-response \
        --header="Content-Type: application/json" \
        --header="Authorization: Basic $(echo -n "$GRAFANA_USER:$GRAFANA_PASSWORD" | base64)" \
        --post-data "{
            \"name\": \"$token_name\"
        }" \
        "http://$GRAFANA_HOST:$GRAFANA_PORT/api/serviceaccounts/$sa_id/tokens" 2>&1 | \
        grep "HTTP/" | tail -1 | awk '{print $2}')

    if [ "$http_code" = "200" ] || [ "$http_code" = "201" ]; then
        log_success "Service account token created successfully"
        token=$(cat "$response_file" | sed -n 's/.*"key":"\([^"]*\)".*/\1/p')

        if [ -n "$token" ]; then
            log_success "Service account token: $token"
            log_info "Set GRAFANA_TOKEN environment variable to: $token"

            # Optionally write token to a file for easy access
            echo "$token" > /tmp/grafana-service-account-token
            log_info "Token also saved to: /tmp/grafana-service-account-token"
        else
            log_error "Could not extract token from response"
            rm -f "$response_file"
            return 1
        fi
    else
        log_error "Failed to create service account token (HTTP $http_code)"
        if [ -f "$response_file" ]; then
            log_error "Response: $(cat "$response_file")"
        fi
        rm -f "$response_file"
        return 1
    fi

    rm -f "$response_file"
    return 0
}

# Function to display configuration
show_config() {
    log_info "Configuration:"
    log_info "  Grafana: http://$GRAFANA_HOST:$GRAFANA_PORT"
    log_info "  Grafana User: $GRAFANA_USER"
    log_info "  Prometheus URL: $PROMETHEUS_URL"
    log_info "  Loki URL: $LOKI_URL"
    log_info "  Timeout: ${TIMEOUT}s"
}

# Main execution
main() {
    log_info "Starting $SCRIPT_NAME"
    show_config

    # Wait for Grafana to be ready
    if ! wait_for_service "$GRAFANA_HOST" "$GRAFANA_PORT" "Grafana"; then
        log_error "Grafana is not available, exiting"
        exit 1
    fi

    # Give Grafana a moment to fully initialize
    log_info "Waiting for Grafana to fully initialize..."
    sleep 5

    # Add data sources
    success_count=0
    total_count=0

    # Add Prometheus
    total_count=$((total_count + 1))
    if add_datasource "Prometheus" "prometheus" "$PROMETHEUS_URL"; then
        success_count=$((success_count + 1))
        test_datasource "Prometheus"
    fi

    # Add Loki
    total_count=$((total_count + 1))
    if add_datasource "Loki" "loki" "$LOKI_URL"; then
        success_count=$((success_count + 1))
        test_datasource "Loki"
    fi

    # Create service account token
    log_info "Creating service account token..."
    if create_service_account_token; then
        log_success "Service account token created successfully"
    else
        log_warning "Failed to create service account token, but continuing..."
    fi

    # Summary
    log_info "Data source setup complete: $success_count/$total_count successful"

    if [ $success_count -eq $total_count ]; then
        log_success "All data sources configured successfully!"
        exit 0
    else
        log_error "Some data sources failed to configure"
        exit 1
    fi
}

# Run main function
main "$@"
