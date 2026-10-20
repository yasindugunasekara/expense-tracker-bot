#!/bin/sh
set -e

# Default START_MCP to false if not set
export START_MCP="${START_MCP:-false}"

# Automatically enable MCP supervisor daemon if transport is configured for SSE
if [ "${MCP_TRANSPORT}" = "sse" ] || [ "${MCP_TRANSPORT}" = "streamable-http" ]; then
    export START_MCP="true"
fi

# Ensure /app/token.json exists as a file (prevents Docker from creating it as a directory on bind mount)
if [ ! -e /app/token.json ]; then
    echo "{}" > /app/token.json
fi

# Execute the given command or default to supervisord
exec "$@"
