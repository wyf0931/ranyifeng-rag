#!/bin/bash

# Operations script for RAG system
# Usage: ./bin/ops.sh [start|stop|restart|logs|status] [options]

set -e

# Configuration
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$PROJECT_ROOT/.venv"
PID_FILE="$PROJECT_ROOT/.flask.pid"
LOG_FILE="$PROJECT_ROOT/logs/flask.log"
ENV_FILE="$PROJECT_ROOT/.env"

# Flask settings
HOST="${FLASK_HOST:-127.0.0.1}"
PORT="${FLASK_PORT:-5000}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Ensure logs directory exists
mkdir -p "$(dirname "$LOG_FILE")"

# Load environment if exists
if [ -f "$ENV_FILE" ]; then
    export $(cat "$ENV_FILE" | grep -v '^#' | xargs)
fi

# Function to kill process on a port
kill_port() {
    local port=$1
    local pids=$(lsof -ti :$port 2>/dev/null)
    if [ -n "$pids" ]; then
        echo -e "${YELLOW}Killing processes on port $port: $pids${NC}"
        echo "$pids" | xargs kill -9 2>/dev/null || true
        sleep 1
    fi
}

# Function to check and kill port if occupied
ensure_port_free() {
    local port=$1
    local pids=$(lsof -ti :$port 2>/dev/null)
    if [ -n "$pids" ]; then
        echo -e "${YELLOW}Port $port is occupied by: $pids${NC}"
        echo -e "${YELLOW}Attempting to free the port...${NC}"
        kill_port "$port"
        # Verify port is free
        pids=$(lsof -ti :$port 2>/dev/null)
        if [ -n "$pids" ]; then
            echo -e "${RED}Failed to free port $port${NC}"
            return 1
        fi
        echo -e "${GREEN}Port $port freed successfully${NC}"
    fi
    return 0
}

start() {
    # Parse optional --port argument
    if [[ "$1" == "--port" && -n "$2" ]]; then
        PORT="$2"
        export FLASK_PORT="$PORT"
    fi

    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            echo -e "${YELLOW}Flask is already running (PID: $PID)${NC}"
            return 1
        else
            rm -f "$PID_FILE"
        fi
    fi

    # Ensure port is free
    if ! ensure_port_free "$PORT"; then
        echo -e "${RED}Failed to start Flask - port $PORT is in use${NC}"
        return 1
    fi

    echo -e "${GREEN}Starting Flask server on port $PORT...${NC}"

    # Start Flask in background
    cd "$PROJECT_ROOT"
    nohup uv run python run.py > "$LOG_FILE" 2>&1 &

    echo $! > "$PID_FILE"

    sleep 2

    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            echo -e "${GREEN}Flask started successfully (PID: $PID)${NC}"
            echo -e "Access: ${GREEN}http://$HOST:$PORT${NC}"
            return 0
        fi
    fi

    echo -e "${RED}Failed to start Flask${NC}"
    return 1
}

stop() {
    if [ ! -f "$PID_FILE" ]; then
        echo -e "${YELLOW}Flask is not running${NC}"
        return 0
    fi

    PID=$(cat "$PID_FILE")

    if ps -p "$PID" > /dev/null 2>&1; then
        echo -e "${GREEN}Stopping Flask (PID: $PID)...${NC}"
        kill "$PID"
        sleep 1

        if ps -p "$PID" > /dev/null 2>&1; then
            echo -e "${YELLOW}Force stopping...${NC}"
            kill -9 "$PID"
        fi

        rm -f "$PID_FILE"
        echo -e "${GREEN}Flask stopped${NC}"
    else
        echo -e "${YELLOW}Flask was not running (stale PID file)${NC}"
        rm -f "$PID_FILE"
    fi
}

restart() {
    # Parse optional --port argument
    if [[ "$1" == "--port" && -n "$2" ]]; then
        PORT="$2"
        export FLASK_PORT="$PORT"
    fi

    stop
    sleep 1
    start "$@"
}

logs() {
    if [ ! -f "$LOG_FILE" ]; then
        echo -e "${YELLOW}No log file found${NC}"
        return 1
    fi

    tail -f "$LOG_FILE"
}

status() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            echo -e "${GREEN}Flask is running (PID: $PID)${NC}"
            echo -e "Access: ${GREEN}http://$HOST:$PORT${NC}"
            echo "Log file: $LOG_FILE"
            return 0
        else
            echo -e "${RED}Flask is not running (stale PID file)${NC}"
            return 1
        fi
    else
        echo -e "${RED}Flask is not running${NC}"
        return 1
    fi
}

# Main
case "${1:-}" in
    start)
        shift
        start "$@"
        ;;
    stop)
        stop
        ;;
    restart)
        shift
        restart "$@"
        ;;
    logs)
        logs
        ;;
    status)
        status
        ;;
    *)
        echo "Usage: $0 [start|stop|restart|logs|status] [--port PORT]"
        echo "Examples:"
        echo "  $0 start              # Start on default port 5000"
        echo "  $0 start --port 8000  # Start on port 8000"
        echo "  $0 restart --port 8000 # Restart on port 8000"
        exit 1
        ;;
esac
